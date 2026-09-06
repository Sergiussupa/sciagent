import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ARTIFACT_KINDS = (
    "paper_claim",
    "research_question",
    "method",
    "system",
    "dataset",
    "model",
    "baseline",
    "task",
    "metric",
    "condition",
)

KIND_WEIGHT = {
    "paper_claim": 8.0,
    "research_question": 6.0,
    "method": 5.0,
    "system": 5.0,
    "dataset": 3.0,
    "model": 3.0,
    "baseline": 3.0,
    "task": 3.0,
    "metric": 2.0,
    "condition": 2.0,
}


def _words(text):
    return re.findall(
        r"[A-Za-z0-9][A-Za-z0-9_.+-]{1,}",
        str(text).lower(),
    )


def _payload_text(kind, payload):
    if kind == "paper_claim":
        return str(
            payload.get("text", "")
        )

    if kind == "research_question":
        return str(
            payload.get("text", "")
        )

    return "{} {}".format(
        payload.get("name", ""),
        payload.get("description", ""),
    ).strip()


class ResearchSession:
    """
    Conversational interface over one persistent ResearchWorkspace.

    The workspace and dialogue history may grow indefinitely.
    Only bounded relevant evidence is supplied to the LLM per turn.
    """

    def __init__(
        self,
        workspace,
        llm,
        run_id,
        run_dir,
        manifest,
        max_items=30,
        max_context_chars=24000,
    ):
        self.workspace = workspace
        self.llm = llm
        self.run_id = run_id
        self.run_dir = Path(run_dir)
        self.manifest = manifest
        self.max_items = max_items
        self.max_context_chars = (
            max_context_chars
        )

        self.history_path = (
            self.run_dir
            / "chat_history.jsonl"
        )

        self.paper_info = {}

        for paper in manifest.get(
            "papers",
            [],
        ):
            arxiv_id = paper.get(
                "arxiv_id",
                "",
            )

            document_id = paper.get(
                "document_id",
                arxiv_id,
            )

            info = {
                "arxiv_id": arxiv_id,
                "title": paper.get(
                    "title",
                    "",
                ),
                "status": paper.get(
                    "status",
                    "",
                ),
            }

            if arxiv_id:
                self.paper_info[
                    arxiv_id
                ] = info

            if document_id:
                self.paper_info[
                    document_id
                ] = info

    def _load_history(self):
        if not self.history_path.exists():
            return []

        history = []

        for line in (
            self.history_path
            .read_text(
                encoding="utf-8"
            )
            .splitlines()
        ):
            line = line.strip()

            if not line:
                continue

            try:
                history.append(
                    json.loads(line)
                )
            except json.JSONDecodeError:
                continue

        return history

    def _append_history(
        self,
        role,
        content,
    ):
        record = {
            "timestamp": (
                datetime.now()
                .isoformat(
                    timespec="seconds"
                )
            ),
            "role": role,
            "content": content,
        }

        with self.history_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    def _recent_dialogue(
        self,
        limit=6,
    ):
        history = (
            self._load_history()
        )[-limit:]

        if not history:
            return "(no previous dialogue)"

        return "\n".join(
            "{}: {}".format(
                item.get(
                    "role",
                    "?",
                ).upper(),
                item.get(
                    "content",
                    "",
                ),
            )
            for item in history
        )

    def _plan_query(
        self,
        question,
    ):
        original_query = (
            self.manifest.get(
                "query",
                "",
            )
        )

        prompt = """
Convert the user's research question into retrieval terms
for scientific knowledge extracted from papers.

The stored scientific knowledge is mostly in English.
The user may ask in Russian or another language.

Use the recent dialogue to resolve references such as
"these methods", "which of them", "and what about this".

Research corpus topic:
%s

Recent dialogue:
%s

Current question:
%s

Return JSON only:

{
  "scope": "broad",
  "terms": [
    "event camera",
    "neuromorphic vision"
  ]
}

scope:
- "broad" for overview, comparison across the corpus,
  main technologies, main findings, trends, common problems.
- "focused" for a specific technology, method, claim,
  dataset, paper or narrow follow-up.

Return 6-15 concise English scientific search terms.
Include useful synonyms where appropriate.
Do not answer the research question.
""".strip() % (
            original_query,
            self._recent_dialogue(),
            question,
        )

        try:
            raw = self.llm.generate(
                prompt,
                system=(
                    "You are a scientific "
                    "retrieval query planner. "
                    "Return valid JSON only."
                ),
                json_mode=True,
            )

            if isinstance(raw, str):
                result = json.loads(raw)
            else:
                result = raw

            terms = [
                str(term).strip().lower()
                for term in result.get(
                    "terms",
                    [],
                )
                if str(term).strip()
            ]

            scope = result.get(
                "scope",
                "focused",
            )

            if (
                scope
                not in (
                    "broad",
                    "focused",
                )
            ):
                scope = "focused"

            if terms:
                return {
                    "scope": scope,
                    "terms": terms[:15],
                }

        except Exception:
            pass

        # Deterministic fallback.
        fallback = _words(
            "{} {}".format(
                original_query,
                question,
            )
        )

        return {
            "scope": "broad",
            "terms": list(
                dict.fromkeys(
                    fallback
                )
            )[:15],
        }

    def _score(
        self,
        kind,
        text,
        title,
        terms,
    ):
        haystack = (
            "{} {}"
            .format(
                title,
                text,
            )
            .lower()
        )

        haystack_words = set(
            _words(haystack)
        )

        score = 0.0

        for term in terms:
            term = term.lower()

            if term in haystack:
                score += 5.0

            for word in _words(term):
                if word in haystack_words:
                    score += 1.0

        if score > 0:
            score += KIND_WEIGHT.get(
                kind,
                1.0,
            )

        return score

    def _collect_candidates(
        self,
        terms,
    ):
        candidates = []

        for kind in ARTIFACT_KINDS:
            artifacts = (
                self.workspace
                .list_artifacts(
                    run_id=self.run_id,
                    kind=kind,
                )
            )

            for artifact in artifacts:
                payload = artifact.get(
                    "payload",
                    {},
                )

                paper_id = artifact.get(
                    "paper_id",
                    "",
                )

                info = self.paper_info.get(
                    paper_id,
                    {},
                )

                title = info.get(
                    "title",
                    "",
                )

                text = _payload_text(
                    kind,
                    payload,
                )

                if not text:
                    continue

                score = self._score(
                    kind=kind,
                    text=text,
                    title=title,
                    terms=terms,
                )

                candidates.append(
                    {
                        "score": score,
                        "kind": kind,
                        "paper_id": paper_id,
                        "title": title,
                        "text": text,
                        "pages": artifact.get(
                            "source_pages",
                            [],
                        ),
                    }
                )

        return candidates

    def _retrieve(
        self,
        plan,
    ):
        candidates = (
            self._collect_candidates(
                plan["terms"]
            )
        )

        candidates.sort(
            key=lambda item: (
                item["score"],
                KIND_WEIGHT.get(
                    item["kind"],
                    1.0,
                ),
            ),
            reverse=True,
        )

        selected = []
        selected_keys = set()
        per_paper = defaultdict(int)

        # For broad questions make sure the model sees
        # at least one compact claim from each paper.
        if plan["scope"] == "broad":
            by_paper = {}

            for item in candidates:
                if (
                    item["kind"]
                    != "paper_claim"
                ):
                    continue

                paper_id = item[
                    "paper_id"
                ]

                current = by_paper.get(
                    paper_id
                )

                if (
                    current is None
                    or item["score"]
                    > current["score"]
                ):
                    by_paper[
                        paper_id
                    ] = item

            for item in by_paper.values():
                key = (
                    item["paper_id"],
                    item["kind"],
                    item["text"],
                )

                selected.append(item)
                selected_keys.add(key)
                per_paper[
                    item["paper_id"]
                ] += 1

                if (
                    len(selected)
                    >= self.max_items
                ):
                    break

        cap_per_paper = (
            4
            if plan["scope"]
            == "broad"
            else 7
        )

        for item in candidates:
            if (
                len(selected)
                >= self.max_items
            ):
                break

            if item["score"] <= 0:
                continue

            key = (
                item["paper_id"],
                item["kind"],
                item["text"],
            )

            if key in selected_keys:
                continue

            if (
                per_paper[
                    item["paper_id"]
                ]
                >= cap_per_paper
            ):
                continue

            selected.append(item)
            selected_keys.add(key)
            per_paper[
                item["paper_id"]
            ] += 1

        return selected

    def _context_text(
        self,
        items,
    ):
        blocks = []
        total_chars = 0

        for index, item in enumerate(
            items,
            start=1,
        ):
            pages = (
                ",".join(
                    str(page)
                    for page in item[
                        "pages"
                    ]
                )
                or "?"
            )

            block = (
                "[K{}]\n"
                "paper_id: {}\n"
                "title: {}\n"
                "kind: {}\n"
                "pages: {}\n"
                "knowledge: {}\n"
            ).format(
                index,
                item["paper_id"],
                item["title"],
                item["kind"],
                pages,
                item["text"],
            )

            if (
                blocks
                and total_chars
                + len(block)
                > self.max_context_chars
            ):
                break

            blocks.append(block)
            total_chars += len(block)

        return "\n".join(blocks)

    def answer(
        self,
        question,
    ):
        plan = self._plan_query(
            question
        )

        items = self._retrieve(
            plan
        )

        if not items:
            return (
                "В текущей ResearchWorkspace "
                "не найдено достаточно знаний "
                "для ответа."
            )

        context = self._context_text(
            items
        )

        recent_dialogue = (
            self._recent_dialogue()
        )

        prompt = """
You are answering a question inside a persistent
scientific research session.

Use ONLY the retrieved knowledge below.
Do not invent findings that are absent from it.

The user may ask in Russian.
Answer in the same language as the user's question.

Important rules:

1. Synthesize across papers when the evidence permits it.
2. Distinguish paper findings from your cross-paper synthesis.
3. If evidence is weak or incomplete, say so.
4. Do not imply that every paper supports a conclusion
   unless the retrieved evidence shows that.
5. Cite supporting knowledge markers like [K3] or [K2][K7].
6. Prefer concrete technologies, methods, quantitative
   findings and limitations over vague generalities.
7. A follow-up question may rely on recent dialogue,
   but factual support must come from retrieved knowledge.

Research session:
%s

Original corpus query:
%s

Recent dialogue:
%s

Current question:
%s

Retrieved scientific knowledge:

%s
""".strip() % (
            self.run_id,
            self.manifest.get(
                "query",
                "",
            ),
            recent_dialogue,
            question,
            context,
        )

        answer = self.llm.generate(
            prompt,
            system=(
                "You are SciAgent, an "
                "evidence-grounded scientific "
                "research assistant."
            ),
        ).strip()

        self._append_history(
            "user",
            question,
        )

        self._append_history(
            "assistant",
            answer,
        )

        return answer

    def status_text(self):
        counts = self.workspace.counts(
            self.run_id
        )

        completed = sum(
            1
            for paper in self.manifest.get(
                "papers",
                [],
            )
            if paper.get(
                "status"
            ) == "completed"
        )

        lines = [
            "run_id: {}".format(
                self.run_id
            ),
            "papers: {}".format(
                completed
            ),
        ]

        for kind in ARTIFACT_KINDS:
            count = counts.get(
                kind,
                0,
            )

            if count:
                lines.append(
                    "{}: {}".format(
                        kind,
                        count,
                    )
                )

        return "\n".join(lines)

    def papers_text(self):
        lines = []

        for index, paper in enumerate(
            self.manifest.get(
                "papers",
                [],
            ),
            start=1,
        ):
            lines.append(
                "{}. {} | {}".format(
                    index,
                    paper.get(
                        "arxiv_id",
                        "?",
                    ),
                    paper.get(
                        "title",
                        "",
                    ),
                )
            )

        return "\n".join(lines)

    def repl(self):
        print()
        print(
            "SciAgent research session:",
            self.run_id,
        )

        print(
            "Papers:",
            sum(
                1
                for paper
                in self.manifest.get(
                    "papers",
                    [],
                )
                if paper.get(
                    "status"
                ) == "completed"
            ),
        )

        print()
        print(
            "Ask questions about the "
            "existing ResearchWorkspace."
        )

        print(
            "Commands: :status  :papers  "
            ":help  :quit"
        )

        while True:
            try:
                question = input(
                    "\nsciagent> "
                ).strip()

            except (
                EOFError,
                KeyboardInterrupt,
            ):
                print()
                break

            if not question:
                continue

            if question in (
                ":quit",
                ":exit",
                "quit",
                "exit",
            ):
                break

            if question == ":status":
                print(
                    self.status_text()
                )
                continue

            if question == ":papers":
                print(
                    self.papers_text()
                )
                continue

            if question == ":help":
                print(
                    "Type a research question. "
                    "The same workspace and "
                    "dialogue history are reused."
                )
                print(
                    ":status - workspace summary"
                )
                print(
                    ":papers - paper list"
                )
                print(
                    ":quit   - leave session"
                )
                continue

            try:
                print()
                print(
                    self.answer(
                        question
                    )
                )

            except Exception as exc:
                print(
                    "\nERROR: {}: {}".format(
                        type(exc).__name__,
                        exc,
                    )
                )
