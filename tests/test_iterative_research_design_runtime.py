import re
from dataclasses import dataclass

import pytest

from sciagent.knowledge_extraction.research_design import (
    ResearchDesignExtractor,
)
from sciagent.knowledge_extraction.research_design_runtime import (
    IterativeResearchDesignRunner,
)
from sciagent.memory.research_workspace import (
    ResearchWorkspace,
)


@dataclass
class FakePage:
    number: int
    text: str


@dataclass
class FakeSection:
    title: str
    page_start: int


@dataclass
class FakeDocument:
    document_id: str
    title: str
    abstract: str
    pages: list
    sections: list


def make_document():
    return FakeDocument(
        document_id="paper-1",
        title="Large Research Paper",
        abstract="",
        pages=[
            FakePage(
                number=i,
                text=(
                    ("scientific page %d " % i)
                    * 70
                ),
            )
            for i in range(1, 9)
        ],
        sections=[
            FakeSection(
                "1 Introduction",
                1,
            ),
            FakeSection(
                "2 Method",
                3,
            ),
            FakeSection(
                "3 Experiments",
                6,
            ),
        ],
    )


def batch_page(prompt):
    match = re.search(
        r"BATCH \d+\nPAGES (\d+)-(\d+):",
        prompt,
    )

    assert match is not None

    return int(match.group(1))


def result_for_page(page):
    return {
        "research_questions": [],
        "methods": [
            {
                "name": (
                    "Method from page %d"
                    % page
                ),
                "description": (
                    "Example method"
                ),
                "source_pages": [page],
                "confidence": 0.9,
            }
        ],
        "systems": [],
        "datasets": [],
        "models": [],
        "baselines": [],
        "tasks": [],
        "metrics": [],
        "conditions": [],
    }


def test_iterative_research_design_persists(
    tmp_path,
):
    document = make_document()

    def generator(prompt):
        return result_for_page(
            batch_page(prompt)
        )

    extractor = ResearchDesignExtractor(
        json_generator=generator
    )

    runner = (
        IterativeResearchDesignRunner(
            extractor=extractor,
            max_batch_chars=2500,
            overlap_pages=1,
        )
    )

    with ResearchWorkspace(
        tmp_path / "workspace.sqlite3"
    ) as workspace:

        result = runner.run(
            document=document,
            workspace=workspace,
            run_id="run-1",
        )

        assert (
            result["status"]
            == "completed"
        )

        methods = (
            workspace.list_artifacts(
                run_id="run-1",
                paper_id="paper-1",
                kind="method",
            )
        )

        assert methods

        checkpoint = (
            workspace.get_checkpoint(
                run_id="run-1",
                paper_id="paper-1",
                stage=(
                    "research_design_v01"
                ),
            )
        )

        assert (
            checkpoint["last_page"]
            == 8
        )

        assert (
            checkpoint["status"]
            == "completed"
        )


def test_iterative_research_design_resume(
    tmp_path,
):
    document = make_document()

    calls = {"count": 0}

    def failing_generator(prompt):
        calls["count"] += 1

        if calls["count"] == 2:
            raise RuntimeError(
                "simulated design failure"
            )

        return result_for_page(
            batch_page(prompt)
        )

    path = (
        tmp_path
        / "workspace.sqlite3"
    )

    extractor = ResearchDesignExtractor(
        json_generator=failing_generator
    )

    runner = (
        IterativeResearchDesignRunner(
            extractor=extractor,
            max_batch_chars=2500,
            overlap_pages=1,
        )
    )

    with ResearchWorkspace(
        path
    ) as workspace:

        with pytest.raises(
            RuntimeError,
            match=(
                "simulated design failure"
            ),
        ):
            runner.run(
                document=document,
                workspace=workspace,
                run_id="run-1",
            )

        checkpoint = (
            workspace.get_checkpoint(
                run_id="run-1",
                paper_id="paper-1",
                stage=(
                    "research_design_v01"
                ),
            )
        )

        assert (
            checkpoint["status"]
            == "failed"
        )

    def resumed_generator(prompt):
        return result_for_page(
            batch_page(prompt)
        )

    extractor = ResearchDesignExtractor(
        json_generator=resumed_generator
    )

    runner = (
        IterativeResearchDesignRunner(
            extractor=extractor,
            max_batch_chars=2500,
            overlap_pages=1,
        )
    )

    with ResearchWorkspace(
        path
    ) as workspace:

        result = runner.run(
            document=document,
            workspace=workspace,
            run_id="run-1",
        )

        assert (
            result["status"]
            == "completed"
        )

        assert (
            result["skipped_batches"]
            >= 1
        )


def test_invalid_design_provenance_rejected(
    tmp_path,
):
    document = make_document()

    def generator(prompt):
        result = result_for_page(999)
        return result

    extractor = ResearchDesignExtractor(
        json_generator=generator
    )

    runner = (
        IterativeResearchDesignRunner(
            extractor=extractor,
            max_batch_chars=2500,
        )
    )

    with ResearchWorkspace(
        tmp_path / "workspace.sqlite3"
    ) as workspace:

        runner.run(
            document=document,
            workspace=workspace,
            run_id="run-1",
        )

        assert (
            workspace.list_artifacts(
                run_id="run-1",
                kind="method",
            )
            == []
        )
