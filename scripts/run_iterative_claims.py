import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from sciagent.document.parser import (
    DocumentParser,
)
from sciagent.knowledge_extraction.claims import (
    ClaimExtractor,
)
from sciagent.knowledge_extraction.claim_runtime import (
    IterativeClaimRunner,
)
from sciagent.llm.providers import (
    OllamaLLM,
)
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

    parser.add_argument(
        "pdf",
    )

    parser.add_argument(
        "--run-id",
        default="manual-research-run",
    )

    parser.add_argument(
        "--model",
        default=os.getenv(
            "SCIAGENT_MODEL",
            "qwen3:14b",
        ),
    )

    parser.add_argument(
        "--ollama-url",
        default=os.getenv(
            "OLLAMA_URL",
            "http://127.0.0.1:11434",
        ),
    )

    parser.add_argument(
        "--batch-chars",
        type=int,
        default=18000,
    )

    args = parser.parse_args()

    document = DocumentParser().parse(
        args.pdf
    )

    llm = OllamaLLM(
        base_url=args.ollama_url,
        model=args.model,
        timeout=600,
    )

    def generator(prompt):
        response = llm.generate(
            prompt,
            system=(
                "You are a precise scientific claim "
                "extraction engine. "
                "Use only supplied evidence. "
                "Return JSON only."
            ),
            json_mode=True,
        )

        return parse_json(response)

    extractor = ClaimExtractor(
        json_generator=generator
    )

    runner = IterativeClaimRunner(
        extractor=extractor,
        max_batch_chars=args.batch_chars,
        overlap_pages=1,
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

        print()
        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

        print()
        print(
            "workspace:",
            workspace_path,
        )

        print(
            "counts:",
            workspace.counts(
                args.run_id
            ),
        )

        claims = workspace.list_artifacts(
            run_id=args.run_id,
            paper_id=document.document_id,
            kind="claim",
        )

        print()
        print(
            "claims:",
            len(claims),
        )

        for item in claims:
            payload = item["payload"]

            print(
                "- [{}] {}".format(
                    payload.get(
                        "kind",
                        "?",
                    ),
                    payload.get(
                        "text",
                        "",
                    ),
                )
            )

            print(
                "  pages:",
                item["source_pages"],
            )


if __name__ == "__main__":
    main()
