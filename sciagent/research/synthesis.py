from typing import Iterable, Tuple

from ..models import ContextBlock


SYSTEM = """You synthesize scientific literature. Never convert a single paper into consensus. Explicitly distinguish supporting evidence, contradictions, uncertainty, methodological limitations and open questions."""


def build_synthesis(llm, context_text: str) -> str:
    prompt = context_text + """

Write a compact synthesis with these headings:
1. Current picture
2. Strongest recurring findings
3. Contradictions / boundary conditions
4. Methodological weaknesses
5. Open questions
6. Papers that matter most
Use arXiv IDs when available. Do not invent evidence.
"""
    return llm.generate(prompt, system=SYSTEM, json_mode=False).strip()
