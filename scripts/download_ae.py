"""Download ECI statistical reports for every State Legislative Assembly election.

Sources (all from https://www.eci.gov.in/statistical-reports, 'General Election To
State Legislative Assembly' and 'States no longer in existence' tabs):
  * old.eci.gov.in file pages (up to 2022/23): every attached file is saved.
  * www.eci.gov.in (2023 onwards): the '10 - Detailed Results' spreadsheet (+ PDF).

Usage: python download_ae.py <out_dir>        -> <out_dir>/<state-slug>/<year>/...
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_eci import UA, fetch_file  # noqa: E402

HERE = Path(__file__).resolve().parent
API = "https://www.eci.gov.in/eci-backend/public/api/election-result?category_id={}"

# States that no longer exist in that form ('Assembly elections of states which are
# no longer in existence after reorganisation').
DEFUNCT = [
    ("Ajmer", "1951", "4110-ajmer-1951"), ("Bhopal", "1951", "4109-bhopal-1951"),
    ("Bombay", "1957", "4108-bombay-1957"), ("Bombay", "1951", "4107-bombay-1951"),
    ("Coorg", "1951", "4106-coorg-1951"), ("Hyderabad", "1951", "4105-hyderabad-1951"),
    ("Madhya Bharat", "1951", "4104-madhya-bharat-1951"), ("Madras", "1967", "4103-madras-1967"),
    ("Madras", "1962", "4102-madras-1962"), ("Madras", "1957", "4101-madras-1957"),
    ("Madras", "1951", "4100-madras-1951"), ("Mysore", "1967", "4099-mysore-1967"),
    ("Mysore", "1951", "4098-mysore-1951"), ("PEPSU", "1954", "4097-patiala-east-punjab-states-union-1954"),
    ("PEPSU", "1951", "4096-patiala-east-punjab-states-union-1951"),
    ("Saurashtra", "1951", "4095-sourastra-1951"), ("Travancore-Cochin", "1954", "4094-travancore-cochin-1954"),
    ("Travancore-Cochin", "1951", "4093-travancore-cochin-1951"), ("Vindhya Pradesh", "1951", "4092-vindhya-pradesh-1951"),
]

# New-site reports: (state, year, category_id or direct folder URL)
NEW_SITE = [
    ("Andhra Pradesh", "2024", 2), ("Arunachal Pradesh", "2024", 3), ("Odisha", "2024", 4),
    ("Sikkim", "2024", 5), ("Haryana", "2024", 6), ("Jammu & Kashmir", "2024", 7),
    ("Maharashtra", "2024", 8), ("Jharkhand", "2024", 9), ("Delhi", "2025", 10),
    ("Bihar", "2025", 16), ("Assam", "2026", 23), ("Kerala", "2026", 24),
    ("Puducherry", "2026", 25), ("Tamil Nadu", "2026", 26), ("West Bengal", "2026", 28),
    ("Mizoram", "2023", 32), ("Madhya Pradesh", "2023", 33), ("Rajasthan", "2023", 34),
    ("Telangana", "2023", 35),
    ("Chhattisgarh", "2023",
     "https://www.eci.gov.in/eci-backend/public/all_files/full-statistical-reports/chhattisgarh/2023/"),
]

# Where ECI publishes two versions of one election, keep the complete one.
SKIP_LABELS = {"2023(Excluding Ac-03)", "2023(Excluding Ac-23)",
               "2021 (Excluding AC 56 & 58)", "2026(Excluding AC-144)"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def year_of(label):
    return re.match(r"\d{4}", label.strip()).group(0)


def old_jobs():
    links = json.loads((HERE / "ae" / "ae_links_raw.json").read_text())
    jobs = []
    for state, label, href in links:
        if "old.eci.gov.in/files/file/" not in href or label.strip() in SKIP_LABELS:
            continue
        jobs.append((state, year_of(label), href.split("/files/file/")[1].strip("/")))
    for state, year, s in DEFUNCT:
        jobs.append((state, year, s))
    return jobs


def run_old(job, out_root):
    state, year, file_slug = job
    out = out_root / slug(state) / year
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        return f"skip {state} {year}"
    for attempt in range(3):
        try:
            sess = requests.Session()
            sess.headers["User-Agent"] = UA
            got = fetch_file(sess, file_slug, out)
            (out / "_source.txt").write_text(f"https://old.eci.gov.in/files/file/{file_slug}/\n")
            return f"{state} {year}: {len(got)} file(s)"
        except Exception as e:  # the archive is flaky; retry
            time.sleep(5 * (attempt + 1))
            err = e
    return f"FAILED {state} {year}: {err}"


def run_new(job, out_root):
    state, year, cat = job
    out = out_root / slug(state) / year
    out.mkdir(parents=True, exist_ok=True)
    if any(out.glob("*Detailed*")) and any(out.glob("*uccessful*")):
        return f"skip {state} {year}"
    h = {"User-Agent": UA, "Referer": "https://www.eci.gov.in/"}
    if isinstance(cat, int):
        res = requests.get(API.format(cat), headers=h, timeout=60).json()["results"]
        hit = next(r for r in res if "detailed result" in r["title"].lower())
        succ = next((r for r in res if "successful" in r["title"].lower()), {})
        urls = [hit.get("xlsx_url"), hit.get("pdf_zip_url"), succ.get("xlsx_url")]
    else:
        urls = [cat + "Detailed_Results.xlsx", cat + "Detailed_Results.pdf",
                cat + "List_of_Successful_Candidates.xlsx"]
    saved = []
    for u in filter(None, urls):
        r = requests.get(u, headers=h, timeout=300)
        if r.ok and r.content[:5] != b"<!doc":
            name = ("List_of_Successful_Candidates" if "uccessful" in u else "Detailed_Results") + Path(u).suffix
            (out / name).write_bytes(r.content)
            saved.append(name)
    (out / "_source.txt").write_text("\n".join(filter(None, urls)) + "\n")
    return f"{state} {year}: {saved}"


def main():
    out_root = Path(sys.argv[1])
    with ThreadPoolExecutor(max_workers=4) as ex:
        for msg in ex.map(lambda j: run_new(j, out_root), NEW_SITE):
            print(msg, flush=True)
        for msg in ex.map(lambda j: run_old(j, out_root), old_jobs()):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
