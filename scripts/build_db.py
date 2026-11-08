"""Build the Lok Sabha results database (SQLite + CSV) from ECI sources.

  1951-2009: PDF statistical reports (text cached in text/<year>/)
  2014, 2019, 2024: ECI 'Constituency Wise Detailed Result' spreadsheets

Usage: python build_db.py   (run from the project root)
"""
import csv
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import xlrd

sys.path.insert(0, str(Path(__file__).parent))
from parse_pdf_results import parse_2004_summaries, parse_year  # noqa: E402
from reference import (CYCLE, EXTRA_PARTY_NAMES, LOK_SABHA_NO, PARTY_ALIASES, PARTY_FAMILY,  # noqa: E402
                       canonical_state)

ROOT = Path(__file__).resolve().parent.parent
RAW, TEXT, OUT = ROOT / "raw" / "eci", ROOT / "text", ROOT / "data"
PDF_YEARS = [1951, 1957, 1962, 1967, 1971, 1977, 1980, 1984, 1985, 1989, 1991,
             1992, 1996, 1998, 1999, 2004, 2009]
XLS = {
    2014: (RAW / "2014" / "Constituency wise detailed result.xlsx",
           "https://old.eci.gov.in/files/file/2785-constituency-wise-detailed-result/"),
    2019: (RAW / "2019" / "33. Constituency Wise Detailed Result.xls",
           "https://old.eci.gov.in/files/file/13539-33-constituency-wise-detailed-result/"),
    2024: (RAW / "2024" / "33-Constituency-Wise-Detailed-Result.xls",
           "https://www.eci.gov.in/eci-backend/public/all_files/GE-2024-statistical-report/"
           "33-Constituency-Wise-Detailed-Result.xls"),
}
PDF_SOURCE = {
    1951: "4111-general-election-1951-vol-i-ii", 1957: "4112-general-election-1957-vol-i-ii",
    1962: "4113-general-election-1962-vol-i-ii", 1967: "4114-general-election-1967-vol-i-ii",
    1971: "4115-general-election-1971-vol-i-ii", 1977: "4116-general-election-1977-vol-i-ii",
    1980: "4117-general-election-1980-vol-i-ii", 1984: "4118-general-election-1984-vol-i-ii",
    1985: "4119-general-election-1985-vol-i-ii", 1989: "4120-general-election-1989-vol-i-ii",
    1991: "4121-general-election-1991-vol-i-ii", 1992: "4122-general-election-1992-vol-i-ii",
    1996: "4123-general-election-1996-vol-i-ii", 1998: "4124-general-election-1998-vol-i-ii",
    1999: "4125-general-election-1999-vol-i-ii-iii", 2004: "4126-general-election-2004-vol-i-ii-iii",
    2009: "2857-constituency-wise-detailed-result",
}


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


# ---------------------------------------------------------------- PDF years
def mark_winners(rows, successful_lines):
    """Single-member seats: top vote-getter. Multi-member seats (1951/57):
    match against ECI's List of Successful Candidates, falling back to top-k."""
    by_pc = defaultdict(list)
    for r in rows:
        by_pc[(r["state"], r["pc_no"], r["pc_name"])].append(r)
    succ = [" " + re.sub(r"[^A-Z0-9() ]", "", x.upper()) for x in successful_lines]

    def key_of(c):
        return " " + re.sub(r"[^A-Z0-9() ]", "", f"{c['candidate']} {c['party']}".upper())
    flagged = []
    for key, cands in by_pc.items():
        k = cands[0]["seats"]
        for c in cands:
            c["won"] = 0
        if k == 1:
            cands[0]["won"] = 1  # rows are already sorted by votes
            continue
        hits = [c for c in cands if any(line.endswith(key_of(c)) for line in succ)]
        if len(hits) != k:
            flagged.append((key, len(hits), k))
            hits = cands[:k]
        for c in hits:
            c["won"] = 1
    return flagged


