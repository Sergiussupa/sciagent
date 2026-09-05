import re
from statistics import median
from typing import Dict, List, Tuple


NUMBERED_HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\.?\s+(.+?)\s*$"
)

NUMBER_ONLY_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\.?\s*$"
)

COMMON_SECTION_NAMES = {
    "abstract",
    "introduction",
    "related work",
    "background",
    "method",
    "methods",
    "methodology",
    "approach",
    "experiments",
    "experiment",
    "experimental setup",
    "results",
    "analysis",
    "analysis and discussion",
    "discussion",
    "limitations",
    "limitation",
    "conclusion",
    "conclusions",
    "references",
    "appendix",
    "ai disclosure",
}


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip()


def _has_letters(text: str) -> bool:
    return any(char.isalpha() for char in text)


def _letter_count(text: str) -> int:
    return sum(char.isalpha() for char in text)


def _uppercase_ratio(text: str) -> float:
    letters = [
        char
        for char in text
        if char.isalpha()
    ]

    if not letters:
        return 0.0

    upper = sum(char.isupper() for char in letters)
    return upper / len(letters)


def _is_metadata_line(text: str) -> bool:
    lowered = text.lower().strip()

    if not lowered:
        return True

    if lowered.startswith("arxiv:"):
        return True

    if lowered == "preprint":
        return True

    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        lowered,
    ):
        return True

    if lowered.startswith(("http://", "https://")):
        return True

    if lowered.startswith(
        (
            "project page:",
            "code repository:",
            "app downloads:",
        )
    ):
        return True

    return False


def _is_affiliation(text: str) -> bool:
    lowered = text.lower()

    keywords = (
        "university",
        "institute",
        "laboratory",
        "laboratories",
        "college",
        "department",
        "research center",
        "research centre",
    )

    return any(
        keyword in lowered
        for keyword in keywords
    )


def _valid_section_number(number: str) -> bool:
    try:
        root = int(number.split(".", 1)[0])
    except ValueError:
        return False

    # Scientific papers rarely have top-level sections > 20.
    # This also rejects years such as "2026."
    return 1 <= root <= 20


def _page_body_font_size(page: Dict) -> float:
    sizes = []

    for block in page.get("blocks", []):
        for line in block.get("lines", []):
            text = _normalize(line.get("text", ""))
            size = float(line.get("font_size", 0))

            if (
                len(text) >= 20
                and size > 0
                and _has_letters(text)
            ):
                sizes.append(size)

    if not sizes:
        return 0.0

    return float(median(sizes))


def _line_y(line: Dict) -> float:
    bbox = line.get("bbox")

    if not bbox:
        return 0.0

    return float(bbox[1])


