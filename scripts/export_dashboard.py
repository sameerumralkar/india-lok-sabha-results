"""Build dashboard/index.html (self-contained) from data/lok_sabha.db."""
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
con = sqlite3.connect(ROOT / "data" / "lok_sabha.db")
con.row_factory = sqlite3.Row
q = lambda sql, *a: [dict(r) for r in con.execute(sql, a)]  # noqa: E731

summary = q("SELECT * FROM election_summary")
years = [r["year"] for r in summary]

# National lineage lines: the four long-run families, plus everyone else.
MAIN = ["Congress", "BJS / BJP", "Janata parivar", "Left"]
fam = defaultdict(lambda: defaultdict(lambda: {"won": 0, "votes": 0}))
for r in q("SELECT year, family, won, votes FROM national_family_trends WHERE family <> 'NOTA'"):
    k = r["family"] if r["family"] in MAIN + ["Independents"] else "Other parties"
    fam[k][r["year"]]["won"] += r["won"]
    fam[k][r["year"]]["votes"] += r["votes"]
valid = {r["year"]: r["v"] for r in q(
    "SELECT cycle AS year, SUM(votes) AS v FROM cand WHERE party <> 'NOTA' GROUP BY cycle")}
seats = {r["year"]: r["seats"] for r in summary}
national = [{"key": k, "won": [fam[k][y]["won"] for y in years],
             "share": [round(100 * fam[k][y]["votes"] / valid[y], 2) for y in years]}
            for k in MAIN + ["Other parties", "Independents"]]

top_parties = defaultdict(list)
for r in q("SELECT year, party, party_name, contested, won, vote_share FROM national_party_trends "
           "WHERE party <> 'NOTA' ORDER BY year, won DESC, votes DESC"):
    if len(top_parties[r["year"]]) < 12:
        top_parties[r["year"]].append(r)

# State view: party level, with Jana Sangh and BJP joined into one line.
def pkey(p):
    return "BJS/BJP" if p in ("BJS", "BJP") else p

names = {}
for r in q("SELECT party, party_name FROM national_party_trends WHERE party_name IS NOT NULL ORDER BY year"):
    names[pkey(r["party"])] = r["party_name"]
names["BJS/BJP"] = "Bharatiya Jana Sangh / Bharatiya Janata Party"

def state_series(rows):
    """rows: dicts with state, year, party, won, seats, votes -> per-state chart series."""
    by_state = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))
    state_seats = defaultdict(dict)
    state_valid = defaultdict(lambda: defaultdict(int))
    for r in rows:
        k = pkey(r["party"])
        by_state[r["state"]][k][r["year"]][0] += r["won"]
        by_state[r["state"]][k][r["year"]][1] += r["votes"]
        state_seats[r["state"]][r["year"]] = r["seats"]
        state_valid[r["state"]][r["year"]] += r["votes"]
    out = {}
    for st, parties in by_state.items():
        yrs = sorted(state_seats[st])
        total_won = {p: sum(v[0] for v in d.values()) for p, d in parties.items()}
        max_share = {p: max(100 * v[1] / state_valid[st][y] for y, v in d.items() if state_valid[st][y])
                     for p, d in parties.items() if any(state_valid[st][y] for y in d)}
        keep = [p for p in parties if p != "IND" and (total_won[p] > 0 or max_share.get(p, 0) >= 8)]
        keep.sort(key=lambda p: (-total_won[p], -max_share.get(p, 0)))
        # INC and BJS/BJP have fixed colours; at most five other named parties get the
        # remaining palette slots, everything else folds into "Others".
        fixed = [p for p in keep if p in ("INC", "BJS/BJP")]
        keep = fixed + [p for p in keep if p not in fixed][:5]
        keep.sort(key=lambda p: (-total_won[p], -max_share.get(p, 0)))
        series = []
        for p in keep + ["IND", "Others"]:
            won, share = [], []
            for y in yrs:
                if p == "Others":
                    w = sum(d[y][0] for pp, d in parties.items() if pp not in keep and pp != "IND" and y in d)
                    v = sum(d[y][1] for pp, d in parties.items() if pp not in keep and pp != "IND" and y in d)
                else:
                    present = p in parties and y in parties[p]
                    w, v = parties[p][y] if present else (0, None)  # None = did not contest
                won.append(w)
                share.append(round(100 * v / state_valid[st][y], 2)
                             if state_valid[st][y] and v is not None else None)
            if any(won) or any(s and s > 0 for s in share):
                series.append({"key": p, "name": names.get(p, "Independents" if p == "IND" else p),
                               "won": won, "share": share})
        out[st] = {"years": yrs, "seats": [state_seats[st][y] for y in yrs], "series": series}
    return out


states = state_series(q("SELECT year, state, party, won, state_seats AS seats, votes FROM state_party_trends "
                        "WHERE party <> 'NOTA'"))

turnout = {r["year"]: r["turnout"] for r in summary}
state_turnout = defaultdict(dict)
for r in q("SELECT year, state, turnout FROM state_summary"):
    state_turnout[r["state"]][r["year"]] = r["turnout"]
for st in states:
    states[st]["turnout"] = [state_turnout[st].get(y) for y in states[st]["years"]]

# ---- State assembly elections
AE_DB = ROOT / "data" / "state_assemblies.db"
if not AE_DB.exists() and Path(str(AE_DB) + ".gz").exists():  # repository copy is gzipped
    import gzip
    import shutil
    with gzip.open(str(AE_DB) + ".gz", "rb") as fi, open(AE_DB, "wb") as fo:
        shutil.copyfileobj(fi, fo)
assembly = {}
if AE_DB.exists():
    con.execute(f"ATTACH DATABASE '{AE_DB}' AS ae")
    for r in q("SELECT party, name FROM ae_parties WHERE name IS NOT NULL"):
        names.setdefault(pkey(r["party"]), r["name"])
    assembly = state_series(q("SELECT year, state, party, won, seats, votes FROM ae_party_trends "
                              "WHERE party <> 'NOTA'"))
    for r in q("SELECT state, year, turnout, candidates, largest_party FROM ae_summary"):
        a_ = assembly.get(r["state"])
        if a_:
            a_.setdefault("turnout", [None] * len(a_["years"]))
            a_.setdefault("candidates", [None] * len(a_["years"]))
            i = a_["years"].index(r["year"])
            a_["turnout"][i] = r["turnout"]
            a_["candidates"][i] = r["candidates"]
    ae_notes = [r["note"] for r in q("SELECT note FROM ae_data_notes")]
    ae_report = q("SELECT * FROM ae_load_report ORDER BY state, year")
else:
    ae_notes, ae_report = [], []

# ---- Party lineage (splits and mergers since 1885)
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import lineage  # noqa: E402
lin = lineage.load()
lin["lok_sabha"] = lineage.lok_sabha_record(con, lin)
lin["seats"] = seats

data = {"lineage": lin, "years": years, "summary": summary, "national": national, "seats": seats,
        "top": top_parties, "states": states, "turnout": turnout,
        "notes": [r["note"] for r in q("SELECT note FROM data_notes")],
        "assembly": assembly, "ae_notes": ae_notes, "ae_report": ae_report}

tpl = (ROOT / "scripts" / "dashboard_template.html").read_text()
out = ROOT / "dashboard" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(tpl.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":"))))
print("wrote", out, f"{out.stat().st_size/1e3:.0f} kB")
