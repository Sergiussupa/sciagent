from pathlib import Path

from sciagent.document.parser import (
    DocumentParser,
)
from sciagent.knowledge_extraction.claims import (
    ClaimExtractor,
)


ROOT = Path(__file__).resolve().parent.parent

FIXTURES = (
    ROOT
    / "benchmarks"
    / "fixtures"
    / "document_parser"
)


def test_wikiskill_claim_context():
    document = DocumentParser().parse(
        str(
            FIXTURES
            / "wikiskill.pdf"
        )
    )

    extractor = ClaimExtractor()

    context = extractor.build_context(
        document
    )

    assert "WikiSkill" in context
    assert "Conclusion" in context
    assert "[PAGE " in context
    assert len(context) <= 26000


def test_urbanground_claim_context():
    document = DocumentParser().parse(
        str(
            FIXTURES
            / "urbanground.pdf"
        )
    )

    extractor = ClaimExtractor()

    context = extractor.build_context(
        document
    )

    assert (
        "URBANGROUND"
        in context.upper()
    )

    assert (
        "EXPERIMENT"
        in context.upper()
    )


def test_claim_contract_fake_generator():
    document = DocumentParser().parse(
        str(
            FIXTURES
            / "wikiskill.pdf"
        )
    )

    def fake_generator(prompt):
        return {
            "claims": [
                {
                    "kind": "CONTRIBUTION",
                    "text": (
                        "WikiSkill uses a "
                        "persistent knowledge base."
                    ),
                    "epistemic_type": (
                        "AUTHOR_CLAIM"
                    ),
                    "source_pages": [1],
                    "confidence": 0.9,
                }
            ]
        }

    extractor = ClaimExtractor(
        json_generator=fake_generator
    )

    result = extractor.extract(
        document
    )

    assert (
        result["contract"]
        == "ClaimSet@0.1"
    )

    assert (
        result["paper_id"]
        == "wikiskill"
    )

    assert len(
        result["claims"]
    ) == 1