class StructureExtractor:

    def extract_title(
        self,
        backend_result: Dict,
    ) -> str:
        pages = backend_result.get("pages", [])

        if not pages:
            return ""

        candidates: List[Dict] = []

        for block in pages[0].get("blocks", []):
            for line in block.get("lines", []):
                text = _normalize(line.get("text", ""))
                size = float(line.get("font_size", 0))

                if len(text) < 5:
                    continue

                if _letter_count(text) < 3:
                    continue

                if _is_metadata_line(text):
                    continue

                candidates.append(
                    {
                        "text": text,
                        "font_size": size,
                        "y": _line_y(line),
                    }
                )

        if not candidates:
            return ""

        max_size = max(
            item["font_size"]
            for item in candidates
        )

        # Title often spans 2–3 lines with nearly identical size.
        title_lines = [
            item
            for item in candidates
            if item["font_size"] >= max_size * 0.92
        ]

        title_lines.sort(
            key=lambda item: item["y"]
        )

        title = " ".join(
            item["text"]
            for item in title_lines
        )

        return _normalize(title)

    def extract_abstract(
        self,
        backend_result: Dict,
    ) -> str:
        pages = backend_result.get("pages", [])

        if not pages:
            return ""

        full_text = "\n".join(
            page["text"]
            for page in pages[:3]
        )

        # Normal explicit Abstract heading.
        patterns = [
            (
                r"(?is)\babstract\b\s*[:—\-]?\s*"
                r"(.+?)"
                r"(?=\n\s*(?:1[\.\s]+)?introduction\b)"
            ),
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                full_text,
            )

            if match:
                abstract = _normalize(
                    match.group(1)
                )

                if len(abstract) >= 100:
                    return abstract

        # Some papers visually format the abstract without
        # an explicit "Abstract" label.
        #
        # v0.2 fallback:
        # choose the largest prose block on page 1.
        candidates: List[str] = []

        for block in pages[0].get("blocks", []):
            lines = [
                _normalize(line.get("text", ""))
                for line in block.get("lines", [])
            ]

            lines = [
                line
                for line in lines
                if line
            ]

            if not lines:
                continue

            text = _normalize(
                " ".join(lines)
            )

            if len(text) < 400:
                continue

            lowered = text.lower()

            if lowered.startswith(
                ("figure ", "table ")
            ):
                continue

            if _is_metadata_line(text):
                continue

            letters = _letter_count(text)

            if letters < len(text) * 0.45:
                continue

            candidates.append(text)

        if candidates:
            return max(
                candidates,
                key=len,
            )

        return ""

    def extract_sections(
        self,
        backend_result: Dict,
    ):
        sections = []
        seen = set()

        for page in backend_result.get("pages", []):
            body_size = _page_body_font_size(page)

            lines = []

            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    text = _normalize(
                        line.get("text", "")
                    )

                    if not text:
                        continue

                    lines.append(
                        {
                            "text": text,
                            "font_size": float(
                                line.get(
                                    "font_size",
                                    0,
                                )
                            ),
                            "bbox": line.get("bbox"),
                        }
                    )

            index = 0

            while index < len(lines):
                line = lines[index]
                text = line["text"]

                # Case 1:
                # complete numbered heading:
                #
                # 3.1. Experimental Setup
                match = NUMBERED_HEADING_RE.match(text)

                if match:
                    number = match.group(1)
                    heading = _normalize(
                        match.group(2)
                    )

                    if self._valid_numbered_heading(
                        number=number,
                        heading=heading,
                        page_number=page["number"],
                    ):
                        self._append_section(
                            sections=sections,
                            seen=seen,
                            title=text,
                            page_number=page["number"],
                        )

                        index += 1
                        continue

                # Case 2:
                # PDF split numbering and title:
                #
                # 3.1
                # SPATIAL AGENCY IN CLOSED-LOOP ...
                number_match = NUMBER_ONLY_RE.match(
                    text
                )

                if (
                    number_match
                    and index + 1 < len(lines)
                ):
                    number = number_match.group(1)
                    next_line = lines[index + 1]

                    if (
                        _valid_section_number(number)
                        and self._can_merge_number_heading(
                            number_line=line,
                            heading_line=next_line,
                            body_size=body_size,
                        )
                    ):
                        combined = (
                            f"{number} "
                            f"{next_line['text']}"
                        )

                        self._append_section(
                            sections=sections,
                            seen=seen,
                            title=combined,
                            page_number=page["number"],
                        )

                        index += 2
                        continue

                # Case 3:
                # unnumbered headings:
                #
                # ABSTRACT
                # LIMITATIONS
                # REFERENCES
                if self._looks_like_unnumbered_heading(
                    text=text,
                    font_size=line["font_size"],
                    body_size=body_size,
                ):
                    self._append_section(
                        sections=sections,
                        seen=seen,
                        title=text,
                        page_number=page["number"],
                    )

                index += 1

        return sections

    def _append_section(
        self,
        sections: List[Dict],
        seen: set,
        title: str,
        page_number: int,
    ) -> None:
        title = _normalize(title)

        key = re.sub(
            r"\s+",
            " ",
            title.lower(),
        )

        if key in seen:
            return

        seen.add(key)

        sections.append(
            {
                "title": title,
                "page_start": page_number,
            }
        )

    def _valid_numbered_heading(
        self,
        number: str,
        heading: str,
        page_number: int,
    ) -> bool:
        if not _valid_section_number(number):
            return False

        if len(heading) > 140:
            return False

        if _letter_count(heading) < 3:
            return False

        # Reject common author-affiliation numbering.
        if (
            page_number == 1
            and _is_affiliation(heading)
        ):
            return False

        # A heading cannot start with punctuation/numeric
        # continuation such as:
        #
        # 5.1, 10.0, 5.8 ...
        if not heading[0].isalnum():
            return False

        return True

    def _can_merge_number_heading(
        self,
        number_line: Dict,
        heading_line: Dict,
        body_size: float,
    ) -> bool:
        heading = heading_line["text"]

        if len(heading) > 160:
            return False

        if _letter_count(heading) < 3:
            return False

        if _is_metadata_line(heading):
            return False

        number_y = _line_y(number_line)
        heading_y = _line_y(heading_line)

        # Split heading pieces should be spatially close.
        if (
            number_y
            and heading_y
            and abs(heading_y - number_y) > 35
        ):
            return False

        normalized = heading.lower().rstrip(".:")

        if normalized in COMMON_SECTION_NAMES:
            return True

        # Many conference templates render headings in caps.
        if _uppercase_ratio(heading) >= 0.70:
            return True

        size = float(
            heading_line.get(
                "font_size",
                0,
            )
        )

        if (
            body_size > 0
            and size >= body_size * 1.03
        ):
            return True

        # Research-question headings are common in papers.
        if re.match(
            r"(?i)^rq\d+\s*[:.]",
            heading,
        ):
            return True

        return False

    def _looks_like_unnumbered_heading(
        self,
        text: str,
        font_size: float,
        body_size: float,
    ) -> bool:
        text = _normalize(text)

        if not text:
            return False

        if len(text) > 100:
            return False

        normalized = text.lower().rstrip(".:")

        if normalized not in COMMON_SECTION_NAMES:
            return False

        # Uppercase section headings are a strong signal.
        if _uppercase_ratio(text) >= 0.70:
            return True

        # Otherwise require a layout signal so that table
        # column headers such as "Method" are not accepted.
        if (
            body_size > 0
            and font_size >= body_size * 1.03
        ):
            return True

        return False
