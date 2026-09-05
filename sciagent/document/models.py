from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DocumentPage:
    number: int
    text: str


@dataclass
class DocumentSection:
    title: str
    text: str = ""
    page_start: Optional[int] = None


@dataclass
class CanonicalDocument:
    document_id: str
    title: str = ""
    abstract: str = ""

    pages: List[DocumentPage] = field(
        default_factory=list
    )

    sections: List[DocumentSection] = field(
        default_factory=list
    )
