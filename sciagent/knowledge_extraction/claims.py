import json
from typing import Callable, Dict, List, Optional


CLAIM_SECTION_HINTS = (
    "abstract",
    "introduction",
    "result",
    "analysis",
    "discussion",
    "conclusion",
    "limitation",
    "ablation",
    "experiment",
)


class ClaimExtractor:
    contract = "ClaimSet@0.1"

    def __init__(
        self,
        json_generator: Optional[
            Callable[[str], Dict]
        ] = None,
        max_context_chars: int = 26000,
    ):
        self.json_generator = json_generator
        self.max_context_chars = (
            max_context_chars
        )

    def build_context(
        self,
        document,
    ) -> str:
        selected_pages = {
            1,
            2,
        }

        for section in document.sections:
            title = section.title.lower()

            if not any(
                hint in title
                for hint in CLAIM_SECTION_HINTS
            ):
                continue

            page = section.page_start

            if not page:
                continue

            selected_pages.add(page)

            if page + 1 <= len(
                document.pages
            ):
                selected_pages.add(
                    page + 1
                )

        chunks: List[str] = []

        chunks.append(
            "TITLE:\n"
            + document.title
        )

        if document.abstract:
            chunks.append(
                "ABSTRACT:\n"
                + document.abstract
            )

        structure = []

        for section in document.sections:
            if not section.page_start:
                continue

            structure.append(
                "[PAGE {}] {}".format(
                    section.page_start,
                    section.title,
                )
            )

        if structure:
            chunks.append(
                "DOCUMENT STRUCTURE:\n"
                + "\n".join(structure)
            )

        for number in sorted(
            selected_pages
        ):
            page = document.pages[
                number - 1
            ]

            chunks.append(
                "[PAGE {}]\n{}".format(
                    page.number,
                    page.text,
                )
            )

        return "\n\n".join(
            chunks
        )[:self.max_context_chars]

    def build_prompt(
        self,
        document,
    ) -> str:
        return """
Extract the central scientific claims from the supplied paper.

Use ONLY supplied evidence.

Return JSON only.

Schema:

{
  "contract": "ClaimSet@0.1",
  "paper_id": "...",
  "claims": [
    {
      "kind": "CONTRIBUTION",
      "text": "...",
      "epistemic_type": "AUTHOR_CLAIM",
      "source_pages": [1],
      "confidence": 0.0
    }
  ]
}

Allowed kind:

CONTRIBUTION
- what the paper introduces, proposes, builds or contributes

FINDING
- empirical or experimental result reported by the authors

INTERPRETATION
- explanation, implication or interpretation of findings

LIMITATION
- explicitly stated limitation, missing capability or scope restriction


Allowed epistemic_type:

AUTHOR_CLAIM
EXPERIMENTAL_RESULT
INTERPRETATION
LIMITATION


Rules:

- Extract central scientific claims, not every sentence.
- Prefer approximately 5-15 high-value claims.
- Do not invent evidence.
- Keep each claim atomic.
- Do not combine unrelated results.
- Preserve important comparisons and directions of effects.
- CONTRIBUTION usually uses AUTHOR_CLAIM.
- FINDING usually uses EXPERIMENTAL_RESULT.
- INTERPRETATION uses INTERPRETATION.
- LIMITATION uses LIMITATION.
- source_pages must refer to supplied [PAGE N] markers.
- confidence must be between 0 and 1.
- DOCUMENT STRUCTURE may guide attention but is not enough
  by itself to invent a scientific finding.

paper_id:
%s

PAPER:

%s
""".strip() % (
            document.document_id,
            self.build_context(document),
        )

    def build_batch_prompt(
        self,
        document,
        batch,
    ) -> str:
        local_structure = []

        for section in document.sections:
            page = section.page_start

            if not page:
                continue

            if (
                batch.page_start - 1
                <= page
                <= batch.page_end + 1
            ):
                local_structure.append(
                    "[PAGE {}] {}".format(
                        page,
                        section.title,
                    )
                )

        structure_text = (
            "\n".join(local_structure)
            if local_structure
            else "(no local headings detected)"
        )

        return """
Extract scientific claims from ONE PART of a larger paper.

This is an incremental extraction step.
Other parts of the paper may be processed separately.

Use ONLY the supplied batch evidence.

Do not attempt to summarize the whole paper.
Do not infer claims from parts that are not present.

Return JSON only:

{
  "claims": [
    {
      "kind": "FINDING",
      "text": "...",
      "epistemic_type": "EXPERIMENTAL_RESULT",
      "source_pages": [1],
      "confidence": 0.0
    }
  ]
}

Allowed kind:

CONTRIBUTION
FINDING
INTERPRETATION
LIMITATION

Allowed epistemic_type:

AUTHOR_CLAIM
EXPERIMENTAL_RESULT
INTERPRETATION
LIMITATION

Rules:

- Extract only scientifically useful claims.
- Keep each claim atomic.
- Avoid ordinary background statements.
- Do not invent missing context.
- Preserve important comparisons and effect directions.
- Prefer 0-8 high-value claims from this batch.
- Returning [] is correct if this batch has no important claims.
- source_pages MUST refer only to [PAGE N] markers in this batch.
- confidence must be between 0 and 1.

PAPER:

%s

LOCAL DOCUMENT STRUCTURE:

%s

BATCH %s
PAGES %s-%s:

%s
""".strip() % (
            document.title,
            structure_text,
            batch.batch_id,
            batch.page_start,
            batch.page_end,
            batch.text,
        )

    def extract_batch(
        self,
        document,
        batch,
    ) -> Dict:
        if self.json_generator is None:
            raise RuntimeError(
                "ClaimExtractor requires json_generator"
            )

        result = self.json_generator(
            self.build_batch_prompt(
                document=document,
                batch=batch,
            )
        )

        if isinstance(result, str):
            result = json.loads(result)

        claims = result.get(
            "claims",
            [],
        )

        if not isinstance(claims, list):
            claims = []

        return {
            "contract": self.contract,
            "paper_id": document.document_id,
            "claims": claims,
        }

    def extract(
        self,
        document,
    ) -> Dict:
        if self.json_generator is None:
            raise RuntimeError(
                "ClaimExtractor requires json_generator"
            )

        result = self.json_generator(
            self.build_prompt(document)
        )

        if isinstance(result, str):
            result = json.loads(result)

        claims = result.get(
            "claims",
            [],
        )

        if not isinstance(
            claims,
            list,
        ):
            claims = []

        return {
            "contract": self.contract,
            "paper_id": (
                document.document_id
            ),
            "claims": claims,
        }
