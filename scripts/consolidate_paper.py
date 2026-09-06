import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from sciagent.knowledge_fabric.paper_consolidator import (
    PaperConsolidator,
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

        if (
            start >= 0
            and end > start
        ):
            return json.loads(
                text[start:end + 1]
            )

        raise


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run-id",
        required=True,
    )

    parser.add_argument(
        "--paper-id",
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

    workspace_path = (
        ROOT
        / "state"
        / "research_runs"
        / args.run_id
        / "workspace.sqlite3"
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
                "You consolidate scientific "
                "knowledge precisely. "
                "Use only supplied claims. "
                "Return JSON only."
            ),
            json_mode=True,
        )

        return parse_json(raw)

    consolidator = PaperConsolidator(
        json_generator=generator,
        group_size=8,
        max_outputs_per_group=4,
        target_claims=12,
    )

    with ResearchWorkspace(
        workspace_path
    ) as workspace:

        result = consolidator.run(
            workspace=workspace,
            run_id=args.run_id,
            paper_id=args.paper_id,
        )

        knowledge = (
            consolidator
            .build_paper_knowledge(
                workspace=workspace,
                run_id=args.run_id,
                paper_id=args.paper_id,
            )
        )

        print()
        print("RUN")
        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

        print()
        print(
            "RAW CLAIMS:",
            knowledge[
                "raw_claim_count"
            ],
        )

        print(
            "PAPER CLAIMS:",
            len(
                knowledge["claims"]
            ),
        )

        print()

        for index, claim in enumerate(
            knowledge["claims"],
            start=1,
        ):
            print(
                "{}. [{}] {}".format(
                    index,
                    claim["kind"],
                    claim["text"],
                )
            )

            print(
                "   pages:",
                claim["source_pages"],
            )

            print(
                "   raw sources:",
                len(
                    claim[
                        "source_fingerprints"
                    ]
                ),
            )


if __name__ == "__main__":
    main()