def load_party_names(year):
    """abbr -> (full name, type) from the 'List of Participating Political Parties'."""
    names = {}
    ptype = None
    for f in sorted((TEXT / str(year)).glob("*.txt")):
        for page in f.read_text().split("\f"):
            if "LIST OF PARTICIPATING POLITICAL PARTIES" not in page.upper():
                continue
            for line in page.split("\n"):
                s = line.strip()
                u = s.upper()
                if u.startswith("NATIONAL PARTIES"):
                    ptype = "National"
                elif "STATE PARTIES" in u or u.startswith("STATE PARTY"):
                    ptype = "State"
                elif "REGISTERED" in u and "PARTIES" in u:
                    ptype = "Registered (unrecognised)"
                elif u.startswith("INDEPENDENT"):
                    ptype = "Independent"
                m = re.match(r"^\d+\s*\.\s*(\S+)\s+(.+)$", s)
                if m and ptype:
                    names.setdefault(m.group(1), (m.group(2).strip().title(), ptype))
    return names


# ---------------------------------------------------------------- XLS years
def read_sheet(path):
    if path.suffix == ".xls":
        wb = xlrd.open_workbook(path, ignore_workbook_corruption=True,
                                logfile=open("/dev/null", "w"))
        return pd.read_excel(wb, header=None, engine="xlrd")
    return pd.read_excel(path, header=None)


def load_xls_year(year, path):
    df = read_sheet(path)
    hdr_row = df.index[df[0].astype(str).str.strip().str.upper() == "STATE NAME"][0]
    cols = [str(c).strip().upper().replace("\n", " ") for c in df.iloc[hdr_row]]
    df = df.iloc[hdr_row + 1:].copy()
    df.columns = cols

    def col(*keys, exact=False):
        for i, c in enumerate(cols):
            if (c == keys[0]) if exact else all(k in c for k in keys):
                return df.iloc[:, i]
        return None

    total = col("TOTAL") if year != 2024 else df.iloc[:, 12]
    out = pd.DataFrame({
        "state": col("STATE"), "pc_name": col("PC"), "candidate": col("CANDIDATE"),
        "sex": col("SEX") if col("SEX") is not None else col("GENDER"),
        "age": col("AGE"), "category": col("CATEGORY"), "party": col("PARTY NAME"),
        "general": col("GENERAL"), "postal": col("POSTAL"), "votes": total,
        "electors": col("TOTAL ELECTORS", exact=True),
        "pct_polled": col("OVER TOTAL VOTES POLLED"),
        "polled": next((df.iloc[:, i] for i, c in enumerate(cols)
                        if c.startswith("TOTAL VOTES POLLED")), None),
    })
    out = out[pd.to_numeric(out["votes"], errors="coerce").notna() & out["pc_name"].notna()]
    rows = []
    pc_seq = defaultdict(dict)
    for (state, pc), g in out.groupby(["state", "pc_name"], sort=False):
        state = str(state).strip()
        pc_no = pc_seq[state].setdefault(pc, len(pc_seq[state]) + 1)
        g = g.assign(votes=g["votes"].astype(int)).sort_values("votes", ascending=False)
        valid = int(g["votes"].sum())
        top = g.iloc[0]
        if pd.notna(top["polled"]):
            voters = int(top["polled"])
        elif pd.notna(top["pct_polled"]) and float(top["pct_polled"]) > 0:
            voters = round(int(top["votes"]) * 100 / float(top["pct_polled"]))
        else:
            voters = None
        for rank, (_, r) in enumerate(g.iterrows(), 1):
            party = str(r["party"]).strip()
            sex = str(r["sex"]).strip().upper()[:1] if pd.notna(r["sex"]) else None
            rows.append({
                "year": year, "state": state, "pc_no": pc_no, "pc_name": str(pc).strip(),
                "seats": 1, "reserved": None, "candidate": str(r["candidate"]).strip(),
                "sex": sex if sex in ("M", "F", "T", "O") else None,
                "age": int(r["age"]) if pd.notna(r["age"]) and str(r["age"]).strip().isdigit() else None,
                "category": str(r["category"]).strip() if pd.notna(r["category"]) else None,
                "party": party, "votes": int(r["votes"]),
                "postal": int(r["postal"]) if pd.notna(r["postal"]) else None,
                "rank": rank, "electors": int(r["electors"]) if pd.notna(r["electors"]) else None,
                "voters": voters, "valid_votes": valid, "uncontested": 0,
                "won": int(rank == 1 and party != "NOTA"),
            })
    # Surat 2024 was won unopposed: ECI lists no poll there, add it explicitly.
    if year == 2024 and not any(r["pc_name"].upper() == "SURAT" for r in rows):
        rows.append({"year": 2024, "state": "Gujarat", "pc_no": 24, "pc_name": "Surat",
                     "seats": 1, "reserved": "GEN", "candidate": "MUKESHKUMAR CHANDRAKAANT DALAL",
                     "sex": "M", "age": None, "category": "GEN", "party": "BJP", "votes": 0,
                     "postal": None, "rank": 1, "electors": None, "voters": None,
                     "valid_votes": 0, "uncontested": 1, "won": 1})
    # Reservation status: in an SC/ST seat every candidate is from that category.
    by_pc = defaultdict(list)
    for r in rows:
        by_pc[(r["state"], r["pc_name"])].append(r)
    for cands in by_pc.values():
        cats = {c["category"] for c in cands if c["party"] != "NOTA"}
        res = cats.pop() if len(cats) == 1 else "GEN"
        for c in cands:
            c["reserved"] = res if res in ("SC", "ST") else "GEN"
    return rows


