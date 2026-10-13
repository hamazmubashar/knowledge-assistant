"""Export the synthetic corpus as the PDF pack for the acceptance-set expert.

Writes eval/pack/<file>.pdf for every current document (and the replaced old version),
plus eval/pack/index.csv describing each file. Content comes from app/eval/corpus.py,
one PDF page per corpus page, so page numbers match what the assistant cites.
Scanned documents are exported as images (no text layer), as the assistant sees them.

Run inside the container:  docker compose exec api python -m app.scripts.export_corpus_pack
"""
import csv
import re
from pathlib import Path

import fitz  # PyMuPDF

from app.eval.corpus import CORPUS_VERSION, DOCS

OUT = Path("/code/eval/pack")
# Documents that deliberately contain hidden instructions (prompt-injection tests).
HIDDEN_INSTRUCTIONS = {"EVAL Support Shipping Policy", "EVAL General Visitor Wi-Fi"}
FOOTER = f"Synthetic test document - not company policy - corpus {CORPUS_VERSION}"


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def text_page(doc, lines: list[str]) -> None:
    page = doc.new_page(width=595, height=842)               # A4 in points
    page.insert_textbox(fitz.Rect(72, 72, 523, 760), "\n\n".join(lines), fontsize=12, fontname="helv")
    page.insert_textbox(fitz.Rect(72, 800, 523, 830), FOOTER, fontsize=8, fontname="helv")


def build_pdf(pages: list[list[str]], scanned: bool, path: Path) -> None:
    doc = fitz.open()
    for lines in pages:
        if not scanned:
            text_page(doc, lines)
            continue
        tmp = fitz.open()
        text_page(tmp, lines)
        pix = tmp[0].get_pixmap(dpi=150)                    # render, then keep only the image
        img_page = doc.new_page(width=595, height=842)
        img_page.insert_image(img_page.rect, pixmap=pix)
        tmp.close()
    doc.save(path)
    doc.close()


def rows() -> list[dict]:
    out = []
    for d in DOCS:
        base = {"title": d["title"], "access_group": d["group"],
                "scanned": "yes" if d.get("scanned") else "no",
                "contains_hidden_instructions": "yes" if d["title"] in HIDDEN_INSTRUCTIONS else "no"}
        out.append({**base, "file": f"{slug(d['title'])}.pdf", "status": "current",
                    "pages": len(d["pages"]), "_pages": d["pages"], "_scanned": bool(d.get("scanned"))})
        if d.get("old_pages"):
            out.append({**base, "file": f"{slug(d['title'])}--replaced-old-version.pdf",
                        "status": "replaced by the current version (do not use as an answer source)",
                        "pages": len(d["old_pages"]), "_pages": d["old_pages"],
                        "_scanned": bool(d.get("scanned"))})
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    table = rows()
    for r in table:
        build_pdf(r["_pages"], r["_scanned"], OUT / r["file"])
    cols = ["file", "title", "access_group", "status", "pages", "scanned", "contains_hidden_instructions"]
    with (OUT / "index.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(table)
    current = sum(r["status"] == "current" for r in table)
    print(f"Exported {len(table)} PDFs ({current} current, {len(table) - current} replaced) "
          f"for corpus {CORPUS_VERSION} to {OUT}")


if __name__ == "__main__":
    main()
