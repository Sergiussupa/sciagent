from typing import List, Optional

from ..models import ContextBlock, PaperSection
from .budget import ContextBudget


IMPORTANT_HEADINGS = (
    "abstract", "introduction", "method", "methodology", "approach", "experiment",
    "result", "evaluation", "discussion", "conclusion", "limitation", "ablation",
)


def choose_sections(sections: List[PaperSection], max_sections: int = 6) -> List[PaperSection]:
    scored = []
    for idx, section in enumerate(sections):
        h = section.heading.lower()
        score = 0
        for term in IMPORTANT_HEADINGS:
            if term in h:
                score += 10
        if idx == 0:
            score += 2
        scored.append((score, -idx, section))
    scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
    selected = [item[2] for item in scored[:max_sections]]
    return selected


class ContextBuilder:
    def __init__(self, total_tokens: int = 8000, output_reserve: int = 1500):
        self.budget = ContextBudget(total_tokens, output_reserve)

    def paper_summary_context(self, title: str, abstract: str, sections: Optional[List[PaperSection]] = None, research_goal: str = ""):
        blocks = [
            ContextBlock("TASK", "Create a faithful structured summary of this scientific paper. Do not invent facts.", priority=100, required=True),
            ContextBlock("TITLE", title, priority=100, required=True),
            ContextBlock("ABSTRACT", abstract, priority=95, required=True),
        ]
        if research_goal:
            blocks.append(ContextBlock("RESEARCH_GOAL", research_goal, priority=90))
        if sections:
            for idx, section in enumerate(choose_sections(sections)):
                blocks.append(ContextBlock("SECTION_%02d_%s" % (idx + 1, section.heading[:60]), section.text, priority=80 - idx))
        return self.budget.pack(blocks)

    def synthesis_context(self, goal: str, paper_summaries: str, evidence_text: str, previous_synthesis: str = ""):
        blocks = [
            ContextBlock("TASK", "Synthesize the literature. Separate consensus, contradictions, limitations and open questions. Ground conclusions in the supplied evidence.", priority=100, required=True),
            ContextBlock("RESEARCH_GOAL", goal, priority=100, required=True),
            ContextBlock("PREVIOUS_SYNTHESIS", previous_synthesis, priority=70),
            ContextBlock("PAPER_SUMMARIES", paper_summaries, priority=85),
            ContextBlock("EVIDENCE", evidence_text, priority=90),
        ]
        return self.budget.pack(blocks)
