from pathlib import Path

from sciagent.document.parser import DocumentParser
from sciagent.knowledge_extraction.research_design import (
    ResearchDesignExtractor,
)


FIXTURES = (
    Path(__file__).parent.parent
    / "benchmarks"
    / "fixtures"
    / "document_parser"
)


def test_wikiskill_context_builder():
    document = DocumentParser().parse(
        str(FIXTURES / "wikiskill.pdf")
    )

    extractor = ResearchDesignExtractor()

    context = extractor.build_context(
        document
    )

    assert "WikiSkill" in context
    assert "Methodology" in context
    assert "Experimental Setup" in context
    assert "[PAGE " in context
    assert len(context) <= 28000


def test_urbanground_context_builder():
    document = DocumentParser().parse(
        str(FIXTURES / "urbanground.pdf")
    )

    extractor = ResearchDesignExtractor()

    context = extractor.build_context(
        document
    )

    assert "URBANGROUND" in context.upper()
    assert "EXPERIMENT" in context.upper()
    assert "SPATIAL" in context.upper()
    assert len(context) <= 28000


def test_extractor_contract_with_fake_generator():
    document = DocumentParser().parse(
        str(FIXTURES / "wikiskill.pdf")
    )

    def fake_generator(prompt):
        return {
            "research_questions": [
                {
                    "text": "Can persistent knowledge improve skill evolution?",
                    "source_pages": [2],
                    "confidence": 0.9
                }
            ],
            "methods": [],
            "systems": [],
            "datasets": [],
            "models": [],
            "baselines": [],
            "tasks": [],
            "metrics": [],
            "conditions": []
        }

    extractor = ResearchDesignExtractor(
        json_generator=fake_generator
    )

    result = extractor.extract(document)

    assert result["contract"] == "ResearchDesign@0.1"
    assert result["paper_id"] == "wikiskill"
    assert len(result["research_questions"]) == 1
