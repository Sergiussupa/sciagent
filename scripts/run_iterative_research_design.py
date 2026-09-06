import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from sciagent.document.parser import DocumentParser
from sciagent.knowledge_extraction.research_design import (
    ResearchDesignExtractor,
)
from sciagent.knowledge_extraction.research_design_runtime import (
    IterativeResearchDesignRunner,
)
from sciagent.llm.providers import OllamaLLM
from sciagent.memory.research_workspace import (
    ResearchWorkspace,
)


def parse_json(text):
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if start >= 0 and end > start:
            return json.loads(
                text[start:end + 1]
            )

        raise


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("pdf")

    parser.add_argument(
        "--run-id",
        required=True,
    )

    parser.add_argument(
        "--model",
        default=os.getenv(
            "SCIAGENT_MODEL",
            "qwen3:14b",
        ),
    )

    args = parser.parse_args()

    document = DocumentParser().parse(
        args.pdf
    )

    llm = OllamaLLM(
        base_url=os.getenv(
            "OLLAMA_URL",
            "http://127.0.0.1:11434",
        ),
        model=args.model,
        timeout=600,
    )

    def generator(prompt):
        raw = llm.generate(
            prompt,
            system=(
                "You extract structured scientific "
                "research design precisely. "
                "Use only supplied evidence. "
                "Return JSON only."
            ),
            json_mode=True,
        )

        return parse_json(raw)

    extractor = ResearchDesignExtractor(
        json_generator=generator
    )

    runner = (
        IterativeResearchDesignRunner(
            extractor=extractor,
            max_batch_chars=18000,
            overlap_pages=1,
        )
    )

    workspace_path = (
        ROOT
        / "state"
        / "research_runs"
        / args.run_id
        / "workspace.sqlite3"
    )

    with ResearchWorkspace(
        workspace_path
    ) as workspace:

        result = runner.run(
            document=document,
            workspace=workspace,
            run_id=args.run_id,
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

        print()
        print("WORKSPACE COUNTS")

        for kind, count in (
            workspace.counts(
                args.run_id
            ).items()
        ):
            print(
                "  {:<28} {}".format(
                    kind,
                    count,
                )
            )


if __name__ == "__main__":
    main()
