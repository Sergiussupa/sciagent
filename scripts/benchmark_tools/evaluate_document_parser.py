import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sciagent.document.parser import DocumentParser


ROOT = Path(__file__).resolve().parents[2]

FIXTURES = (
    ROOT
    / "benchmarks"
    / "fixtures"
    / "document_parser"
)

GOLD = (
    ROOT
    / "benchmarks"
    / "gold"
    / "document_parser"
)


def normalize(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains(expected, actual):
    expected = normalize(expected)
    actual = normalize(actual)

    # Never let two empty normalized strings count as a match.
    if not expected or not actual:
        return False

    return expected in actual

def evaluate(name):
    gold = json.loads(
        (GOLD / f"{name}.json").read_text()
    )

    doc = DocumentParser().parse(
        str(FIXTURES / f"{name}.pdf")
    )

    full_text = "\n".join(
        page.text
        for page in doc.pages
    )

    detected_sections = [
        section.title
        for section in doc.sections
    ]

    title_ok = (
        normalize(doc.title)
        == normalize(gold["title"])
    )

    page_ok = (
        len(doc.pages)
        == gold["page_count"]
    )

    abstract_anchor_hits = sum(
        contains(anchor, doc.abstract)
        for anchor in gold["abstract"]["anchors"]
    )

    text_anchor_hits = sum(
        contains(anchor, full_text)
        for anchor in gold["text_anchors"]
    )

    top_section_hits = sum(
        any(
            contains(expected, actual)
            for actual in detected_sections
        )
        for expected in gold["top_level_sections"]
    )

    subsection_hits = sum(
        any(
            contains(expected, actual)
            for actual in detected_sections
        )
        for expected in gold["required_subsections"]
    )

    print()
    print("=" * 72)
    print(name)
    print("=" * 72)

    print("TITLE")
    print(" expected:", gold["title"])
    print(" detected:", doc.title)
    print(" pass:", title_ok)

    print()
    print(
        "PAGE COUNT:",
        len(doc.pages),
        "/",
        gold["page_count"],
        "PASS" if page_ok else "FAIL",
    )

    print()
    print(
        "ABSTRACT:",
        len(doc.abstract),
        "chars"
    )

    print(
        " abstract anchors:",
        f"{abstract_anchor_hits}/{len(gold['abstract']['anchors'])}"
    )

    print(
        " text anchors:",
        f"{text_anchor_hits}/{len(gold['text_anchors'])}"
    )

    print(
        " top-level sections:",
        f"{top_section_hits}/{len(gold['top_level_sections'])}"
    )

    print(
        " required subsections:",
        f"{subsection_hits}/{len(gold['required_subsections'])}"
    )

    print(
        " detected section candidates:",
        len(detected_sections)
    )


for paper in (
    "wikiskill",
    "urbanground",
):
    evaluate(paper)
