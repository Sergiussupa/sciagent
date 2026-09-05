import os
from pathlib import Path

from .models import (
    CanonicalDocument,
    DocumentPage,
    DocumentSection,
)
from .backends.pymupdf import PyMuPDFBackend
from .structure import StructureExtractor


def _main_paper_sections(sections):
    """
    DocumentParser v0.1 scope:
    main paper structure through References.

    Appendix fine structure will be handled in a later version.
    """
    output = []

    for section in sections:
        output.append(section)

        normalized = (
            section["title"]
            .strip()
            .lower()
            .rstrip(".:")
        )

        if normalized == "references":
            break

    return output


class DocumentParser:

    def __init__(
        self,
        backend=None,
        structure_extractor=None,
        structure_verifier=None,
    ):
        self.backend = (
            backend
            or PyMuPDFBackend()
        )

        self.structure_extractor = (
            structure_extractor
            or StructureExtractor()
        )

        if structure_verifier is not None:
            self.structure_verifier = (
                structure_verifier
            )

        elif os.getenv(
            "SCIAGENT_DOC_GLM_VERIFY",
            "0",
        ) == "1":

            from .verifiers import (
                GLMOCRStructureVerifier,
            )

            verbose = (
                os.getenv(
                    "SCIAGENT_DOC_GLM_VERBOSE",
                    "0",
                )
                == "1"
            )

            self.structure_verifier = (
                GLMOCRStructureVerifier(
                    verbose=verbose,
                )
            )

        else:
            self.structure_verifier = None

    def parse(
        self,
        pdf_path: str,
    ) -> CanonicalDocument:

        result = self.backend.parse(
            pdf_path
        )

        pages = [
            DocumentPage(
                number=p["number"],
                text=p["text"],
            )
            for p in result["pages"]
        ]

        title = (
            self.structure_extractor
            .extract_title(result)
        )

        abstract = (
            self.structure_extractor
            .extract_abstract(result)
        )

        raw_sections = (
            self.structure_extractor
            .extract_sections(result)
        )

        raw_sections = _main_paper_sections(
            raw_sections
        )

        if self.structure_verifier:
            raw_sections = (
                self.structure_verifier
                .filter_sections(
                    pdf_path=pdf_path,
                    sections=raw_sections,
                )
            )

        sections = [
            DocumentSection(
                title=s["title"],
                page_start=s["page_start"],
            )
            for s in raw_sections
        ]

        return CanonicalDocument(
            document_id=Path(pdf_path).stem,
            title=title,
            abstract=abstract,
            pages=pages,
            sections=sections,
        )
