"""Build data/state_assemblies.db with State Legislative Assembly results.

Also writes gzipped copies (state_assemblies.db.gz, ae_candidates.csv.gz) small enough
for GitHub; tests and the dashboard exporter use the .db.

For each raw/ae/<state>/<year>/ folder the source is, in order of preference:
  1. a 'Detailed Results' spreadsheet (ECI publishes these from ~2017),
  2. the 'Detailed Results' section of the PDF report (text via PyMuPDF).
Every constituency's candidate votes are checked against ECI's printed total.
"""
import csv
import gzip
import json
import shutil
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ae_text import pdf_text  # noqa: E402
from ae_xlsx import load_detailed_xlsx, read_any  # noqa: E402
from build_db import mark_winners  # noqa: E402
from download_ae import DEFUNCT, slug  # noqa: E402
from parse_pdf_results import parse_text, winners_from_successful_list  # noqa: E402
from reference import PARTY_ALIASES, PARTY_FAMILY, canonical_state  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW, TEXT, OUT = ROOT / "raw" / "ae", ROOT / "text" / "ae", ROOT / "data"

# Display names for folder slugs
NAMES = {slug(s): s for s, _, _ in json.loads((Path(__file__).parent / "ae" / "ae_links_raw.json").read_text())}
NAMES.update({slug(s): s for s, _, _ in DEFUNCT})
NAMES.update({"jammu-kashmir": "Jammu & Kashmir"})
PARTY_NAMES = {}  # (state, year) -> {abbr: (name, type)}
# Gaps in ECI's own reports (explained in the notes; no rows are invented for them)
KNOWN_GAPS = {
    ("Arunachal Pradesh", 2024): "ECI's statistical report covers only the 50 seats that went to the polls; "
                                 "the other 10 of the 60 seats were won unopposed and are not in the report.",
    ("Arunachal Pradesh", 2014): "ECI's PDF for this election is scanned images with no text layer, so it could not be read.",
}
UNOPPOSED = {}  # (state, year) -> ['AC (party)', ...] added from the successful-candidates list


def detailed_files(folder: Path, exts):
    files = [p for p in folder.iterdir() if p.suffix.lower() in exts and not p.name.startswith("_")]
    det = [p for p in files if re.search(r"detail|deailed", p.name, re.I)]
    return det or ([] if len(files) > 4 else files)  # sectioned pages: only the detailed file


def party_names_from_text(text):
    """abbr -> (name, type) from 'List of Participating Political Parties' pages."""
    out, ptype = {}, None
    for page in text.split("\f"):
        if "LIST OF PARTICIPATING POLITICAL PARTIES" not in page.upper() and "PARTYTYPE" not in page.upper():
            continue
        for line in page.split("\n"):
            u = line.strip().upper()
            if u.startswith("NATIONAL PARTIES"):
                ptype = "National"
            elif "STATE PARTIES" in u:
                ptype = "State"
            elif "REGISTERED" in u and "PARTIES" in u:
                ptype = "Registered (unrecognised)"
            elif u.startswith("INDEPENDENT"):
                ptype = "Independent"
            m = re.match(r"^\d+\s*\.\s*(\S+)\s+(.+)$", line.strip())
            if m and ptype:
                out.setdefault(m.group(1), (m.group(2).strip().title(), ptype))
    return out


def party_names_from_xls(folder):
    out = {}
    for f in folder.glob("*olitical*arties*articipated*.xls*"):
        try:
            df = read_any(f)
        except Exception:
            continue
        for _, row in df.iterrows():
            vals = [str(v).strip() for v in row if str(v) != "nan"]
            if len(vals) >= 3 and vals[0].rstrip(".").isdigit():
                abbr = vals[2] if len(vals) >= 4 and len(vals[1]) <= 2 else vals[1]
                name = vals[-1]
                if abbr and name and abbr != name:
                    out.setdefault(abbr, (name, None))
    return out


def _norm_ac(name):
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"\((SC|ST|BL|SANGHA)\)", "", str(name).upper()))


