import json
from typing import Callable, Dict, List, Optional


RELEVANT_SECTION_HINTS = (
    "abstract",
    "introduction",
    "problem setup",
    "method",
    "methodology",
    "approach",
    "framework",
    "experimental setup",
    "experiment",
    "evaluation",
    "dataset",
    "benchmark",
)


CATEGORIES = (
    "research_questions",
    "methods",
    "systems",
    "datasets",
    "models",
    "baselines",
    "tasks",
    "metrics",
    "conditions",
)


class ResearchDesignExtractor:
    """
    Extract structured research design from a parsed scientific document.

    The module deliberately depends only on a small document interface:
      document_id
      title
      abstract
      pages[number, text]
      sections[title, page_start]

    This isolates Knowledge Extraction from DocumentParser internals.
    """

    contract = "ResearchDesign@0.1"

    def __init__(
        self,
        json_generator: Optional[Callable[[str], Dict]] = None,
        max_context_chars: int = 28000,
    ):
        self.json_generator = json_generator
        self.max_context_chars = max_context_chars

    def build_context(self, document) -> str:
        selected_pages = {1}

        for section in document.sections:
            title = section.title.lower()

            if any(
                hint in title
                for hint in RELEVANT_SECTION_HINTS
            ):
                page = section.page_start

                if page:
                    selected_pages.add(page)

                    if page + 1 <= len(document.pages):
                        selected_pages.add(page + 1)

        chunks: List[str] = []

        if document.title:
            chunks.append(
                "TITLE:\n" + document.title
            )

        if document.abstract:
            chunks.append(
                "ABSTRACT:\n" + document.abstract
            )

        # Document structure is cheap, compact evidence.
        # It is especially useful for named frameworks,
        # architectural layers and experimental components
        # whose prose may fall outside the selected pages.
        structure_lines = []

        for section in document.sections:
            if not section.page_start:
                continue

            structure_lines.append(
                "[PAGE {}] {}".format(
                    section.page_start,
                    section.title,
                )
            )

        if structure_lines:
            chunks.append(
                "DOCUMENT STRUCTURE:\n"
                + "\n".join(structure_lines)
            )

        for page_number in sorted(selected_pages):
            page = document.pages[page_number - 1]

            chunks.append(
                "[PAGE {}]\n{}".format(
                    page.number,
                    page.text,
                )
            )

        context = "\n\n".join(chunks)

        return context[:self.max_context_chars]

    def build_prompt(self, document) -> str:
        context = self.build_context(document)

        return """
You extract research design from scientific papers.

Use ONLY the supplied paper text.

Do not infer facts that are not explicitly supported.
Do not extract results, conclusions, or claims unless they describe
the research design itself.

Return JSON only.

Required schema:

{{
  "contract": "ResearchDesign@0.1",
  "paper_id": "...",

  "research_questions": [
    {{
      "text": "...",
      "source_pages": [1],
      "confidence": 0.0
    }}
  ],

  "methods": [],
  "systems": [],
  "datasets": [],
  "models": [],
  "baselines": [],
  "tasks": [],
  "metrics": [],
  "conditions": []
}}

Every object in methods/systems/datasets/models/baselines/tasks/metrics/conditions
must have:

{{
  "name": "...",
  "description": "...",
  "source_pages": [1],
  "confidence": 0.0
}}

Rules:

- source_pages must refer to [PAGE N] markers in the supplied text.
- If a category is not supported, return [].
- Prefer canonical names used by the authors.
- Avoid duplicates.

Category definitions:

- systems:
  named frameworks, platforms, architectures, agents,
  modules, components or architectural layers introduced,
  built or evaluated in the paper.

- methods:
  procedures, algorithms, strategies, interaction methods,
  training methods, evaluation approaches or protocols.

- baselines:
  comparison systems or methods used to evaluate the
  paper's proposed approach. Do not also classify a baseline
  as the paper's own method unless the source explicitly
  requires both roles.

- datasets:
  named datasets, benchmarks, environments or data resources.

- models:
  named model families or concrete models being studied.

- tasks:
  capabilities or tasks being evaluated or solved.

- metrics:
  named quantitative or qualitative evaluation measures.

- conditions:
  experimental settings, variants or environmental conditions.

A named system may contain named subsystems or architectural
layers. Include those components separately when the paper
explicitly names them.

DOCUMENT STRUCTURE is valid evidence for the existence,
canonical name and page location of a structural component.
Do not invent details about that component unless supplied
page text supports them.

- confidence must be between 0 and 1.

paper_id:
{paper_id}

PAPER:
{context}
""".strip().format(
            paper_id=document.document_id,
            context=context,
        )

    def extract(self, document) -> Dict:
        if self.json_generator is None:
            raise RuntimeError(
                "ResearchDesignExtractor requires json_generator"
            )

        prompt = self.build_prompt(document)

        result = self.json_generator(prompt)

        if isinstance(result, str):
            result = json.loads(result)

        result = self._normalize(
            document=document,
            result=result,
        )

        # A compact repair pass is only used when document
        # structure contains likely research-design objects
        # that are not represented in the first extraction.
        if self._needs_structure_repair(
            document=document,
            result=result,
        ):
            repair_prompt = self.build_repair_prompt(
                document=document,
                current=result,
            )

            repair = self.json_generator(
                repair_prompt
            )

            if isinstance(repair, str):
                repair = json.loads(repair)

            result = self._merge_repair(
                document=document,
                result=result,
                repair=repair,
            )

        return result

    def _structure_candidates(
        self,
        document,
    ) -> List[str]:
        hints = (
            "framework",
            "architecture",
            "layer",
            "agent",
            "system",
            "module",
            "component",
            "pipeline",
            "platform",
            "interaction",
            "evaluation",
            "protocol",
            "method",
            "orchestration",
            "navigation",
        )

        candidates = []

        for section in document.sections:
            title = section.title.strip()
            lowered = title.lower()

            if any(
                hint in lowered
                for hint in hints
            ):
                candidates.append(title)

        return candidates

    def _needs_structure_repair(
        self,
        document,
        result: Dict,
    ) -> bool:
        candidates = self._structure_candidates(
            document
        )

        if not candidates:
            return False

        extracted = []

        for category in (
            "methods",
            "systems",
            "tasks",
        ):
            for item in result.get(
                category,
                [],
            ):
                if not isinstance(item, dict):
                    continue

                extracted.append(
                    " ".join(
                        [
                            str(
                                item.get(
                                    "name",
                                    "",
                                )
                            ),
                            str(
                                item.get(
                                    "description",
                                    "",
                                )
                            ),
                        ]
                    ).lower()
                )

        combined = "\n".join(extracted)

        missing = 0

        for candidate in candidates:
            simplified = candidate.lower()

            # Remove common numeric section prefix.
            simplified = __import__(
                "re"
            ).sub(
                r"^\s*\d+(?:\.\d+)*\.?\s*",
                "",
                simplified,
            ).strip()

            if len(simplified) < 5:
                continue

            if simplified not in combined:
                missing += 1

        return missing >= 2

    def build_repair_prompt(
        self,
        document,
        current: Dict,
    ) -> str:
        context = self.build_context(
            document
        )

        current_json = json.dumps(
            current,
            ensure_ascii=False,
            indent=2,
        )

        return """
You are performing a SECOND-PASS repair of scientific
research-design extraction.

The first extraction is shown below.

Do NOT rewrite the whole result.
Do NOT remove anything.
Find only important missing objects in these categories:

- methods
- systems
- tasks

Pay special attention to DOCUMENT STRUCTURE headings.

Definitions:

systems:
named frameworks, platforms, architectures, agents,
architectural layers, modules, components, sandboxes,
or subsystems introduced, built, or evaluated by the paper.

methods:
procedures, algorithms, strategies, interaction methods,
evaluation approaches, protocols, gating mechanisms,
or other research procedures.

tasks:
explicit capabilities, task families, evaluation levels,
navigation tasks, reasoning tasks, or other activities
the studied system must perform.

A named architectural layer such as "Simulation Layer"
or named agent such as "Inference Agent" should normally
be represented as a system if explicitly supported.

Do not invent objects.

Return JSON only:

{
  "methods": [
    {
      "name": "...",
      "description": "...",
      "source_pages": [1],
      "confidence": 0.0
    }
  ],
  "systems": [],
  "tasks": []
}

source_pages must use [PAGE N] markers from the evidence.

CURRENT EXTRACTION:

%s

PAPER EVIDENCE:

%s
""".strip() % (
            current_json,
            context,
        )

    def _merge_repair(
        self,
        document,
        result: Dict,
        repair: Dict,
    ) -> Dict:
        for category in (
            "methods",
            "systems",
            "tasks",
        ):
            additions = repair.get(
                category,
                [],
            )

            if not isinstance(
                additions,
                list,
            ):
                continue

            existing = result.get(
                category,
                [],
            )

            names = {
                str(
                    item.get(
                        "name",
                        "",
                    )
                ).strip().lower()
                for item in existing
                if isinstance(item, dict)
            }

            for item in additions:
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                name = str(
                    item.get(
                        "name",
                        "",
                    )
                ).strip()

                if not name:
                    continue

                pages = item.get(
                    "source_pages",
                    [],
                )

                if not (
                    isinstance(pages, list)
                    and pages
                    and all(
                        isinstance(page, int)
                        and 1 <= page <= len(
                            document.pages
                        )
                        for page in pages
                    )
                ):
                    continue

                key = name.lower()

                if key in names:
                    continue

                existing.append(item)
                names.add(key)

            result[category] = existing

        return result

    def _normalize(
        self,
        document,
        result: Dict,
    ) -> Dict:
        normalized = {
            "contract": self.contract,
            "paper_id": document.document_id,
        }

        for category in CATEGORIES:
            value = result.get(category, [])

            if not isinstance(value, list):
                value = []

            normalized[category] = value

        return normalized
