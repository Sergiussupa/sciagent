import json
import re
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sciagent.document.parser import DocumentParser


FIXTURES = ROOT / "benchmarks" / "fixtures" / "document_parser"
GOLD = ROOT / "benchmarks" / "gold" / "document_parser"


def normalize(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def matches(expected, actual):
    return normalize(expected) in normalize(actual)


def inspect_gold_misses(name):
    gold = json.loads(
        (GOLD / f"{name}.json").read_text()
    )

    doc = DocumentParser().parse(
        str(FIXTURES / f"{name}.pdf")
    )

    detected = [s.title for s in doc.sections]

    print()
    print("=" * 100)
    print(name.upper())
    print("=" * 100)

    print("\nDETECTED TITLE:")
    print(doc.title)

    print("\nMISSING TOP-LEVEL:")
    missing = [
        expected
        for expected in gold["top_level_sections"]
        if not any(matches(expected, actual) for actual in detected)
    ]
    if missing:
        for item in missing:
            print(" -", item)
    else:
        print(" none")

    print("\nMISSING SUBSECTIONS:")
    missing = [
        expected
        for expected in gold["required_subsections"]
        if not any(matches(expected, actual) for actual in detected)
    ]
    if missing:
        for item in missing:
            print(" -", item)
    else:
        print(" none")

    print("\nFIRST 40 DETECTED SECTION CANDIDATES:")
    for section in doc.sections[:40]:
        print(
            f" p{section.page_start!s:>2} | {section.title}"
        )


def inspect_first_page_layout(name):
    pdf_path = FIXTURES / f"{name}.pdf"
    pdf = fitz.open(str(pdf_path))
    page = pdf[0]

    data = page.get_text("dict")

    lines = []

    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])

            text = "".join(
                span.get("text", "")
                for span in spans
            ).strip()

            if not text:
                continue

            max_size = max(
                span.get("size", 0)
                for span in spans
            )

            fonts = sorted({
                span.get("font", "")
                for span in spans
                if span.get("font")
            })

            bbox = line.get("bbox")

            lines.append(
                (
                    max_size,
                    bbox[1] if bbox else 0,
                    bbox,
                    fonts,
                    text,
                )
            )

    lines.sort(
        key=lambda x: (
            -x[0],
            x[1],
        )
    )

    print()
    print("-" * 100)
    print(f"{name.upper()} — FIRST PAGE LINES BY FONT SIZE")
    print("-" * 100)

    for size, y, bbox, fonts, text in lines[:60]:
        print(
            f"{size:6.2f} | y={y:7.1f} | "
            f"{str(fonts):35} | {text}"
        )

    pdf.close()


for paper in ("wikiskill", "urbanground"):
    inspect_gold_misses(paper)
    inspect_first_page_layout(paper)