def load_successful(folder: Path):
    """Winners from ECI's 'List of Successful Candidates' spreadsheet:
    [(ac_no or None, ac_name, winner, party, sex)]."""
    for f in folder.glob("*uccessful*.xls*"):
        try:
            df = read_any(f)
        except Exception:
            continue
        hr = next((i for i in range(min(10, len(df)))
                   if df.iloc[i].astype(str).str.upper().str.contains("CONSTITUENCY").any()), None)
        if hr is None:
            continue
        cols = [str(c).strip().upper() for c in df.iloc[hr]]
        ci = lambda *k: next((i for i, c in enumerate(cols) if any(x == c or x in c for x in k)), None)  # noqa: E731
        i_no = next((i for i, c in enumerate(cols) if "AC NO" in c or ("CONSTITUENCY" in c and "NO" in c)), None)
        i_ac = next((i for i, c in enumerate(cols) if ("CONSTITUENCY" in c or "AC NAME" in c) and i != i_no), None)
        i_name = next((i for i, c in enumerate(cols) if "WINNER" in c), None)
        if i_name is None:
            i_name = next((i for i, c in enumerate(cols) if "NAME" in c and "CONSTITUENCY" not in c and "AC" not in c), None)
        i_party, i_sex = ci("PARTY"), ci("SEX")
        out = []
        for _, r in df.iloc[hr + 1:].iterrows():
            ac = r.iloc[i_ac] if i_ac is not None else None
            party = str(r.iloc[i_party]).strip() if i_party is not None else "nan"
            if ac is None or str(ac) == "nan" or party in ("nan", "") or party.replace(".0", "").isdigit() \
                    or str(ac).strip().upper().startswith("TOTAL") or str(ac).strip().replace(".0", "").isdigit():
                continue  # summary rows at the foot of the list
            no = r.iloc[i_no] if i_no is not None else None
            out.append((int(float(no)) if no is not None and str(no).replace(".0", "").isdigit() else None,
                        str(ac).strip(), str(r.iloc[i_name]).strip() if i_name is not None else "",
                        str(r.iloc[i_party]).strip(),
                        (str(r.iloc[i_sex]).strip()[:1].upper() if i_sex is not None else None)))
        if out:
            return out
    return []


def add_unopposed(rows, folder, state, year):
    """ECI's detailed-results spreadsheets leave out seats won unopposed; take those
    winners from the successful-candidates list of the same report."""
    winners = load_successful(folder)
    have_no = {r["pc_no"] for r in rows}
    have_name = {_norm_ac(r["pc_name"]) for r in rows}
    added = []
    for i, (no, ac, name, party, sex) in enumerate(winners, 1):
        present = (no in have_no) if no is not None else (_norm_ac(ac) in have_name)
        if present:
            continue
        rows.append({"year": year, "state": state, "pc_no": no or i, "pc_name": ac, "seats": 1, "reserved": None,
                     "candidate": name, "sex": sex if sex in ("M", "F") else None, "age": None, "category": None,
                     "party": party, "votes": 0, "postal": None, "rank": 1, "electors": None, "voters": None,
                     "valid_votes": 0, "uncontested": 1})
        added.append(f"{no or i} {ac} ({party})")
    return added


def load_folder(folder: Path, state: str, year: int):
    """Return (rows, source_kind, source_file, successful_lines)."""
    for f in detailed_files(folder, {".xlsx", ".xls"}):
        rows = load_detailed_xlsx(f, year, state)
        if rows:
            by = defaultdict(list)
            for r in rows:
                by[(r["ac_no"], r["ac_name"])].append(r)
            out = []
            for (no, name), cands in by.items():
                valid = sum(c["votes"] for c in cands if c["party"] != "NOTA")
                cands.sort(key=lambda c: (c["party"] == "NOTA", -c["votes"]))
                for rank, c in enumerate(cands, 1):
                    out.append({"year": year, "state": state, "pc_no": no, "pc_name": name, "seats": 1,
                                "reserved": None, "candidate": c["candidate"], "sex": c["sex"],
                                "age": c["age"], "category": c["category"], "party": c["party"],
                                "votes": c["votes"], "postal": c["postal"], "rank": rank,
                                "electors": c["electors"], "voters": None, "valid_votes": valid,
                                "uncontested": 0})
            added = add_unopposed(out, folder, state, year)
            if added:
                UNOPPOSED[(state, year)] = added
            return out, "xlsx", f, []
    best, src, succ = [], None, []
    for f in sorted(detailed_files(folder, {".pdf"}), key=lambda p: -p.stat().st_size):
        t = pdf_text(f, TEXT / folder.parent.name / folder.name / (f.stem + ".txt"))
        succ += winners_from_successful_list(t)
        PARTY_NAMES.setdefault((state, year), {}).update(party_names_from_text(t))
        rows = parse_text(t, year, fixed_state=state)
        if len(rows) > len(best):
            best, src = rows, f
    return best, "pdf", src, succ


