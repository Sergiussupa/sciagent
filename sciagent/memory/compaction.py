from typing import Tuple


def prune_tool_result(text: str, max_chars: int = 6000, head_chars: int = 3500, tail_chars: int = 1500) -> Tuple[str, bool]:
    """DeepSeek-Harness-style surface pruning: keep raw data elsewhere, expose bounded head/tail."""
    if len(text) <= max_chars:
        return text, False
    omitted = len(text) - head_chars - tail_chars
    compact = (
        text[:head_chars]
        + "\n\n[... %d characters omitted from working context; canonical artifact retained ...]\n\n" % omitted
        + text[-tail_chars:]
    )
    return compact, True
