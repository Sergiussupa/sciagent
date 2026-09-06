import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from sciagent.config import Config
from sciagent.llm.providers import (
    OllamaLLM,
)
from sciagent.pipelines.research_run import (
    ResearchRunPipeline,
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
        "query",
        help=(
            "arXiv keyword query"
        ),
    )

    parser.add_argument(
        "--run-id",
        required=True,
    )

    parser.add_argument(
        "--max-papers",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--days",
        type=int,
        default=365,
    )

    parser.add_argument(
        "--date-from",
    )

    parser.add_argument(
        "--date-to",
    )

    parser.add_argument(
        "--model",
        default=os.getenv(
            "SCIAGENT_MODEL",
            "qwen3:14b",
        ),
    )

    args = parser.parse_args()

    today = date.today()

    date_to = (
        args.date_to
        or today.isoformat()
    )

    date_from = (
        args.date_from
        or (
            today
            - timedelta(
                days=args.days
            )
        ).isoformat()
    )

    config = Config()
    config.ensure_dirs()

    llm = OllamaLLM(
        base_url=config.ollama_url,
        model=args.model,
        timeout=600,
    )

    if not llm.available():
        raise SystemExit(
            "Ollama is not reachable at "
            + config.ollama_url
        )

    def generator(prompt):
        raw = llm.generate(
            prompt=prompt,
            system=(
                "You are SciAgent, a precise "
                "scientific knowledge extraction "
                "engine. Use only supplied evidence. "
                "Return valid JSON only."
            ),
            json_mode=True,
        )

        return parse_json(raw)

    pipeline = ResearchRunPipeline(
        config=config,
        json_generator=generator,
        model_name=args.model,
    )

    pipeline.run(
        query=args.query,
        run_id=args.run_id,
        date_from=date_from,
        date_to=date_to,
        max_papers=args.max_papers,
    )


if __name__ == "__main__":
    main()
