import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sciagent.document.parser import DocumentParser
from sciagent.knowledge_extraction.research_design import (
    ResearchDesignExtractor,
)
from sciagent.llm.providers import OllamaLLM


FIXTURES = (
    ROOT
    / "benchmarks"
    / "fixtures"
    / "document_parser"
)

GOLD_DIR = (
    ROOT
    / "benchmarks"
    / "gold"
    / "research_design_extractor"
)

SCHEMA_PATH = (
    ROOT
    / "contracts"
    / "research_design"
    / "schema.json"
)

RESULTS_DIR = (
    ROOT
    / "state"
    / "benchmark_runs"
    / "research_design_extractor"
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


def normalize(text):
    text = unicodedata.normalize(
        "NFKC",
        str(text),
    ).lower()

    text = re.sub(
        r"[^\w\s]+",
        " ",
        text,
        flags=re.UNICODE,
    )

    return " ".join(text.split())


def item_text(category, item):
    if category == "research_questions":
        return str(item.get("text", ""))

    return " ".join(
        [
            str(item.get("name", "")),
            str(item.get("description", "")),
        ]
    )


def concept_matches(aliases, candidates):
    for alias in aliases:
        alias_key = normalize(alias)

        if not alias_key:
            continue

        for candidate in candidates:
            if alias_key in normalize(candidate):
                return True

    return False


def parse_json_response(text):
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Defensive fallback if a model ever wraps JSON in prose/fences.
    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        return json.loads(
            text[start:end + 1]
        )

    raise ValueError(
        "Model did not return a JSON object"
    )


def make_generator(llm):
    def generate(prompt):
        raw = llm.generate(
            prompt,
            system=(
                "You are a precise scientific information "
                "extraction engine. Use only supplied evidence. "
                "Return valid JSON only."
            ),
            json_mode=True,
        )

        return parse_json_response(raw)

    return generate


def evaluate(name, parser, extractor, schema):
    pdf_path = FIXTURES / f"{name}.pdf"
    gold_path = GOLD_DIR / f"{name}.json"

    document = parser.parse(
        str(pdf_path)
    )

    gold = json.loads(
        gold_path.read_text(
            encoding="utf-8"
        )
    )

    print()
    print("=" * 78)
    print(name.upper())
    print("=" * 78)
    print("document:", document.title)
    print("running qwen3:14b ...")

    result = extractor.extract(document)

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        RESULTS_DIR
        / f"{name}.json"
    )

    output_path.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    # -------------------------------------------------------
    # Schema validity
    # -------------------------------------------------------

    validator = Draft202012Validator(
        schema
    )

    schema_errors = list(
        validator.iter_errors(result)
    )

    schema_validity = (
        1.0
        if not schema_errors
        else 0.0
    )

    # -------------------------------------------------------
    # Required concept recall
    # -------------------------------------------------------

    required_total = 0
    required_hits = 0
    misses = []

    required = gold.get(
        "required_concepts",
        {},
    )

    for category, concepts in required.items():
        items = result.get(
            category,
            [],
        )

        candidates = [
            item_text(category, item)
            for item in items
            if isinstance(item, dict)
        ]

        for aliases in concepts:
            required_total += 1

            if concept_matches(
                aliases,
                candidates,
            ):
                required_hits += 1
            else:
                misses.append(
                    (
                        category,
                        aliases,
                    )
                )

    required_recall = (
        required_hits / required_total
        if required_total
        else 1.0
    )

    # -------------------------------------------------------
    # Source-page coverage
    # -------------------------------------------------------

    provenance_total = 0
    provenance_valid = 0

    for category in CATEGORIES:
        for item in result.get(
            category,
            [],
        ):
            if not isinstance(
                item,
                dict,
            ):
                continue

            provenance_total += 1

            pages = item.get(
                "source_pages",
                [],
            )

            valid = (
                isinstance(pages, list)
                and bool(pages)
                and all(
                    isinstance(page, int)
                    and 1 <= page <= len(document.pages)
                    for page in pages
                )
            )

            if valid:
                provenance_valid += 1

    source_page_coverage = (
        provenance_valid
        / provenance_total
        if provenance_total
        else 1.0
    )

    # -------------------------------------------------------
    # Report
    # -------------------------------------------------------

    print()
    print("METRICS")
    print(
        " schema_validity:       ",
        f"{schema_validity:.3f}",
    )
    print(
        " required_concept_recall:",
        f"{required_recall:.3f}",
        f"({required_hits}/{required_total})",
    )
    print(
        " source_page_coverage:  ",
        f"{source_page_coverage:.3f}",
        f"({provenance_valid}/{provenance_total})",
    )

    if schema_errors:
        print()
        print("SCHEMA ERRORS:")

        for error in schema_errors[:10]:
            path = ".".join(
                str(part)
                for part in error.absolute_path
            )

            print(
                " -",
                path or "<root>",
                ":",
                error.message,
            )

    print()
    print("EXTRACTED:")

    for category in CATEGORIES:
        items = result.get(
            category,
            [],
        )

        print(
            f"\n{category}: {len(items)}"
        )

        for item in items[:20]:
            if not isinstance(
                item,
                dict,
            ):
                print(" -", item)
                continue

            if category == "research_questions":
                label = item.get(
                    "text",
                    "",
                )
            else:
                label = item.get(
                    "name",
                    "",
                )

            print(
                " -",
                label,
                "| pages:",
                item.get(
                    "source_pages",
                    [],
                ),
            )

    print()
    print("MISSED REQUIRED CONCEPTS:")

    if misses:
        for category, aliases in misses:
            print(
                " -",
                category,
                ":",
                " / ".join(aliases),
            )
    else:
        print(" none")

    print()
    print("saved:", output_path)

    passed = (
        schema_validity >= 1.0
        and required_recall >= 0.80
        and source_page_coverage >= 0.95
    )

    print(
        "ACCEPTANCE:",
        "PASS" if passed else "FAIL",
    )

    return passed


def main():
    model = os.getenv(
        "SCIAGENT_MODEL",
        "qwen3:14b",
    )

    ollama_url = os.getenv(
        "OLLAMA_URL",
        "http://127.0.0.1:11434",
    )

    print("model:", model)
    print("ollama:", ollama_url)

    llm = OllamaLLM(
        base_url=ollama_url,
        model=model,
        timeout=600,
    )

    if not llm.available():
        print(
            "ERROR: Ollama is not reachable",
            file=sys.stderr,
        )
        return 2

    schema = json.loads(
        SCHEMA_PATH.read_text(
            encoding="utf-8"
        )
    )

    parser = DocumentParser()

    # Keep enough space for model output inside the
    # current Ollama 8192-token context.
    extractor = ResearchDesignExtractor(
        json_generator=make_generator(
            llm
        ),
        max_context_chars=24000,
    )

    passed = []

    for name in (
        "wikiskill",
        "urbanground",
    ):
        passed.append(
            evaluate(
                name=name,
                parser=parser,
                extractor=extractor,
                schema=schema,
            )
        )

    print()
    print("=" * 78)
    print(
        "OVERALL:",
        "PASS"
        if all(passed)
        else "FAIL",
    )
    print("=" * 78)

    return (
        0
        if all(passed)
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
