"""Party splits and mergers, 1885 to date (data/party_lineage.json).

Usage: python scripts/lineage.py   -> validates the file, writes the lineage_* tables
into data/lok_sabha.db and data/lineage_*.csv.
"""
import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "party_lineage.json"
TYPES = {"split", "merger", "rename", "succession", "founded"}
NOW = 2026


def load():
    return json.loads(SRC.read_text())


def validate(d):
    """Return a list of problems (empty when the file is consistent)."""
    bad = []
    fams = {f["key"] for f in d["families"]}
    P = {}
    for p in d["parties"]:
        if p["id"] in P:
            bad.append(f"duplicate id {p['id']}")
        P[p["id"]] = p
        if p["family"] not in fams:
            bad.append(f"{p['id']}: unknown family {p['family']}")
        end = p["end"] or NOW
        if not 1885 <= p["start"] <= end <= NOW:
            bad.append(f"{p['id']}: bad years {p['start']}-{p['end']}")
        if p["end"] and not p.get("end_how"):
            bad.append(f"{p['id']}: ended without end_how")
        for code, a, b in p.get("eci", []):
            if not (a <= b and p["start"] <= a + 1 and b <= end + 1):  # +1: deferred polls
                bad.append(f"{p['id']}: ECI window {code} {a}-{b} outside {p['start']}-{end}")
    for e in d["events"]:
        tag = f"{e['year']} {e['type']} {e['from']}->{e['to']}"
        if e["type"] not in TYPES:
            bad.append(f"{tag}: unknown type")
        for i in e["from"] + e["to"]:
            if i not in P:
                bad.append(f"{tag}: unknown party {i}")
        if any(i not in P for i in e["from"] + e["to"]):
            continue
        for i in e["from"]:  # the source must exist when the event happens
            if not P[i]["start"] <= e["year"] <= (P[i]["end"] or NOW):
                bad.append(f"{tag}: {i} not active in {e['year']}")
        if e["type"] in ("split", "founded", "succession") or (e["type"] == "rename" and e["from"] != e["to"]):
            for i in e["to"]:
                if i not in e["from"] and P[i]["start"] != e["year"]:
                    bad.append(f"{tag}: {i} starts {P[i]['start']}, not {e['year']}")
        if e["type"] == "merger":
            for i in e["to"]:
                if not P[i]["start"] <= e["year"] <= (P[i]["end"] or NOW):
                    bad.append(f"{tag}: target {i} not active")
        if e["type"] in ("merger", "succession", "rename"):
            for i in e["from"]:
                # a source that ends here must end in this year; PSP 1964 and JNP 1988 carry on
                if i not in e["to"] and P[i]["end"] not in (e["year"], None) and P[i]["end"] < e["year"]:
                    bad.append(f"{tag}: {i} ended before the event")
    return bad


def lok_sabha_record(con, d):
    """Seats and vote share in each Lok Sabha election, per lineage party, via its ECI codes."""
    rows = con.execute("SELECT year, party, won, vote_share FROM national_party_trends").fetchall()
    by = {}
    for y, code, won, share in rows:
        by.setdefault(code, {})[y] = (won, share)
    out = {}
    for p in d["parties"]:
        rec = {}
        for code, a, b in p.get("eci", []):
            for y, (won, share) in by.get(code, {}).items():
                if a <= y <= b:
                    w, s = rec.get(y, (0, 0.0))
                    rec[y] = (w + won, round(s + (share or 0), 2))
        if rec:
            out[p["id"]] = {str(y): list(v) for y, v in sorted(rec.items())}
    return out


def write(con, d=None):
    d = d or load()
    con.executescript("""
        DROP TABLE IF EXISTS lineage_parties; DROP TABLE IF EXISTS lineage_events;
        DROP TABLE IF EXISTS lineage_eci_codes;
        CREATE TABLE lineage_parties (id TEXT PRIMARY KEY, name TEXT, family TEXT, start_year INT,
            end_year INT, end_how TEXT, note TEXT);
        CREATE TABLE lineage_events (year INT, type TEXT, from_ids TEXT, to_ids TEXT, text TEXT);
        CREATE TABLE lineage_eci_codes (id TEXT, eci_code TEXT, from_year INT, to_year INT);
    """)
    con.executemany("INSERT INTO lineage_parties VALUES (?,?,?,?,?,?,?)",
                    [(p["id"], p["name"], p["family"], p["start"], p["end"], p.get("end_how"), p.get("note"))
                     for p in d["parties"]])
    con.executemany("INSERT INTO lineage_events VALUES (?,?,?,?,?)",
                    [(e["year"], e["type"], ",".join(e["from"]), ",".join(e["to"]), e["text"])
                     for e in sorted(d["events"], key=lambda e: e["year"])])
    con.executemany("INSERT INTO lineage_eci_codes VALUES (?,?,?,?)",
                    [(p["id"], c, a, b) for p in d["parties"] for c, a, b in p.get("eci", [])])
    con.commit()
    for t in ("lineage_parties", "lineage_events", "lineage_eci_codes"):
        cur = con.execute(f"SELECT * FROM {t}")
        with open(ROOT / "data" / f"{t}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([c[0] for c in cur.description])
            w.writerows(cur)


if __name__ == "__main__":
    data = load()
    problems = validate(data)
    for b in problems:
        print("!", b)
    if problems:
        raise SystemExit(1)
    write(sqlite3.connect(ROOT / "data" / "lok_sabha.db"), data)
    print(f"{len(data['parties'])} parties, {len(data['events'])} events written")
