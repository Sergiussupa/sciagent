from pathlib import Path

from sciagent.document.parser import DocumentParser


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "benchmarks" / "fixtures" / "document_parser"


def test_wikiskill_pdf_text_extraction():
    parser = DocumentParser()
    doc = parser.parse(str(FIXTURES / "wikiskill.pdf"))

    assert doc.document_id == "wikiskill"
    assert len(doc.pages) == 28

    assert all(
        page.number == index
        for index, page in enumerate(doc.pages, start=1)
    )

    full_text = "\n".join(page.text for page in doc.pages)

    assert len(full_text) > 50_000

    assert "WikiSkill" in full_text
    assert "Persistent Knowledge for Skill Evolution" in full_text
    assert "Inference Agent" in full_text
    assert "Skill Proposer" in full_text


def test_urbanground_pdf_text_extraction():
    parser = DocumentParser()
    doc = parser.parse(str(FIXTURES / "urbanground.pdf"))

    assert doc.document_id == "urbanground"
    assert len(doc.pages) >= 10

    full_text = "\n".join(page.text for page in doc.pages)

    assert len(full_text) > 20_000
    assert "UrbanGround" in full_text


def test_parser_preserves_page_navigation():
    parser = DocumentParser()
    doc = parser.parse(str(FIXTURES / "wikiskill.pdf"))

    assert doc.pages
    assert doc.pages[0].number == 1
    assert doc.pages[-1].number == len(doc.pages)

    numbers = [page.number for page in doc.pages]

    assert numbers == list(
        range(1, len(doc.pages) + 1)
    )


def test_parser_extracts_document_structure():
    parser = DocumentParser()
    doc = parser.parse(str(FIXTURES / "wikiskill.pdf"))

    # These are intentionally expected to fail in v0.1 implementation.
    # They define the next implementation target.
    assert doc.title
    assert doc.abstract
    assert len(doc.sections) >= 5
