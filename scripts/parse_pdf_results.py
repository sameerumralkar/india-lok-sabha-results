"""Parse the 'DETAILED RESULTS' section of ECI Lok Sabha statistical reports
(text cached by pdf_to_text.py) into candidate-level rows.

Handles the layouts used from 1951 to 2009:
  Constituency 7 NOWGONG NUMBER OF SEATS 1                 (1951/57)
  Constituency : 8 . RAJAHMUNDRY                           (1962+)
  1 . BAROOAH, DEV KANTA INC 79673 45.83%                  (no sex column)
  1. D.S. RAJU M INC 227154 57.32%                         (with sex column)
  ELECTORS : 342855 VOTERS : 173832 POLL PERCENTAGE : 50.70% VALID VOTES 173832
"""
import re
from pathlib import Path

CONST_RE = re.compile(
    r"^Constituency\s*:?\s*(\d+)\s*\.?\s*-?\s*(.+?)(?:\s+NUMBER OF SEATS\s*:?\s*(\d+))?\s*$", re.I)
CAND_RE = re.compile(
    r"^(\d+)\s*\.\s*(.+?)\s+(?:(M|F|W|O|MALE|FEMALE|THIRD|TG)\s+)?"
    r"(?:(GEN|SC|ST)\s+)?(?:(\d{2,3})\s+)?(\S+)\s+(\d+)\s+(-?[\d.]+\s*%?|#Num!|-)\s*$")
FOOT_RE = re.compile(
    r"ELECTORS\s*:?\s*(\d+).*?VOTERS\s*:?\s*(\d+).*?POLL PERCENTAGE\s*:?\s*([\d.]+)\s*%"
    r".*?VALID VOTES\s*:?\s*(\d+)", re.I)
# 2004/2009 layout: N[.] NAME SEX AGE CAT PARTY GENERAL POSTAL TOTAL [% %]
CAND2_RE = re.compile(
    r"^(\d+)\s*\.?\s+(.+?)\s+(M|F|O|TG)\s+(?:(\d{2,3})\s+)?(GEN|SC|ST|BL|SNGH|SANGHA|SG|OBC)\s+(\S+)\s+"
    r"(\d+)\s+(\d+|\d[\d.]*E\+?\d*)\s+(\d+)(?:\s+[\d.]+\s+([\d.]+))?\s*$")  # postal may print as '1E+
# 2014 PDF adds a free-text Symbol column between party and votes
CAND3_RE = re.compile(
    r"^(\d+)\s+(.+?)\s+(M|F|O|TG)\s+(\d{2,3})\s+(GEN|SC|ST|BL|SNGH|SANGHA|SG|OBC)\s+(\S+)\s+.*?\s*"
    r"(\d+)\s+(\d+)\s+(\d+)\s+(?:[\d.]+\s+)?([\d.]+)\s*$")
NOTA_RE = re.compile(r"^(\d+)\s+None of the Above\s+NOTA\s+NOTA\s+(\d+)\s+(\d+)\s+(\d+)\s+(?:[\d.]+\s+)?([\d.]+)", re.I)
TOTAL_RE = re.compile(r"^(?:TURNOUT\s+)?TOTAL\s*:\s*(\d+)\s+(\d+)\s+(\d+)")
# '( Total Electors N )'; the PDF sometimes shifts the paren one letter left: 'Island(s Total Electors N )'
ELECTORS_IN_HEADER = re.compile(r"(?:\((\w?)\s*Total Electors\s*(\d+)\s*\)|()\s*TOTAL ELECTORS\s*:\s*(\d+)\s*$)", re.I)
# later layout: '1 . NAME M 54 GEN SDF Uncontested'
UNCONTESTED2_RE = re.compile(r"^(\d+)\s*\.?\s*(.+?)\s+(M|F|W|O)\s+(?:\d{2,3}\s+)?(?:[A-Z]{2,6}\s+)?(\S+)\s+Uncontested\s*$", re.I)
UNCONTESTED_RE = re.compile(r"^(\d+)\s*\.\s*(.+?)\s+(\S+)\s+RETURNED\s+UN", re.I)
PAGE_NOISE = re.compile(
    r"^(rpt|GENERAL ELECTIONS?\b|Election Commission|No\.\s*CANDIDATE|DETAILED RESULTS|Page \d|\d+$|@@PAGE"
    r"|PART-|\d+\s*-\s*CONSTITUENCY WISE|% of votes|Over total|el[e]?ctors in|constituency constituency"
    r"|GENERAL POSTAL|SL NO|VALID VOTES POLLED|NAME\s+GENERAL|elctors in|Votes Secured)", re.I)
RESERVED_RE = re.compile(r"\((SC|ST)\)\s*$")


def is_state_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 45 or any(ch.isdigit() for ch in s):
        return False
    if s.upper().startswith(("ELECTORS", "CONSTITUENCY", "NO.", "TOTAL")):
        return False
    return bool(re.fullmatch(r"[A-Za-z &.,'()\-]+", s))


