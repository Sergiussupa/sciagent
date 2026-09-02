from typing import Iterable, List, Tuple

from ..models import ContextBlock


def estimate_tokens(text: str) -> int:
    # Conservative language-agnostic approximation suitable for an 8k budget.
    return max(1, int(len(text) / 3.2))


class ContextBudget:
    def __init__(self, total_tokens: int = 8000, output_reserve: int = 1500):
        self.total_tokens = total_tokens
        self.output_reserve = output_reserve
        self.input_budget = max(1000, total_tokens - output_reserve)

    def pack(self, blocks: Iterable[ContextBlock]) -> Tuple[str, List[str], int]:
        ordered = sorted(blocks, key=lambda b: (not b.required, -b.priority))
        selected = []
        names = []
        used = 0
        for block in ordered:
            block_text = "\n\n[%s]\n%s" % (block.name, block.text.strip())
            cost = estimate_tokens(block_text)
            if used + cost <= self.input_budget or block.required:
                selected.append(block_text)
                names.append(block.name)
                used += cost
        return "".join(selected).strip(), names, used