# ---------------------------------------------------------------- build
def main():
    OUT.mkdir(exist_ok=True)
    all_rows, party_names, notes = [], {}, []
    for y in PDF_YEARS:
        rows, succ = parse_year(TEXT / str(y), y)
        if y == 2004:
            summ = parse_2004_summaries((TEXT / "2004" / "2004 (Vol II).txt").read_text())
            for r in rows:
                hit = summ.get((r["state"].upper(), r["pc_no"]))
                if hit:
                    r["electors"], r["voters"] = hit
        flagged = mark_winners(rows, succ)
        for f in flagged:
            notes.append(f"{y}: multi-member seat {f[0]}: name match against ECI's list of "
                         f"successful candidates was ambiguous ({f[1]} of {f[2]}); used the top "
                         f"{f[2]} vote-getters, which agree with that list on manual check")
        src = "https://old.eci.gov.in/files/file/" + PDF_SOURCE[y] + "/"
        for r in rows:
            r.setdefault("age", None)
            r.setdefault("category", None)
            r.setdefault("postal", None)
            r["source"] = src
        all_rows += rows
        party_names[y] = load_party_names(y)
        print(f"{y}: {len(rows)} candidates", flush=True)
    for y, (path, src) in XLS.items():
        rows = load_xls_year(y, path)
        for r in rows:
            r["source"] = src
        if y == 2014:
            # ECI's 2014 spreadsheet omits Odisha and Chhattisgarh; take them from its PDF.
            have = {canonical_state(r["state"], y) for r in rows}
            pdf_rows, _ = parse_year(TEXT / "2014", 2014)
            extra = [r for r in pdf_rows if canonical_state(r["state"], y) not in have]
            for r in extra:
                r["won"] = int(r["rank"] == 1)
                r["source"] = "https://old.eci.gov.in/files/file/2785-constituency-wise-detailed-result/ (PDF)"
            notes.append(f"2014: ECI spreadsheet lacks {sorted({r['state'] for r in extra})}; "
                         f"{len(extra)} rows taken from the 2014 PDF of the same report")
            rows += extra
        all_rows += rows
        print(f"{y}: {len(rows)} candidates", flush=True)
    party_names.update(load_recent_party_names())

    # ECI statistical reports define 'valid votes' without NOTA (2014 onwards);
    # vote shares use that denominator. NOTA's own share is over valid + NOTA.
    pc_valid = defaultdict(int)
    for r in all_rows:
        if r["party"] != "NOTA":
            pc_valid[(r["year"], r["state"], r["pc_no"], r["pc_name"])] += r["votes"]
    for r in all_rows:
        if r["year"] >= 2014:
            r["valid_votes"] = pc_valid[(r["year"], r["state"], r["pc_no"], r["pc_name"])]

    # normalise
    for r in all_rows:
        r["state_raw"] = r["state"]
        r["state"] = canonical_state(r["state"], r["year"])
        r["party_raw"] = r["party"]
        r["party"] = PARTY_ALIASES.get((r["year"], r["party"]), PARTY_ALIASES.get(r["party"], r["party"]))
        r["party_family"] = PARTY_FAMILY.get((r["year"], r["party"]), PARTY_FAMILY.get(r["party"], r["party"]))
        if r["reserved"] is None:
            m = re.search(r"\((SC|ST)\)", r["pc_name"])
            r["reserved"] = m.group(1) if m else "GEN"
        denom = r["valid_votes"] + (r["votes"] if r["party"] == "NOTA" else 0)
        r["vote_share"] = round(100 * r["votes"] / denom, 4) if denom else None

    write_db(all_rows, party_names, notes)