def main():
    defunct = {slug(s) for s, _, _ in DEFUNCT}
    # current-state folders first, so a defunct-state copy of the same election is skipped
    folders = sorted((p for p in RAW.glob("*/*") if p.is_dir() and any(p.iterdir())),
                     key=lambda p: (p.parent.name in defunct, p.parent.name, p.name))
    all_rows, report, notes, seen = [], [], [], set()
    for folder in folders:
        year = int(folder.name)
        # Madras (1957-67) and Mysore (1957-72) are the same states as Tamil Nadu and Karnataka
        state = canonical_state(NAMES.get(folder.parent.name, folder.parent.name.replace("-", " ").title()), year)
        if (state, year) in seen:
            notes.append(f"{state} {year}: ECI lists this report under both the old and new state name; loaded once")
            continue
        seen.add((state, year))
        PARTY_NAMES.setdefault((state, year), {}).update(party_names_from_xls(folder))
        try:
            rows, kind, src, succ = load_folder(folder, state, year)
        except Exception as e:  # keep going; the report lists the failure
            rows, kind, src, succ = [], "error", None, []
            notes.append(f"{state} {year}: could not parse ({e})")
        source_url = (folder / "_source.txt").read_text().split()[0] if (folder / "_source.txt").exists() else ""
        if not rows:
            report.append({"state": state, "year": year, "source": kind, "acs": 0, "seats": 0,
                           "candidates": 0, "mismatched_acs": None, "missing_acs": None, "status": "NO DATA"})
            continue
        # winners
        nota = [r for r in rows if r["party"] == "NOTA"]
        real = [r for r in rows if r["party"] != "NOTA"]
        flagged = mark_winners(real, succ)
        for r in nota:
            r["won"] = 0
        for f in flagged:
            notes.append(f"{state} {year}: multi-member seat {f[0][1]} {f[0][2]}: used top {f[2]} vote-getters "
                         f"({f[1]} matched ECI's successful-candidates list)")
        by = defaultdict(list)
        for r in rows:
            by[(r["pc_no"], r["pc_name"])].append(r)
        mism = [k for k, v in by.items()
                if v[0]["valid_votes"] and sum(x["votes"] for x in v if x["party"] != "NOTA") != v[0]["valid_votes"]
                and sum(x["votes"] for x in v) != v[0]["valid_votes"]]
        for k in mism:
            notes.append(f"{state} {year}: AC {k[0]} {k[1]}: candidate votes do not add up to ECI's printed total")
        for r in rows:
            r["source"] = source_url
            r["source_file"] = src.name if src else None
        all_rows += rows
        if (state, year) in UNOPPOSED:
            notes.append(f"{state} {year}: won unopposed (not in ECI's detailed results, taken from its list of "
                         f"successful candidates): {', '.join(UNOPPOSED[(state, year)])}")
        nos = {k[0] for k in by if k[0]}
        missing = [i for i in range(1, max(nos) + 1) if i not in nos] if nos else []
        if missing:
            notes.append(f"{state} {year}: no detailed result for AC no. {', '.join(map(str, missing[:20]))}"
                         + (" …" if len(missing) > 20 else ""))
        report.append({"state": state, "year": year, "source": kind, "acs": len(by),
                       "seats": sum(v[0]["seats"] for v in by.values()),
                       "candidates": len(real), "mismatched_acs": len(mism),
                       "missing_acs": len(missing),
                       "status": "OK" if not mism and not missing else "CHECK"})
        print(f"{state} {year}: {kind} {len(by)} ACs, {len(real)} candidates, {len(mism)} mismatched", flush=True)

    # normalise
    for r in all_rows:
        r["party_raw"] = r["party"]
        r["party"] = PARTY_ALIASES.get((r["year"], r["party"]), PARTY_ALIASES.get(r["party"], r["party"]))
        r["party_family"] = PARTY_FAMILY.get(r["party"], r["party"])
        if r.get("valid_votes") is None:
            r["valid_votes"] = 0
        # NOTA from 2013: valid votes exclude it, as in ECI's reports
        denom = r["valid_votes"] + (r["votes"] if r["party"] == "NOTA" else 0)
        r["vote_share"] = round(100 * r["votes"] / denom, 4) if denom else None
        if not r.get("reserved"):
            m = re.search(r"\((SC|ST)\)", r["pc_name"])
            r["reserved"] = m.group(1) if m else None
    # Turnout where ECI's detailed results give no 'voters' figure: votes counted for
    # candidates and NOTA over electors (leaves out rejected ballots, <1% of votes).
    counted = defaultdict(int)
    for r in all_rows:
        counted[(r["state"], r["year"], r["pc_no"], r["pc_name"])] += r["votes"]
    for r in all_rows:
        if r.get("voters") is None and r.get("electors"):
            r["voters"] = counted[(r["state"], r["year"], r["pc_no"], r["pc_name"])] or None

    # reservation from candidate categories where the name does not say
    by = defaultdict(list)
    for r in all_rows:
        by[(r["state"], r["year"], r["pc_no"], r["pc_name"])].append(r)
    for cands in by.values():
        if cands[0]["reserved"]:
            continue
        cats = {c.get("category") for c in cands if c["party"] != "NOTA"}
        res = cats.pop() if len(cats) == 1 else "GEN"
        for c in cands:
            c["reserved"] = res if res in ("SC", "ST") else "GEN"

    for (st, y), msg in KNOWN_GAPS.items():
        notes.append(f"{st} {y}: {msg}")
    for x in report:
        if x["status"] == "NO DATA" and (x["state"], x["year"]) not in KNOWN_GAPS:
            notes.append(f"{x['state']} {x['year']}: ECI's PDF is scanned images with no text layer; "
                         "this election is not in the database")
    write(all_rows, report, notes)


