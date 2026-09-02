import json
from typing import List, Tuple


DEFAULT_DOMAINS = {
    "geology": ["geology", "geological", "rock", "mineral", "seismic", "tectonic", "sediment", "geochemistry"],
    "physics": ["physics", "quantum", "particle", "field theory", "condensed matter", "wave", "thermodynamic"],
    "biology": ["biology", "biological", "protein", "genome", "cell", "neural", "ecology"],
    "chemistry": ["chemistry", "chemical", "molecule", "reaction", "catalyst", "polymer"],
    "ai_agents": ["agent", "agentic", "multi-agent", "tool use", "memory agent", "autonomous agent"],
}


def heuristic_routes(title: str, abstract: str, domains=None) -> List[Tuple[str, float, str]]:
    domains = domains or DEFAULT_DOMAINS
    text = (title + " " + abstract).lower()
    out = []
    for name, keywords in domains.items():
        hits = sum(1 for keyword in keywords if keyword in text)
        if hits:
            score = min(1.0, 0.35 + hits * 0.15)
            out.append((name, score, "keyword hits: %s" % hits))
    return sorted(out, key=lambda x: x[1], reverse=True)
