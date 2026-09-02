from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Paper:
    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    published: str
    updated: str
    categories: List[str]
    abs_url: str
    pdf_url: str
    html_url: str = ""


@dataclass
class PaperSection:
    heading: str
    text: str
    level: int = 2


@dataclass
class PaperMemory:
    paper_id: str
    summary: str
    research_question: str = ""
    method: str = ""
    datasets: List[str] = field(default_factory=list)
    baselines: List[str] = field(default_factory=list)
    main_results: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    relevance: float = 0.0


@dataclass
class Evidence:
    paper_id: str
    claim: str
    evidence_type: str = "claim"
    result: str = ""
    section: str = ""
    quote: str = ""
    confidence: float = 0.5
    tags: List[str] = field(default_factory=list)


@dataclass
class DomainAssignment:
    paper_id: str
    cell_name: str
    score: float
    rationale: str = ""


@dataclass
class ContextBlock:
    name: str
    text: str
    priority: int = 50
    required: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)