def write(rows, report, notes):
    db = OUT / "state_assemblies.db"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript((Path(__file__).parent / "schema_ae.sql").read_text())
    pcs = {}
    for r in rows:
        k = (r["year"], r["state"], r["pc_no"], r["pc_name"])
        pcs.setdefault(k, (r["year"], r["state"], r["pc_no"], r["pc_name"], r["reserved"], r["seats"],
                           r["electors"], r["voters"], r["valid_votes"],
                           round(100 * r["voters"] / r["electors"], 2) if r["voters"] and r["electors"] else None,
                           r["source"]))
    con.executemany("INSERT OR IGNORE INTO ae_constituencies VALUES (?,?,?,?,?,?,?,?,?,?,?)", list(pcs.values()))
    cols = ["year", "state", "pc_no", "pc_name", "candidate", "sex", "age", "category", "party", "party_raw",
            "party_family", "votes", "postal", "vote_share", "rank", "won", "uncontested", "source"]
    con.executemany(
        f"INSERT INTO ae_candidates (year,state,ac_no,ac_name,{','.join(cols[4:])}) VALUES ({','.join('?' * len(cols))})",
        [tuple(r.get(c) for c in cols) for r in rows])
    con.executemany("INSERT INTO ae_data_notes (note) VALUES (?)", [(n,) for n in notes])
    used = {(r["state"], r["year"], r["party"], r["party_raw"]) for r in rows}
    prow = []
    for st, y, p, raw in used:
        hit = PARTY_NAMES.get((st, y), {}).get(raw)
        if p == "IND":
            hit = ("Independent", "Independent")
        if p == "NOTA":
            hit = ("None of the Above", "NOTA")
        prow.append((st, y, p, raw, hit[0] if hit else None, hit[1] if hit else None))
    con.executemany("INSERT OR IGNORE INTO ae_parties VALUES (?,?,?,?,?,?)", prow)
    con.executemany("INSERT INTO ae_load_report VALUES (?,?,?,?,?,?,?,?,?)",
                    [tuple(x.values()) for x in report])
    con.executescript((Path(__file__).parent / "views_ae.sql").read_text())
    con.commit()
    for name in ["ae_candidates", "ae_constituencies", "ae_summary", "ae_party_trends",
                 "ae_family_trends", "ae_load_report"]:
        cur = con.execute(f"SELECT * FROM {name}")
        with open(OUT / f"{name}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([d[0] for d in cur.description])
            w.writerows(cur)
    con.execute("VACUUM")
    con.close()
    for src in (db, OUT / "ae_candidates.csv"):
        with open(src, "rb") as fi, gzip.open(str(src) + ".gz", "wb", compresslevel=9) as fo:
            shutil.copyfileobj(fi, fo)
    print(f"wrote {len(rows)} assembly rows; report: "
          f"{Counter(x['status'] for x in report)}")


if __name__ == "__main__":
    main()