def _join_split_headers(lines):
    """Some pages print 'NN . NAME' on one line and a bare 'Constituency :' on the next."""
    out, i = [], 0
    while i < len(lines):
        cur = lines[i].strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        bare = re.fullmatch(r"Constituency\s*:?", nxt, re.I)
        if bare and re.match(r"^\d+\s*\.\s*[A-Za-z]", cur) and not CAND_RE.match(cur):
            out.append("Constituency : " + cur)
            i += 2
            continue
        if re.fullmatch(r"Constituency\s*:?", cur, re.I) and re.match(r"^\d+\s*\.\s*[A-Za-z]", nxt) \
                and not CAND_RE.match(nxt):
            out.append("Constituency : " + nxt)
            i += 2
            continue
        out.append(lines[i])
        i += 1
    return out


def detailed_pages(text: str):
    """Yield the lines of pages that belong to the DETAILED RESULTS section."""
    for page in text.split("\f"):
        head = "\n".join(page.split("\n")[:5]).upper()
        if ("DETAILED RESULTS" in head and "CONTENTS" not in head) or "SL NO CANDIDATE" in page.upper() \
                or re.search(r"^No\.\s*CANDIDATES?\s+(SEX\s+)?(AGE\s+CATEGORY\s+)?PARTY", page, re.M | re.I):
            yield _join_split_headers(page.split("\n"))


def parse_text(text: str, year: int, fixed_state: str = None):
    """fixed_state: assembly reports cover one state and print no state headers."""
    rows, consts = [], []
    state = fixed_state
    cur = None
    pending_name = None  # candidate name wrapped onto two lines

    def close():
        nonlocal cur
        if cur and cur["cands"]:
            consts.append(cur)
        cur = None

    for lines in detailed_pages(text):
        for raw in lines:
            line = raw.strip()
            if not line or PAGE_NOISE.match(line):
                continue
            m = CONST_RE.match(line)
            if m and cur and not cur["foot"] and cur["pc_no"] == int(m.group(1)):
                continue  # header repeated at the top of a continuation page
            if m:
                close()
                name = m.group(2).strip(" .-")
                em = ELECTORS_IN_HEADER.search(name)
                name = ELECTORS_IN_HEADER.sub(lambda mm: mm.group(1) or "", name).strip(" .-")
                cur = {"state": state, "pc_no": int(m.group(1)), "pc_name": name,
                       "seats": int(m.group(3) or 1), "cands": [], "foot": None,
                       "electors": int(em.group(2) or em.group(4)) if em else None}
                pending_name = None
                continue
            m = FOOT_RE.search(line)
            if m and cur:
                cur["foot"] = tuple(int(m.group(i)) for i in (1, 2, 4))
                continue
            # 2005-07 assembly reports: the AC is a bare 'NN. NAME' line (no 'Constituency')
            bare = fixed_state and (cur is None or cur["foot"]) and \
                re.match(r"^(\d+)\s*\.\s*([A-Za-z][^\d%]*)$", line)
            if bare:
                close()
                cur = {"state": state, "pc_no": int(bare.group(1)), "pc_name": bare.group(2).strip(" .-"),
                       "seats": 1, "cands": [], "foot": None, "electors": None}
                pending_name = None
                continue
            m = TOTAL_RE.match(line)
            if m and cur:
                cur["foot"] = (cur.get("electors"), None, int(m.group(3)))
                continue
            m = CAND2_RE.match(line)
            if m and cur is not None and not cur["foot"]:
                cur["cands"].append({"name": m.group(2).strip(), "sex": m.group(3)[:1],
                                     "party": m.group(6), "votes": int(m.group(9)),
                                     "postal": int(m.group(8)) if m.group(8).isdigit() else None,
                                     "age": m.group(4), "category": m.group(5),
                                     "pct_polled": float(m.group(10)) if m.group(10) else None})
                continue
            m = NOTA_RE.match(line)
            if m and cur is not None and not cur["foot"]:
                cur["cands"].append({"name": "None of the Above", "sex": None, "party": "NOTA",
                                     "votes": int(m.group(4)), "postal": int(m.group(3)),
                                     "pct_polled": float(m.group(5))})
                continue
            m = CAND3_RE.match(line)
            if m and cur is not None and not cur["foot"]:
                cur["cands"].append({"name": m.group(2).strip(), "sex": m.group(3)[:1],
                                     "party": m.group(6), "votes": int(m.group(9)),
                                     "postal": int(m.group(8)), "age": m.group(4),
                                     "category": m.group(5), "pct_polled": float(m.group(10))})
                continue
            m = UNCONTESTED2_RE.match(line)
            if m and cur is not None and not cur["foot"]:
                cur["cands"].append({"name": m.group(2).strip(), "sex": {"W": "F"}.get(m.group(3).upper(), m.group(3).upper()),
                                     "party": m.group(4), "votes": 0, "returned": True})
                continue
            m = UNCONTESTED_RE.match(line)
            if m and cur is not None:
                cur["cands"].append({"name": m.group(2).strip(), "sex": None,
                                     "party": m.group(3), "votes": 0, "returned": True})
                continue
            m = CAND_RE.match(line)
            if m and cur is not None:
                name = m.group(2).strip()
                if pending_name:
                    name = f"{pending_name} {name}"
                    pending_name = None
                sex = {"W": "F"}.get((m.group(3) or "")[:1], (m.group(3) or "")[:1]) or None
                cur["cands"].append({"name": name, "sex": sex, "party": m.group(6),
                                     "votes": int(m.group(7))})
                continue
            if cur is None or (cur and cur["foot"]):
                if fixed_state is None and is_state_line(line):
                    close()
                    state = line.title() if line.isupper() else line
                    continue
            # A line that is none of the above inside a constituency block is
            # usually the first half of a wrapped candidate name.
            if cur is not None and not cur["foot"] and re.match(r"^\d+\s*\.\s*\S", line):
                pending_name = re.sub(r"^\d+\s*\.\s*", "", line)
            elif state and line.upper() == state.upper():
                continue  # state name repeated at the top of a continuation page
            elif cur is not None and not cur["foot"] and cur["cands"] and not re.search(r"\d", line):
                # Wrapped name tails are UPPER CASE; Title-case words are wrapped party
                # symbols ('KUMAR Rickshaw' -> keep 'KUMAR').
                tail = []
                for tok in line.split():
                    if not (tok.isupper() or not any(ch.isalpha() for ch in tok)):
                        break
                    tail.append(tok)
                if tail and any(ch.isalpha() for ch in "".join(tail)):
                    cur["cands"][-1]["name"] += " " + " ".join(tail)
            elif cur is not None and not cur["foot"] and cur["cands"] == [] and not line[0].isdigit():
                cur["pc_name"] += " " + line  # wrapped constituency name
    close()

    for c in consts:
        if c["state"] is None:
            continue
        valid = c["foot"][2] if c["foot"] else sum(x["votes"] for x in c["cands"])
        # 'RETURNED UNCONTESTED' candidates come first even though they show 0 votes
        ordered = sorted(c["cands"], key=lambda x: (not x.get("returned"), -x["votes"]))
        voters = c["foot"][1] if c["foot"] else None
        if voters is None and ordered and ordered[0].get("pct_polled"):
            # 2009 prints only '% over total votes polled'; back out the votes polled
            voters = round(ordered[0]["votes"] * 100 / ordered[0]["pct_polled"])
        for rank, cand in enumerate(ordered, 1):
            rows.append({
                "year": year, "state": c["state"], "pc_no": c["pc_no"],
                "pc_name": c["pc_name"], "seats": c["seats"],
                "reserved": (RESERVED_RE.search(c["pc_name"]).group(1)
                             if RESERVED_RE.search(c["pc_name"]) else "GEN"),
                "candidate": cand["name"], "sex": cand["sex"], "party": cand["party"],
                "votes": cand["votes"], "rank": rank,
                "electors": c["foot"][0] if c["foot"] else None,
                "voters": voters, "age": int(cand["age"]) if cand.get("age") else None,
                "category": cand.get("category"), "postal": cand.get("postal"),
                "valid_votes": valid,
                "uncontested": int(bool(cand.get("returned"))),
            })
    return rows


