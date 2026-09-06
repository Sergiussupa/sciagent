from dataclasses import dataclass

import pytest

from sciagent.knowledge_extraction.claim_runtime import (
    IterativeClaimRunner,
)
from sciagent.knowledge_extraction.claims import (
    ClaimExtractor,
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
        title="Large Scientific Paper",
        abstract="",
        pages=[
            FakePage(
                number=i,
                text=(
                    ("scientific content page %d " % i)
                    * 60
                ),
            )
            for i in range(1, 9)
        ],
        sections=[
            FakeSection(
                title="1 Introduction",
                page_start=1,
            ),
            FakeSection(
                title="2 Experiments",
                page_start=4,
            ),
            FakeSection(
                title="3 Conclusion",
                page_start=7,
            ),
        ],
    )


def page_from_prompt(prompt):
    import re

    match = re.search(
        r"BATCH \d+\nPAGES (\d+)-(\d+):",
        prompt,
    )

    assert match is not None

    return int(match.group(1))


def test_iterative_claims_persist(
    tmp_path,
):
    document = make_document()

    def generator(prompt):
        page = page_from_prompt(prompt)

        return {
            "claims": [
                {
                    "kind": "FINDING",
                    "text": (
                        "Finding from page %d"
                        % page
                    ),
                    "epistemic_type": (
                        "EXPERIMENTAL_RESULT"
                    ),
                    "source_pages": [page],
                    "confidence": 0.9,
                }
            ]
        }

    extractor = ClaimExtractor(
        json_generator=generator
    )

    runner = IterativeClaimRunner(
        extractor=extractor,
        max_batch_chars=2500,
        overlap_pages=1,
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

        artifacts = (
            workspace.list_artifacts(
                run_id="run-1",
                kind="claim",
            )
        )

        assert artifacts

        checkpoint = (
            workspace.get_checkpoint(
                run_id="run-1",
                paper_id="paper-1",
                stage="claims_v01",
            )
        )

        assert (
            checkpoint["status"]
            == "completed"
        )

        assert (
            checkpoint["last_page"]
            == 8
        )


def test_iterative_claims_resume_after_failure(
    tmp_path,
):
    document = make_document()

    calls = {
        "count": 0,
    }

    def failing_generator(prompt):
        calls["count"] += 1

        if calls["count"] == 2:
            raise RuntimeError(
                "simulated LLM failure"
            )

        page = page_from_prompt(prompt)

        return {
            "claims": [
                {
                    "kind": "FINDING",
                    "text": (
                        "Finding from page %d"
                        % page
                    ),
                    "epistemic_type": (
                        "EXPERIMENTAL_RESULT"
                    ),
                    "source_pages": [page],
                    "confidence": 0.9,
                }
            ]
        }

    db_path = (
        tmp_path
        / "workspace.sqlite3"
    )

    extractor = ClaimExtractor(
        json_generator=failing_generator
    )

    runner = IterativeClaimRunner(
        extractor=extractor,
        max_batch_chars=2500,
        overlap_pages=1,
    )

    with ResearchWorkspace(
        db_path
    ) as workspace:

        with pytest.raises(
            RuntimeError,
            match="simulated LLM failure",
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
                stage="claims_v01",
            )
        )

        assert (
            checkpoint["status"]
            == "failed"
        )

        first_last_page = (
            checkpoint["last_page"]
        )

        assert first_last_page >= 1
        assert first_last_page < 8

    resumed_calls = {
        "count": 0,
    }

    def resumed_generator(prompt):
        resumed_calls["count"] += 1

        page = page_from_prompt(prompt)

        return {
            "claims": [
                {
                    "kind": "FINDING",
                    "text": (
                        "Finding from page %d"
                        % page
                    ),
                    "epistemic_type": (
                        "EXPERIMENTAL_RESULT"
                    ),
                    "source_pages": [page],
                    "confidence": 0.9,
                }
            ]
        }

    resumed_extractor = ClaimExtractor(
        json_generator=resumed_generator
    )

    resumed_runner = IterativeClaimRunner(
        extractor=resumed_extractor,
        max_batch_chars=2500,
        overlap_pages=1,
    )

    with ResearchWorkspace(
        db_path
    ) as workspace:

        result = resumed_runner.run(
            document=document,
            workspace=workspace,
            run_id="run-1",
        )

        assert (
            result["status"]
            == "completed"
        )

        checkpoint = (
            workspace.get_checkpoint(
                run_id="run-1",
                paper_id="paper-1",
                stage="claims_v01",
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

        # Resume should skip at least one already
        # committed batch instead of restarting the paper.
        assert result["skipped_batches"] >= 1


def test_invalid_batch_provenance_is_rejected(
    tmp_path,
):
    document = make_document()

    def generator(prompt):
        return {
            "claims": [
                {
                    "kind": "FINDING",
                    "text": "Bad provenance",
                    "epistemic_type": (
                        "EXPERIMENTAL_RESULT"
                    ),
                    "source_pages": [999],
                    "confidence": 0.9,
                }
            ]
        }

    extractor = ClaimExtractor(
        json_generator=generator
    )

    runner = IterativeClaimRunner(
        extractor=extractor,
        max_batch_chars=2500,
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
                kind="claim",
            )
            == []
        )
