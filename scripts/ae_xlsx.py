"""Load ECI assembly 'Detailed Results' spreadsheets (new site, 2023 onwards, and any
xls/xlsx shipped on the old archive) into candidate rows."""
import re

import pandas as pd
import xlrd


def read_any(path):
    if str(path).lower().endswith(".xls"):
        wb = xlrd.open_workbook(path, ignore_workbook_corruption=True, logfile=open("/dev/null", "w"))
        return pd.read_excel(wb, header=None, engine="xlrd")
    return pd.read_excel(path, header=None)


def _find(cols, *alts, exclude=()):
    for keys in alts:
        for i, c in enumerate(cols):
            if all(k in c for k in keys) and not any(x in c for x in exclude):
                return i
    return None


def load_detailed_xlsx(path, year, state_hint):
    df = read_any(path)
    hr = next((i for i in range(min(20, len(df)))
               if df.iloc[i].astype(str).str.upper().str.contains("CANDIDATE").any()), None)
    if hr is None:
        return []
    cols = [re.sub(r"\s+", " ", str(c)).strip().upper() for c in df.iloc[hr]]
    body = df.iloc[hr + 1:]
    ix = {
        "state": _find(cols, ("STATE",)),
        "ac_no": _find(cols, ("AC NO",), ("AC_NO",), ("CONSTITUENCY NO",)),
        "ac_name": _find(cols, ("AC NAME",), ("CONSTITUENCY NAME",), ("AC",), exclude=("NO",)),
        "cand": _find(cols, ("CANDIDATE",)),
        "sex": _find(cols, ("GENDER",), ("SEX",)),
        "age": _find(cols, ("AGE",)),
        "cat": _find(cols, ("CATEGORY",)),
        "party": _find(cols, ("PARTY",), exclude=("SYMBOL", "TYPE")),
        "general": _find(cols, ("GENERAL",)),
        "postal": _find(cols, ("POSTAL",)),
        "total": _find(cols, ("TOTAL",), exclude=("ELECTOR", "%", "OVER", "VALID VOTES +")),
        "electors": _find(cols, ("TOTAL ELECTORS",), exclude=("OVER", "%")),
    }
    if ix["total"] is None or ix["cand"] is None or ix["party"] is None:
        return []
    rows = []
    for _, r in body.iterrows():
        v = pd.to_numeric(r.iloc[ix["total"]], errors="coerce")
        name = r.iloc[ix["cand"]]
        if pd.isna(v) or pd.isna(name) or (ix["ac_name"] is not None and pd.isna(r.iloc[ix["ac_name"]])):
            continue
        party = str(r.iloc[ix["party"]]).strip()
        cand = re.sub(r"^\d+\s+", "", str(name).strip())  # '3 Nota' -> 'Nota'
        if party.upper() == "NOTA" or cand.upper() == "NOTA":
            party, cand = "NOTA", "None of the Above"
        g = lambda k: r.iloc[ix[k]] if ix[k] is not None and pd.notna(r.iloc[ix[k]]) else None  # noqa: E731
        sex = str(g("sex") or "").strip().upper()[:1] or None
        cat = str(g("cat") or "").strip().upper()
        rows.append({
            "year": year, "state": str(g("state") or state_hint).strip(),
            "ac_no": int(float(g("ac_no"))) if g("ac_no") is not None else None,
            "ac_name": str(g("ac_name")).strip(), "candidate": cand,
            "sex": sex if sex in ("M", "F", "T", "O") else None,
            "age": int(float(g("age"))) if g("age") is not None and str(g("age")).replace(".", "").isdigit() else None,
            "category": {"GENERAL": "GEN"}.get(cat, cat) or None,
            "party": party, "votes": int(v),
            "postal": int(float(g("postal"))) if g("postal") is not None else None,
            "electors": int(float(g("electors"))) if g("electors") is not None else None,
        })
    return rows
