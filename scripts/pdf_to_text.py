"""Cache the text of every ECI PDF as <name>.txt next to a page marker.

Usage: python pdf_to_text.py <raw_dir> <text_dir>
"""
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfplumber


def dump(args):
    src, dest = args
    if dest.exists():
        return f"skip {dest.name}"
    parts = []
    with pdfplumber.open(src) as pdf:
        for i, page in enumerate(pdf.pages):
            parts.append(f"\f@@PAGE {i}\n{page.extract_text() or ''}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(parts))
    return f"done {dest} ({len(parts)} pages)"


def main():
    raw, out = Path(sys.argv[1]), Path(sys.argv[2])
    jobs = [(p, out / p.parent.name / (p.stem + ".txt"))
            for p in sorted(raw.rglob("*")) if p.suffix.lower() == ".pdf"]
    with ProcessPoolExecutor(max_workers=6) as ex:
        for msg in ex.map(dump, jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