def winners_from_successful_list(text: str):
    """Return the set of 'NAME PARTY' strings in the LIST OF SUCCESSFUL CANDIDATES."""
    out = set()
    for page in text.split("\f"):
        if "LIST OF SUCCESSFUL CANDIDATES" not in page.upper():
            continue
        for line in page.split("\n"):
            s = re.sub(r"\s+", " ", line.strip().upper())
            if s:
                out.add(s)
    return out


def parse_year(text_dir: Path, year: int):
    files = sorted(text_dir.glob("*.txt"))
    rows, succ = [], set()
    for f in files:
        t = f.read_text()
        succ |= winners_from_successful_list(t)
        r = parse_text(t, year)
        if len(r) > len(rows):  # the volume with the detailed results
            rows = r
    return rows, succ


def parse_2004_summaries(text: str):
    """Electors and voters per PC from the 2004 Vol II 'Constituency Data - Summary'."""
    out = {}
    for page in text.split("\f"):
        if "CONSTITUENCY DATA - SUMMARY" not in page.upper():
            continue
        st = re.search(r"STATE/UT\s*:\s*(.+?)\s+CODE", page)
        pc = re.search(r"CONSTITUENCY\s*:\s*(.+?)\s+NO\s*:\s*(\d+)", page)
        el = re.search(r"II\. ELECTORS.*?3\.TOTAL\s+\d+\s+\d+\s+(\d+)", page, re.S)
        vo = re.search(r"III\. VOTERS.*?4\.TOTAL\s+(\d+)", page, re.S)
        if st and pc and el:
            out[(st.group(1).strip().upper(), int(pc.group(2)))] = (
                int(el.group(1)), int(vo.group(1)) if vo else None)
    return out
