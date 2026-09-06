from dataclasses import dataclass

from sciagent.memory.research_workspace import (
    ResearchWorkspace,
)
from sciagent.knowledge_extraction.batching import (
    iter_document_batches,
)


def test_workspace_roundtrip(tmp_path):
    path = (
        tmp_path
        / "workspace.sqlite3"
    )

    with ResearchWorkspace(path) as ws:
        ws.add_artifact(
            run_id="run-1",
            paper_id="paper-1",
            kind="claim",
            payload={
                "text": "Example claim"
            },
            source_pages=[2],
        )

        artifacts = ws.list_artifacts(
            "run-1"
        )

        assert len(artifacts) == 1

        assert (
            artifacts[0]["payload"]["text"]
            == "Example claim"
        )

        assert (
            artifacts[0]["source_pages"]
            == [2]
        )


def test_workspace_deduplicates_and_merges_pages(
    tmp_path,
):
    path = (
        tmp_path
        / "workspace.sqlite3"
    )

    with ResearchWorkspace(path) as ws:
        payload = {
            "text": "Same claim"
        }

        ws.add_artifact(
            "run-1",
            "paper-1",
            "claim",
            payload,
            [2],
        )

        ws.add_artifact(
            "run-1",
            "paper-1",
            "claim",
            payload,
            [3],
        )

        artifacts = ws.list_artifacts(
            "run-1"
        )

        assert len(artifacts) == 1

        assert (
            artifacts[0]["source_pages"]
            == [2, 3]
        )


def test_workspace_checkpoint_resume(
    tmp_path,
):
    path = (
        tmp_path
        / "workspace.sqlite3"
    )

    with ResearchWorkspace(path) as ws:
        ws.save_checkpoint(
            run_id="run-1",
            paper_id="paper-1",
            stage="claims",
            last_page=12,
            status="running",
        )

    with ResearchWorkspace(path) as ws:
        checkpoint = (
            ws.get_checkpoint(
                run_id="run-1",
                paper_id="paper-1",
                stage="claims",
            )
        )

        assert checkpoint is not None

        assert (
            checkpoint["last_page"]
            == 12
        )

        assert (
            checkpoint["status"]
            == "running"
        )


@dataclass
class FakePage:
    number: int
    text: str


@dataclass
class FakeDocument:
    pages: list


def test_document_batcher_covers_document():
    document = FakeDocument(
        pages=[
            FakePage(
                number=i,
                text=("page-%d " % i) * 100,
            )
            for i in range(
                1,
                8,
            )
        ]
    )

    batches = list(
        iter_document_batches(
            document,
            max_chars=1800,
            overlap_pages=1,
        )
    )

    assert len(batches) > 1

    covered = set()

    for batch in batches:
        covered.update(
            range(
                batch.page_start,
                batch.page_end + 1,
            )
        )

    assert covered == set(
        range(1, 8)
    )
