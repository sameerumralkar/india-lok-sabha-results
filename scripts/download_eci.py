"""Download Lok Sabha statistical reports from the ECI archive (old.eci.gov.in).

The archive (Invision Community) needs a session cookie and a per-session csrfKey:
  file page -> ?do=download (terms page) -> ?do=download&confirm=1&csrfKey=..
  (list of files) -> ?do=download&r=<id>&confirm=1&t=1&csrfKey=.. (binary).

Usage: python download_eci.py <out_dir>
"""
import html
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests

BASE = "https://old.eci.gov.in/files/file/"
UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36"

# year -> list of archive file slugs (the full report for older years,
# only the constituency-wise detailed result for 2009-2019).
FILES = {
    1951: ["4111-general-election-1951-vol-i-ii"],
    1957: ["4112-general-election-1957-vol-i-ii"],
    1962: ["4113-general-election-1962-vol-i-ii"],
    1967: ["4114-general-election-1967-vol-i-ii"],
    1971: ["4115-general-election-1971-vol-i-ii"],
    1977: ["4116-general-election-1977-vol-i-ii"],
    1980: ["4117-general-election-1980-vol-i-ii"],
    1984: ["4118-general-election-1984-vol-i-ii"],
    1985: ["4119-general-election-1985-vol-i-ii"],
    1989: ["4120-general-election-1989-vol-i-ii"],
    1991: ["4121-general-election-1991-vol-i-ii"],
    1992: ["4122-general-election-1992-vol-i-ii"],
    1996: ["4123-general-election-1996-vol-i-ii"],
    1998: ["4124-general-election-1998-vol-i-ii"],
    1999: ["4125-general-election-1999-vol-i-ii-iii"],
    2004: ["4126-general-election-2004-vol-i-ii-iii"],
    2009: ["2857-constituency-wise-detailed-result", "2851-party-wise-state-wise-seat-won-and-votes-polled-lok-sabha-2009"],
    2014: ["2785-constituency-wise-detailed-result", "2824-state-wise-seat-won-and-valid-votes-polled-by-political-party"],
    2019: ["13539-33-constituency-wise-detailed-result", "13571-17-state-wise-seat-won-valid-votes-polled-by-political-parties"],
}


def fetch_file(sess: requests.Session, slug: str, out: Path) -> list:
    page = BASE + slug + "/"
    sess.get(page, timeout=60)
    terms = sess.get(page + "?do=download", headers={"Referer": page}, timeout=60).text
    m = re.search(r"confirm=1&amp;csrfKey=([0-9a-f]+)", terms)
    direct = re.search(r"do=download&amp;r=\d+&amp;confirm=1&amp;t=1&amp;csrfKey=([0-9a-f]+)", terms)
    if m:  # terms page first, then the list of files
        key = m.group(1)
        listing = sess.get(f"{page}?do=download&confirm=1&csrfKey={key}",
                           headers={"Referer": page + "?do=download"}, timeout=60)
    elif direct:  # some pages have no terms step and list the files straight away
        key = direct.group(1)
        listing = sess.get(page + "?do=download", headers={"Referer": page}, timeout=60)
    else:
        raise RuntimeError(f"no csrfKey for {slug}")
    rids = sorted(set(re.findall(r"do=download&amp;r=(\d+)&amp;confirm=1&amp;t=1", listing.text)))
    got = []
    if not rids:  # single file: the confirm URL returns the binary directly
        rids = [None]
    for rid in rids:
        url = f"{page}?do=download&confirm=1&t=1&csrfKey={key}" + (f"&r={rid}" if rid else "")
        r = sess.get(url, headers={"Referer": listing.url}, timeout=600)
        cd = r.headers.get("Content-Disposition", "")
        fm = re.search(r'filename="?([^";]+)', cd)
        if not fm or not r.content:
            print(f"  ! {slug} r={rid}: no file ({r.headers.get('Content-Type')})")
            continue
        name = html.unescape(unquote(fm.group(1))).replace("/", "_")
        dest = out / name
        dest.write_bytes(r.content)
        got.append(dest)
        print(f"  {dest.name}  {len(r.content)/1e6:.1f} MB")
        time.sleep(1)
    return got


NEW_SITE_2024 = "https://www.eci.gov.in/eci-backend/public/all_files/GE-2024-statistical-report/"
FILES_2024 = ["33-Constituency-Wise-Detailed-Result.xls",
              "17-State-Wise-Seat-Won-&-Valid-Votes-Polled-by-Political-Parties.xls",
              "3-List-Of-Political-Parties-Participated.xlsx"]


def fetch_2024(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for name in FILES_2024:
        if not (out / name).exists():
            r = requests.get(NEW_SITE_2024 + name, headers={"User-Agent": UA,
                             "Referer": "https://www.eci.gov.in/"}, timeout=300)
            r.raise_for_status()
            (out / name).write_bytes(r.content)
            print(f"  2024/{name}  {len(r.content)/1e6:.1f} MB")


def main():
    out_root = Path(sys.argv[1])
    fetch_2024(out_root / "2024")
    for year, slugs in FILES.items():
        out = out_root / str(year)
        out.mkdir(parents=True, exist_ok=True)
        if any(out.iterdir()):
            print(f"{year}: already present, skipping")
            continue
        print(year)
        sess = requests.Session()
        sess.headers["User-Agent"] = UA
        for slug in slugs:
            for attempt in range(3):
                try:
                    fetch_file(sess, slug, out)
                    break
                except Exception as e:  # network hiccups on the archive are common
                    print(f"  retry {attempt+1} {slug}: {e}")
                    time.sleep(5)


if __name__ == "__main__":
    main()
