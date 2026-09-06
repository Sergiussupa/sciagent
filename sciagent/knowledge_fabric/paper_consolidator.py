import hashlib
import json
import re
from typing import Dict, List, Optional


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


def _normalized_text(text):
    return re.sub(
        r"\s+",
        " ",
        str(text).strip().lower(),
    )


def _sha256(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


class PaperConsolidator:
    """
    Hierarchical bounded-context reduction of raw claims.

    Raw workspace claims remain untouched.

    Intermediate reduction groups are persisted, which means a failed
    consolidation can resume without repeating already completed LLM calls.
    """

    version = "PaperConsolidator@0.1"
    contract = "PaperKnowledge@0.1"
    stage = "paper_consolidation_v01"

    def __init__(
        self,
        json_generator=None,
        group_size=8,
        max_outputs_per_group=4,
        target_claims=12,
    ):
        if json_generator is None:
            raise ValueError(
                "PaperConsolidator requires json_generator"
            )

        if group_size < 2:
            raise ValueError(
                "group_size must be >= 2"
            )

        if max_outputs_per_group < 1:
            raise ValueError(
                "max_outputs_per_group must be >= 1"
            )

        if (
            max_outputs_per_group
            >= group_size
        ):
            raise ValueError(
                "max_outputs_per_group must be "
                "smaller than group_size"
            )

        self.json_generator = json_generator
        self.group_size = group_size
        self.max_outputs_per_group = (
            max_outputs_per_group
        )
        self.target_claims = target_claims

    def run(
        self,
        workspace,
        run_id: str,
        paper_id: str,
    ) -> Dict:

        checkpoint = workspace.get_checkpoint(
            run_id=run_id,
            paper_id=paper_id,
            stage=self.stage,
        )

        if (
            checkpoint
            and checkpoint.get("status")
            == "completed"
        ):
            knowledge = (
                self.build_paper_knowledge(
                    workspace=workspace,
                    run_id=run_id,
                    paper_id=paper_id,
                )
            )

            return {
                "status": "already_completed",
                "paper_id": paper_id,
                "raw_claims": (
                    knowledge["raw_claim_count"]
                ),
                "paper_claims": len(
                    knowledge["claims"]
                ),
                "llm_calls": 0,
                "reused_groups": 0,
            }

        raw = workspace.list_artifacts(
            run_id=run_id,
            paper_id=paper_id,
            kind="claim",
        )

        nodes = [
            self._node_from_raw(item)
            for item in raw
        ]

        nodes = self._dedupe_nodes(nodes)

        cache = self._load_group_cache(
            workspace=workspace,
            run_id=run_id,
            paper_id=paper_id,
        )

        llm_calls = 0
        reused_groups = 0
        level = 0

        try:
            while (
                len(nodes)
                > self.target_claims
            ):
                next_nodes = []

                groups = [
                    nodes[index:index + self.group_size]
                    for index in range(
                        0,
                        len(nodes),
                        self.group_size,
                    )
                ]

                for group in groups:
                    if len(group) == 1:
                        next_nodes.extend(group)
                        continue

                    group_key = (
                        self._group_key(
                            level=level,
                            group=group,
                        )
                    )

                    if group_key in cache:
                        reduced = (
                            self._nodes_from_cached_group(
                                cache[group_key]
                            )
                        )

                        reused_groups += 1

                    else:
                        reduced = (
                            self._reduce_group(
                                group
                            )
                        )

                        payload = {
                            "version": self.version,
                            "paper_id": paper_id,
                            "level": level,
                            "group_key": group_key,
                            "input_node_ids": [
                                node["node_id"]
                                for node in group
                            ],
                            "claims": reduced,
                        }

                        source_pages = sorted(
                            {
                                page
                                for node in reduced
                                for page in node[
                                    "source_pages"
                                ]
                            }
                        )

                        workspace.add_artifact(
                            run_id=run_id,
                            paper_id=paper_id,
                            kind=(
                                "claim_consolidation_group"
                            ),
                            payload=payload,
                            source_pages=source_pages,
                        )

                        cache[group_key] = payload

                        llm_calls += 1

                    next_nodes.extend(reduced)

                next_nodes = (
                    self._dedupe_nodes(
                        next_nodes
                    )
                )

                if len(next_nodes) >= len(nodes):
                    # Defensive guarantee of progress.
                    next_nodes = sorted(
                        next_nodes,
                        key=lambda item: (
                            item["confidence"]
                        ),
                        reverse=True,
                    )[
                        :max(
                            1,
                            len(nodes) - 1,
                        )
                    ]

                nodes = next_nodes
                level += 1

                if level > 20:
                    raise RuntimeError(
                        "Paper consolidation failed "
                        "to converge"
                    )

            for node in nodes:
                payload = {
                    "kind": node["kind"],
                    "text": node["text"],
                    "epistemic_type": (
                        node["epistemic_type"]
                    ),
                    "confidence": (
                        node["confidence"]
                    ),
                    "source_fingerprints": (
                        node[
                            "source_fingerprints"
                        ]
                    ),
                }

                workspace.add_artifact(
                    run_id=run_id,
                    paper_id=paper_id,
                    kind="paper_claim",
                    payload=payload,
                    source_pages=(
                        node["source_pages"]
                    ),
                )

            workspace.save_checkpoint(
                run_id=run_id,
                paper_id=paper_id,
                stage=self.stage,
                last_page=None,
                status="completed",
            )

        except Exception:
            workspace.save_checkpoint(
                run_id=run_id,
                paper_id=paper_id,
                stage=self.stage,
                last_page=None,
                status="failed",
            )

            raise

        return {
            "status": "completed",
            "paper_id": paper_id,
            "raw_claims": len(raw),
            "paper_claims": len(nodes),
            "levels": level,
            "llm_calls": llm_calls,
            "reused_groups": reused_groups,
        }

    def build_paper_knowledge(
        self,
        workspace,
        run_id,
        paper_id,
    ):
        raw = workspace.list_artifacts(
            run_id=run_id,
            paper_id=paper_id,
            kind="claim",
        )

        compact = workspace.list_artifacts(
            run_id=run_id,
            paper_id=paper_id,
            kind="paper_claim",
        )

        claims = []

        for artifact in compact:
            payload = artifact["payload"]

            claims.append(
                {
                    "kind": payload["kind"],
                    "text": payload["text"],
                    "epistemic_type": (
                        payload[
                            "epistemic_type"
                        ]
                    ),
                    "source_pages": (
                        artifact[
                            "source_pages"
                        ]
                    ),
                    "source_fingerprints": (
                        payload[
                            "source_fingerprints"
                        ]
                    ),
                    "confidence": (
                        payload["confidence"]
                    ),
                }
            )

        return {
            "contract": self.contract,
            "paper_id": paper_id,
            "raw_claim_count": len(raw),
            "claims": claims,
        }

    def _node_from_raw(
        self,
        artifact,
    ):
        payload = artifact["payload"]

        return {
            "node_id": artifact[
                "fingerprint"
            ],
            "kind": payload["kind"],
            "text": payload["text"],
            "epistemic_type": payload[
                "epistemic_type"
            ],
            "confidence": float(
                payload["confidence"]
            ),
            "source_pages": list(
                artifact["source_pages"]
            ),
            "source_fingerprints": [
                artifact["fingerprint"]
            ],
        }

    def _node_id(
        self,
        claim,
    ):
        material = json.dumps(
            {
                "kind": claim["kind"],
                "text": claim["text"],
                "source_fingerprints": (
                    claim[
                        "source_fingerprints"
                    ]
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

        return _sha256(material)

    def _group_key(
        self,
        level,
        group,
    ):
        material = json.dumps(
            {
                "version": self.version,
                "level": level,
                "nodes": [
                    node["node_id"]
                    for node in group
                ],
            },
            sort_keys=True,
        )

        return _sha256(material)

    def _load_group_cache(
        self,
        workspace,
        run_id,
        paper_id,
    ):
        artifacts = (
            workspace.list_artifacts(
                run_id=run_id,
                paper_id=paper_id,
                kind=(
                    "claim_consolidation_group"
                ),
            )
        )

        cache = {}

        for artifact in artifacts:
            payload = artifact["payload"]

            if (
                payload.get("version")
                != self.version
            ):
                continue

            key = payload.get(
                "group_key"
            )

            if key:
                cache[key] = payload

        return cache

    def _nodes_from_cached_group(
        self,
        payload,
    ):
        output = []

        for claim in payload.get(
            "claims",
            [],
        ):
            node = dict(claim)

            node["node_id"] = (
                self._node_id(node)
            )

            output.append(node)

        return output

    def _reduce_group(
        self,
        group,
    ):
        prompt = self._build_prompt(
            group
        )

        result = self.json_generator(
            prompt
        )

        if isinstance(result, str):
            result = json.loads(result)

        raw_claims = result.get(
            "claims",
            [],
        )

        if not isinstance(
            raw_claims,
            list,
        ):
            raw_claims = []

        lookup = {
            "C{}".format(index): node
            for index, node in enumerate(
                group,
                start=1,
            )
        }

        reduced = []

        for item in raw_claims[
            :self.max_outputs_per_group
        ]:
            normalized = (
                self._normalize_output_claim(
                    item=item,
                    lookup=lookup,
                )
            )

            if normalized is not None:
                reduced.append(normalized)

        if not reduced:
            # Fail-open without losing all knowledge.
            fallback = sorted(
                group,
                key=lambda node: (
                    node["confidence"]
                ),
                reverse=True,
            )[
                :self.max_outputs_per_group
            ]

            return [
                dict(node)
                for node in fallback
            ]

        return reduced

    def _normalize_output_claim(
        self,
        item,
        lookup,
    ):
        if not isinstance(item, dict):
            return None

        kind = item.get("kind")

        if kind not in ALLOWED_KINDS:
            return None

        epistemic_type = item.get(
            "epistemic_type"
        )

        if (
            epistemic_type
            not in ALLOWED_EPISTEMIC_TYPES
        ):
            return None

        text = str(
            item.get("text", "")
        ).strip()

        if not text:
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

        source_ids = item.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):
            return None

        referenced = []

        for source_id in source_ids:
            node = lookup.get(
                str(source_id)
            )

            if node is not None:
                referenced.append(node)

        if not referenced:
            return None

        source_pages = sorted(
            {
                page
                for node in referenced
                for page in node[
                    "source_pages"
                ]
            }
        )

        source_fingerprints = sorted(
            {
                fingerprint
                for node in referenced
                for fingerprint in node[
                    "source_fingerprints"
                ]
            }
        )

        claim = {
            "kind": kind,
            "text": text,
            "epistemic_type": (
                epistemic_type
            ),
            "confidence": confidence,
            "source_pages": (
                source_pages
            ),
            "source_fingerprints": (
                source_fingerprints
            ),
        }

        claim["node_id"] = (
            self._node_id(claim)
        )

        return claim

    def _dedupe_nodes(
        self,
        nodes,
    ):
        output = []
        seen = set()

        for node in nodes:
            key = (
                node["kind"],
                _normalized_text(
                    node["text"]
                ),
            )

            if key in seen:
                continue

            seen.add(key)
            output.append(node)

        return output

    def _build_prompt(
        self,
        group,
    ):
        parts = []

        for index, node in enumerate(
            group,
            start=1,
        ):
            parts.append(
                """
[C%s]
kind: %s
epistemic_type: %s
pages: %s
text: %s
""".strip()
                % (
                    index,
                    node["kind"],
                    node[
                        "epistemic_type"
                    ],
                    node[
                        "source_pages"
                    ],
                    node["text"],
                )
            )

        evidence = "\n\n".join(
            parts
        )

        return """
You are consolidating one SMALL GROUP of scientific claims
from the same paper.

Do not summarize the whole paper.
Only work with the supplied claims.

Your goals:

1. Merge semantic duplicates.
2. Preserve distinct important findings.
3. Prefer scientifically central knowledge over implementation trivia.
4. Preserve important quantitative results.
5. Preserve explicit limitations.
6. Do not invent facts.

Return at most %s consolidated claims.

Return JSON only:

{
  "claims": [
    {
      "kind": "FINDING",
      "text": "...",
      "epistemic_type": "EXPERIMENTAL_RESULT",
      "source_ids": ["C1", "C3"],
      "confidence": 0.9
    }
  ]
}

source_ids MUST reference only supplied claim IDs.

If multiple claims are merged, include every input claim
that directly supports the consolidated statement.

INPUT CLAIMS:

%s
""".strip() % (
            self.max_outputs_per_group,
            evidence,
        )
