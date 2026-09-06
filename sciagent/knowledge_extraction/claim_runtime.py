from typing import Dict

from .batching import iter_document_batches


ALLOWED_KINDS = {
    "CONTRIBUTION",
    "FINDING",
    "INTERPRETATION",
    "LIMITATION",
}

ALLOWED_EPISTEMIC_TYPES = {
    "AUTHOR_CLAIM",
    "EXPERIMENTAL_RESULT",
    "INTERPRETATION",
    "LIMITATION",
}


class IterativeClaimRunner:
    """
    Runs ClaimExtractor incrementally over a document and persists
    extracted knowledge into a ResearchWorkspace.

    LLM context is bounded by one DocumentBatch.
    Workspace memory can grow independently of context size.
    """

    stage = "claims_v01"

    def __init__(
        self,
        extractor,
        max_batch_chars=18000,
        overlap_pages=1,
    ):
        self.extractor = extractor
        self.max_batch_chars = max_batch_chars
        self.overlap_pages = overlap_pages

    def run(
        self,
        document,
        workspace,
        run_id: str,
    ) -> Dict:

        paper_id = document.document_id

        checkpoint = workspace.get_checkpoint(
            run_id=run_id,
            paper_id=paper_id,
            stage=self.stage,
        )

        last_completed_page = 0

        if checkpoint:
            last_completed_page = (
                checkpoint.get("last_page")
                or 0
            )

            if checkpoint.get("status") == "completed":
                return {
                    "run_id": run_id,
                    "paper_id": paper_id,
                    "status": "already_completed",
                    "processed_batches": 0,
                    "skipped_batches": 0,
                    "stored_claims": 0,
                    "last_page": last_completed_page,
                }

        processed_batches = 0
        skipped_batches = 0
        stored_claims = 0

        batches = iter_document_batches(
            document=document,
            max_chars=self.max_batch_chars,
            overlap_pages=self.overlap_pages,
        )

        try:
            for batch in batches:

                # Entire batch was already committed.
                if (
                    batch.page_end
                    <= last_completed_page
                ):
                    skipped_batches += 1
                    continue

                result = (
                    self.extractor.extract_batch(
                        document=document,
                        batch=batch,
                    )
                )

                for claim in result.get(
                    "claims",
                    [],
                ):
                    if not self._valid_claim(
                        claim=claim,
                        page_start=batch.page_start,
                        page_end=batch.page_end,
                    ):
                        continue

                    source_pages = claim.get(
                        "source_pages",
                        [],
                    )

                    # Keep page provenance outside payload so that
                    # provenance can later be merged independently.
                    payload = {
                        "kind": claim["kind"],
                        "text": claim["text"].strip(),
                        "epistemic_type": (
                            claim["epistemic_type"]
                        ),
                        "confidence": float(
                            claim["confidence"]
                        ),
                    }

                    workspace.add_artifact(
                        run_id=run_id,
                        paper_id=paper_id,
                        kind="claim",
                        payload=payload,
                        source_pages=source_pages,
                    )

                    stored_claims += 1

                processed_batches += 1

                last_completed_page = (
                    batch.page_end
                )

                # Checkpoint is written only after the batch
                # artifacts were successfully committed.
                workspace.save_checkpoint(
                    run_id=run_id,
                    paper_id=paper_id,
                    stage=self.stage,
                    last_page=last_completed_page,
                    status="running",
                )

        except Exception:
            workspace.save_checkpoint(
                run_id=run_id,
                paper_id=paper_id,
                stage=self.stage,
                last_page=(
                    last_completed_page
                    if last_completed_page
                    else None
                ),
                status="failed",
            )

            raise

        final_page = (
            document.pages[-1].number
            if document.pages
            else None
        )

        workspace.save_checkpoint(
            run_id=run_id,
            paper_id=paper_id,
            stage=self.stage,
            last_page=final_page,
            status="completed",
        )

        return {
            "run_id": run_id,
            "paper_id": paper_id,
            "status": "completed",
            "processed_batches": processed_batches,
            "skipped_batches": skipped_batches,
            "stored_claims": stored_claims,
            "last_page": final_page,
        }

    def _valid_claim(
        self,
        claim,
        page_start,
        page_end,
    ):
        if not isinstance(claim, dict):
            return False

        kind = claim.get("kind")

        if kind not in ALLOWED_KINDS:
            return False

        epistemic_type = claim.get(
            "epistemic_type"
        )

        if (
            epistemic_type
            not in ALLOWED_EPISTEMIC_TYPES
        ):
            return False

        text = claim.get("text")

        if (
            not isinstance(text, str)
            or not text.strip()
        ):
            return False

        confidence = claim.get(
            "confidence"
        )

        if not isinstance(
            confidence,
            (int, float),
        ):
            return False

        if not 0 <= confidence <= 1:
            return False

        pages = claim.get(
            "source_pages"
        )

        if (
            not isinstance(pages, list)
            or not pages
        ):
            return False

        for page in pages:
            if not isinstance(page, int):
                return False

            if not (
                page_start
                <= page
                <= page_end
            ):
                return False

        return True
