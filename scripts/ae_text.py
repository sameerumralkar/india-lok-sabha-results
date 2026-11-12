"""Fast text extraction for assembly PDFs (PyMuPDF), normalised to the layout the
Lok Sabha parser expects: one line per row, single spaces, '\\f@@PAGE n' markers."""
import re
from pathlib import Path

import fitz  # PyMuPDF


def pdf_text(src: Path, cache: Path) -> str:
    if cache.exists():
        return cache.read_text()
    parts = []
    with fitz.open(src) as doc:
        for i, page in enumerate(doc):
            lines = [re.sub(r"[ \t ]+", " ", ln).strip()
                     for ln in page.get_text("text", sort=True).split("\n")]
            # PyMuPDF prints '1 . NAME' with spaces; the parser handles both.
            parts.append(f"\f@@PAGE {i}\n" + "\n".join(ln for ln in lines if ln))
    text = "\n".join(parts)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text)
    return text
