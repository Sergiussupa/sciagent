from typing import Dict

from .batching import iter_document_batches


CATEGORY_KIND = {
    "research_questions": "research_question",
    "methods": "method",
    "systems": "system",
    "datasets": "dataset",
    "models": "model",
    "baselines": "baseline",
    "tasks": "task",
    "metrics": "metric",
    "conditions": "condition",
}


class IterativeResearchDesignRunner:
    """
    Incrementally extracts research-design knowledge into a
    persistent ResearchWorkspace.

    The size of LLM context is bounded by DocumentBatch size,
    not by paper size.
    """

    stage = "research_design_v01"

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

            if (
                checkpoint.get("status")
                == "completed"
            ):
                return {
                    "status": "already_completed",
                    "run_id": run_id,
                    "paper_id": paper_id,
                    "processed_batches": 0,
                    "skipped_batches": 0,
                    "stored_items": 0,
                    "last_page": last_completed_page,
                }

        processed_batches = 0
        skipped_batches = 0
        stored_items = 0

        try:
            for batch in iter_document_batches(
                document=document,
                max_chars=self.max_batch_chars,
                overlap_pages=self.overlap_pages,
            ):
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

                for category, kind in (
                    CATEGORY_KIND.items()
                ):
                    for item in result.get(
                        category,
                        [],
                    ):
                        payload = (
                            self._normalize_item(
                                category=category,
                                item=item,
                                page_start=(
                                    batch.page_start
                                ),
                                page_end=(
                                    batch.page_end
                                ),
                            )
                        )

                        if payload is None:
                            continue

                        pages = payload.pop(
                            "source_pages"
                        )

                        workspace.add_artifact(
                            run_id=run_id,
                            paper_id=paper_id,
                            kind=kind,
                            payload=payload,
                            source_pages=pages,
                        )

                        stored_items += 1

                processed_batches += 1
                last_completed_page = (
                    batch.page_end
                )

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
            "status": "completed",
            "run_id": run_id,
            "paper_id": paper_id,
            "processed_batches": (
                processed_batches
            ),
            "skipped_batches": (
                skipped_batches
            ),
            "stored_items": stored_items,
            "last_page": final_page,
        }

    def _normalize_item(
        self,
        category,
        item,
        page_start,
        page_end,
    ):
        if not isinstance(item, dict):
            return None

        pages = item.get(
            "source_pages",
            [],
        )

        if (
            not isinstance(pages, list)
            or not pages
        ):
            return None

        if not all(
            isinstance(page, int)
            and page_start
            <= page
            <= page_end
            for page in pages
        ):
            return None

        confidence = item.get(
            "confidence"
        )

        if not isinstance(
            confidence,
            (int, float),
        ):
            return None

        confidence = max(
            0.0,
            min(
                1.0,
                float(confidence),
            ),
        )

        if category == "research_questions":
            text = str(
                item.get("text", "")
            ).strip()

            if not text:
                return None

            return {
                "text": text,
                "confidence": confidence,
                "source_pages": pages,
            }

        name = str(
            item.get("name", "")
        ).strip()

        if not name:
            return None

        description = str(
            item.get(
                "description",
                "",
            )
        ).strip()

        return {
            "name": name,
            "description": description,
            "confidence": confidence,
            "source_pages": pages,
        }
