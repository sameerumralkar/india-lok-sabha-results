# India election results database: Lok Sabha 1951–2024 and state assemblies 1951–2026

[![CI](https://github.com/sameerumralkar/india-lok-sabha-results/actions/workflows/ci.yml/badge.svg)](https://github.com/sameerumralkar/india-lok-sabha-results/actions/workflows/ci.yml)

**Live dashboard:** https://sameerumralkar.github.io/india-lok-sabha-results/

Every Lok Sabha general-election result from 1951 to 2024, plus State Legislative Assembly elections for every state from the first assemblies of 1951–52 to the latest polls: candidate by candidate, constituency by constituency. The data comes from the Election Commission of India's statistical reports. The project also includes party trend views and an HTML dashboard with two menus, **Lok Sabha** and **State elections**.

## What's here

| Path | Contents |
|---|---|
| `data/lok_sabha.db` | Lok Sabha SQLite database (tables and views below) |
| `data/state_assemblies.db.gz` | State assembly SQLite database, gzipped (108 MB unpacked; `gunzip -k` it, or let the tests/exporter unpack it) |
| `data/*.csv` | The same tables and trend views as CSV (`ae_candidates.csv.gz` is gzipped) |
| `dashboard/index.html` | Self-contained trends dashboard: national lineages, each election's top parties, a state explorer, and the largest party per state per election |
| `scripts/` | Download, parse, build and export code (Python 3.9+) |
| `tests/` | Integrity checks run in CI (seat counts, vote reconciliation, known results) |
| `raw/`, `text/` | *Not committed.* The original ECI downloads and their extracted text are re-created by the rebuild steps below |

## Tables

- `elections`: year, Lok Sabha number, and `cycle`. The deferred polls of 1985 (Assam, Punjab) and 1992 (Punjab) roll up into the 1984 and 1991 cycles.
- `constituencies`: one row per seat per election: state, PC number and name, reservation, seats (2 or 3 for some 1951/57 seats), electors, voters, valid votes, turnout, source URL.
- `candidates`: one row per candidate (and per NOTA line from 2014): party (normalised and as printed), lineage family, votes, postal votes, vote share, rank, `won`, `uncontested`.
- `parties`: full name and type (National / State / Registered) for each party abbreviation.
- `data_notes`: known source quirks and how each one was handled.

Views: `national_party_trends`, `state_party_trends`, `national_family_trends`, `state_family_trends`, `election_summary`, `state_summary`.

```sql
-- BJP and INC seats and vote share in Uttar Pradesh across all elections
SELECT year, party, won, state_seats, vote_share
FROM state_party_trends
WHERE state = 'Uttar Pradesh' AND party IN ('INC', 'BJP', 'BJS')
ORDER BY year, party;
```

## State assembly tables (`state_assemblies.db`)

- `ae_constituencies`: one row per assembly seat per election (state as it existed then, AC number and name, reservation, seats, electors, voters, valid votes, turnout, source URL).
- `ae_candidates`: one row per candidate, with the same fields as the Lok Sabha `candidates` table.
- `ae_parties`: party names and types from each report's list of participating parties.
- `ae_load_report`: one row per state election: source (PDF or spreadsheet), seats loaded, mismatched and missing constituencies, status.
- `ae_data_notes`: every gap and quirk, seat by seat.
- Views: `ae_summary` (seats, candidates, turnout and largest party per election), `ae_party_trends` (seats, vote share and outright majority per party), `ae_family_trends`.

Coverage: 414 elections across 43 states and former states. Of those, 385 reconcile completely: every constituency's candidate votes add up to ECI's printed total, and no seat is missing. The other 29 are flagged because a few seats are absent from ECI's own report (countermanded or postponed polls, boycotts, blank entries) or, in 4 cases, one seat doesn't add up. Every one is listed in `ae_data_notes`.

**Not covered:** 7 elections whose ECI PDFs are scanned images with no text layer: Arunachal Pradesh 2014, Bihar 2005, Gujarat 2007 and 2012, Haryana 2005, Himachal Pradesh 2007, and Jharkhand 2005. Reading them needs OCR.

## Validation

- **1951–2009:** for every constituency, the candidate vote totals add up exactly to the valid-vote total that ECI prints for that seat.
- **Candidate counts** match ECI's published figures (for example 1996: 13,952; 2014: 8,251; 2024: 8,360).
- **National seats and vote shares** match ECI's published figures. Examples: INC 364 seats / 44.99% in 1951; BLD 295 / 41.32% in 1977; BJP 282 / 31.34% in 2014.
- **State assemblies:** known results are checked in `tests/test_assembly.py`, for example UP 2017 BJP 312, West Bengal 2011 AITC 184, Tamil Nadu 1967 DMK 137, and Kerala 1957 CPI 60.
- **2019 and 2024:** state-by-state seats and votes reconcile exactly with ECI's "State wise seat won & valid votes" tables. The one exception is the uncontested Surat seat in 2024, which ECI's own table leaves out.

## Conventions

- **Vote share:** calculated over valid votes as ECI defines them, which excludes NOTA. Press figures often include NOTA in the base, which makes them about 1% lower (for example BJP 2024: 36.93% here, 36.56% in the press).
- **State names:** only renames are normalised (Orissa → Odisha, Madras → Tamil Nadu from 1957, Mysore → Karnataka from 1957, and so on). Units that were split or merged keep their historic names: Bombay, Hyderabad, PEPSU, Travancore-Cochin, Goa, Daman & Diu, and others. Undivided Andhra Pradesh stays "Andhra Pradesh" until 2014.
- **Party aliases** (CPI(M) → CPM, ADK → ADMK, WBTC → AITC, INC(I) in 1980 → INC, …) and the lineage families are defined in `scripts/reference.py`. The families are a judgement call; edit them there if you prefer a different grouping.
- **Assembly sources:** ECI's "Detailed Results" spreadsheets are used where published (about 2017 onwards); older elections are parsed from the PDF reports. Seats won unopposed, which the spreadsheets leave out, are added from the same report's list of successful candidates. Parties appear as ECI recorded them, so parties that were not yet registered show as Independents (for example TDP in Andhra Pradesh 1983).
- **2014:** ECI's spreadsheet is missing Odisha and Chhattisgarh. Those 32 seats come from the PDF of the same ECI report.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

CI runs these on every push and deploys `dashboard/` to GitHub Pages.

## Rebuild

```bash
python3 -m venv .venv && .venv/bin/pip install pdfplumber pandas openpyxl xlrd requests
.venv/bin/python -I scripts/download_eci.py raw/eci
.venv/bin/python -I scripts/pdf_to_text.py raw/eci text
.venv/bin/python -I scripts/build_db.py
.venv/bin/pip install pymupdf                             # fast PDF text for the ~400 assembly reports
.venv/bin/python -I scripts/download_ae.py raw/ae
.venv/bin/python -I scripts/build_ae.py
.venv/bin/python -I scripts/export_dashboard.py
```

## Licence

Code: MIT (see `LICENSE`). The election results are the Election Commission of India's published statistics. This repository restructures them, and ECI remains the authoritative source.