def load_recent_party_names():
    """2024 'List of Political Parties Participated': Sr, type (N/S/U), abbr, symbol, name."""
    df = pd.read_excel(RAW / "2024" / "3-List-Of-Political-Parties-Participated.xlsx", header=None)
    types = {"N": "National", "S": "State", "U": "Registered (unrecognised)"}
    names = {}
    for _, row in df.iterrows():
        if str(row[0]).strip().isdigit() and pd.notna(row[2]) and pd.notna(row[4]):
            names[str(row[2]).strip()] = (str(row[4]).strip(), types.get(str(row[1]).strip()))
    return {2024: names}


def write_db(rows, party_names, notes):
    db = OUT / "lok_sabha.db"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(Path(__file__).with_name("schema.sql").read_text())

    # parties: year-specific names; fall back to the nearest year that lists the abbr
    all_years = sorted({r["year"] for r in rows})
    used = sorted({(r["year"], r["party"], r["party_raw"]) for r in rows})
    party_rows = []
    for y, p, raw in used:
        name, ptype = None, None
        for yy in sorted(party_names, key=lambda k: abs(k - y)):
            hit = party_names[yy].get(raw) or party_names[yy].get(p)
            if hit:
                name, ptype = hit
                break
        if name is None and p in EXTRA_PARTY_NAMES:
            name = EXTRA_PARTY_NAMES[p]
        if p == "IND":
            name, ptype = "Independent", "Independent"
        if p == "NOTA":
            name, ptype = "None of the Above", "NOTA"
        party_rows.append((y, p, raw, name, ptype, PARTY_FAMILY.get((y, p), PARTY_FAMILY.get(p, p))))
    con.executemany("INSERT OR IGNORE INTO parties VALUES (?,?,?,?,?,?)", party_rows)

    con.executemany(
        "INSERT INTO elections (year, lok_sabha, cycle) VALUES (?, ?, ?)",
        [(y, LOK_SABHA_NO[y], CYCLE.get(y, y)) for y in all_years])

    pcs = {}
    for r in rows:
        k = (r["year"], r["state"], r["pc_no"], r["pc_name"])
        if k not in pcs:
            pcs[k] = (r["year"], r["state"], r["state_raw"], r["pc_no"], r["pc_name"],
                      r["reserved"], r["seats"], r["electors"], r["voters"], r["valid_votes"],
                      round(100 * r["voters"] / r["electors"], 2) if r["voters"] and r["electors"] else None,
                      r["source"])
    con.executemany("INSERT INTO constituencies VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", list(pcs.values()))

    cols = ["year", "state", "pc_no", "pc_name", "candidate", "sex", "age", "category", "party",
            "party_raw", "party_family", "votes", "postal", "vote_share", "rank", "won",
            "uncontested", "source"]
    con.executemany(f"INSERT INTO candidates ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(r.get(c) for c in cols) for r in rows])
    con.executemany("INSERT INTO data_notes (note) VALUES (?)", [(n,) for n in notes])
    con.executescript(Path(__file__).with_name("views.sql").read_text())
    con.commit()

    # CSV exports
    for name in ["candidates", "constituencies", "parties", "national_party_trends",
                 "state_party_trends", "national_family_trends", "state_family_trends",
                 "election_summary", "state_summary"]:
        cur = con.execute(f"SELECT * FROM {name}")
        with open(OUT / f"{name}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([d[0] for d in cur.description])
            w.writerows(cur)
    con.close()
    print("wrote", db)


if __name__ == "__main__":
    main()
