import json
import re
from typing import List, Tuple

from ..models import Evidence, PaperMemory, PaperSection


SYSTEM = """You are a scientific paper analyst. Stay strictly grounded in the supplied paper text. If information is absent, use empty strings/lists. Return valid JSON only."""


PROMPT_SUFFIX = r'''

Return JSON with exactly these top-level fields:
{
  "summary": "compact but informative summary, 120-250 words",
  "research_question": "",
  "method": "",
  "datasets": [],
  "baselines": [],
  "main_results": [],
  "limitations": [],
  "evidence": [
    {
      "claim": "atomic claim supported by the paper",
      "evidence_type": "experiment|ablation|theory|observation|benchmark|claim",
      "result": "result or measurement if stated",
      "section": "section heading if known",
      "quote": "short supporting excerpt, max 30 words; empty if unavailable",
      "confidence": 0.0,
      "tags": []
    }
  ]
}
Do not add markdown fences.
'''


def _json_object(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("LLM did not return JSON")
        return json.loads(match.group(0))


def summarize_paper(llm, context_text: str, paper_id: str) -> Tuple[PaperMemory, List[Evidence]]:
    raw = llm.generate(context_text + PROMPT_SUFFIX, system=SYSTEM, json_mode=True)
    data = _json_object(raw)
    memory = PaperMemory(
        paper_id=paper_id,
        summary=str(data.get("summary", "")).strip(),
        research_question=str(data.get("research_question", "")).strip(),
        method=str(data.get("method", "")).strip(),
        datasets=[str(x) for x in (data.get("datasets") or [])],
        baselines=[str(x) for x in (data.get("baselines") or [])],
        main_results=[str(x) for x in (data.get("main_results") or [])],
        limitations=[str(x) for x in (data.get("limitations") or [])],
    )
    evidence = []
    for item in data.get("evidence") or []:
        if not isinstance(item, dict) or not item.get("claim"):
            continue
        try:
            confidence = float(item.get("confidence", 0.5))
        except Exception:
            confidence = 0.5
        evidence.append(
            Evidence(
                paper_id=paper_id,
                claim=str(item.get("claim", "")).strip(),
                evidence_type=str(item.get("evidence_type", "claim")).strip(),
                result=str(item.get("result", "")).strip(),
                section=str(item.get("section", "")).strip(),
                quote=str(item.get("quote", "")).strip(),
                confidence=max(0.0, min(1.0, confidence)),
                tags=[str(x) for x in (item.get("tags") or [])],
            )
        )
    return memory, evidence
