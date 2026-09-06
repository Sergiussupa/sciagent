import re

import pytest

from sciagent.knowledge_fabric.paper_consolidator import (
    PaperConsolidator,
)
from sciagent.memory.research_workspace import (
    ResearchWorkspace,
)


def seed_claims(
    workspace,
    count=25,
):
    for number in range(
        1,
        count + 1,
    ):
        workspace.add_artifact(
            run_id="run-1",
            paper_id="paper-1",
            kind="claim",
            payload={
                "kind": "FINDING",
                "text": (
                    "Scientific finding %d"
                    % number
                ),
                "epistemic_type": (
                    "EXPERIMENTAL_RESULT"
                ),
                "confidence": 0.9,
            },
            source_pages=[number],
        )


def make_generator(
    fail_at=None,
):
    state = {
        "calls": 0,
    }

    def generator(prompt):
        state["calls"] += 1

        if (
            fail_at is not None
            and state["calls"]
            == fail_at
        ):
            raise RuntimeError(
                "simulated reducer failure"
            )

        ids = re.findall(
            r"\[(C\d+)\]",
            prompt,
        )

        # One compact claim per group.
        return {
            "claims": [
                {
                    "kind": "FINDING",
                    "text": (
                        "Merged scientific finding "
                        "%d"
                        % state["calls"]
                    ),
                    "epistemic_type": (
                        "EXPERIMENTAL_RESULT"
                    ),
                    "source_ids": ids,
                    "confidence": 0.9,
                }
            ]
        }

    return generator, state


def test_hierarchical_reduction_and_provenance(
    tmp_path,
):
    path = (
        tmp_path
        / "workspace.sqlite3"
    )

    generator, state = (
        make_generator()
    )

    with ResearchWorkspace(path) as ws:
        seed_claims(
            ws,
            count=25,
        )

        consolidator = (
            PaperConsolidator(
                json_generator=generator,
                group_size=5,
                max_outputs_per_group=2,
                target_claims=4,
            )
        )

        result = consolidator.run(
            workspace=ws,
            run_id="run-1",
            paper_id="paper-1",
        )

        assert (
            result["status"]
            == "completed"
        )

        assert (
            result["paper_claims"]
            <= 4
        )

        assert state["calls"] > 1

        knowledge = (
            consolidator
            .build_paper_knowledge(
                workspace=ws,
                run_id="run-1",
                paper_id="paper-1",
            )
        )

        assert (
            knowledge["raw_claim_count"]
            == 25
        )

        assert knowledge["claims"]

        for claim in knowledge["claims"]:
            assert claim[
                "source_pages"
            ]

            assert claim[
                "source_fingerprints"
            ]


def test_consolidator_resume_reuses_groups(
    tmp_path,
):
    path = (
        tmp_path
        / "workspace.sqlite3"
    )

    failing, first_state = (
        make_generator(
            fail_at=3
        )
    )

    with ResearchWorkspace(path) as ws:
        seed_claims(
            ws,
            count=25,
        )

        consolidator = (
            PaperConsolidator(
                json_generator=failing,
                group_size=5,
                max_outputs_per_group=2,
                target_claims=4,
            )
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "simulated reducer failure"
            ),
        ):
            consolidator.run(
                workspace=ws,
                run_id="run-1",
                paper_id="paper-1",
            )

        checkpoint = (
            ws.get_checkpoint(
                run_id="run-1",
                paper_id="paper-1",
                stage=(
                    "paper_consolidation_v01"
                ),
            )
        )

        assert (
            checkpoint["status"]
            == "failed"
        )

    resumed, second_state = (
        make_generator()
    )

    with ResearchWorkspace(path) as ws:
        consolidator = (
            PaperConsolidator(
                json_generator=resumed,
                group_size=5,
                max_outputs_per_group=2,
                target_claims=4,
            )
        )

        result = consolidator.run(
            workspace=ws,
            run_id="run-1",
            paper_id="paper-1",
        )

        assert (
            result["status"]
            == "completed"
        )

        assert (
            result["reused_groups"]
            >= 2
        )


def test_completed_consolidation_is_idempotent(
    tmp_path,
):
    path = (
        tmp_path
        / "workspace.sqlite3"
    )

    generator, state = (
        make_generator()
    )

    with ResearchWorkspace(path) as ws:
        seed_claims(
            ws,
            count=12,
        )

        consolidator = (
            PaperConsolidator(
                json_generator=generator,
                group_size=5,
                max_outputs_per_group=2,
                target_claims=4,
            )
        )

        first = consolidator.run(
            workspace=ws,
            run_id="run-1",
            paper_id="paper-1",
        )

        calls_after_first = (
            state["calls"]
        )

        second = consolidator.run(
            workspace=ws,
            run_id="run-1",
            paper_id="paper-1",
        )

        assert (
            first["status"]
            == "completed"
        )

        assert (
            second["status"]
            == "already_completed"
        )

        assert (
            state["calls"]
            == calls_after_first
        )
