import base64
import json
import os
import re
import urllib.request

import fitz


NUMBERED_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\.?\s+(.+?)\s*$"
)


def _uppercase_ratio(text):
    letters = [
        c for c in text
        if c.isalpha()
    ]

    if not letters:
        return 0.0

    return sum(c.isupper() for c in letters) / len(letters)


class GLMOCRStructureVerifier:
    """
    Lightweight visual verifier for ambiguous section candidates.

    PyMuPDF/StructureExtractor remains the primary parser.
    GLM-OCR is only consulted for uncertain candidates.
    """

    def __init__(
        self,
        model="glm-ocr:latest",
        ollama_url=None,
        timeout=60,
        verbose=False,
    ):
        self.model = model

        self.ollama_url = (
            ollama_url
            or os.getenv(
                "OLLAMA_URL",
                "http://127.0.0.1:11434",
            )
        ).rstrip("/")

        self.timeout = timeout
        self.verbose = verbose

        self.last_stats = {
            "checked": 0,
            "accepted": 0,
            "rejected": 0,
            "errors": 0,
        }

    def filter_sections(
        self,
        pdf_path,
        sections,
    ):
        output = []

        for section in sections:
            if not self.should_verify(section):
                output.append(section)
                continue

            self.last_stats["checked"] += 1

            try:
                keep = self.verify(
                    pdf_path=pdf_path,
                    page_number=section["page_start"],
                    candidate=section["title"],
                )

            except Exception as exc:
                # Fail open: visual verifier must never destroy
                # deterministic parser recall.
                self.last_stats["errors"] += 1

                if self.verbose:
                    print(
                        "[glm-ocr] ERROR:",
                        section["title"],
                        repr(exc),
                    )

                keep = True

            if keep:
                self.last_stats["accepted"] += 1
                output.append(section)

                if self.verbose:
                    print(
                        "[glm-ocr] KEEP :",
                        section["title"],
                    )

            else:
                self.last_stats["rejected"] += 1

                if self.verbose:
                    print(
                        "[glm-ocr] DROP :",
                        section["title"],
                    )

        if self.verbose:
            print(
                "[glm-ocr] stats:",
                self.last_stats,
            )

        return output

    def should_verify(
        self,
        section,
    ):
        text = section["title"]
        page_number = section["page_start"]

        match = NUMBERED_RE.match(text)

        if not match:
            return False

        number = match.group(1)
        heading = match.group(2).strip()

        # Page-one numbered text is often affiliations:
        #
        # 3 Meituan
        # 4 University of ...
        if page_number == 1:
            return True

        # Real section headings rendered in ALL CAPS are already
        # a strong deterministic signal.
        if _uppercase_ratio(heading) >= 0.70:
            return False

        parts = number.split(".")

        # Ambiguous short decimal rows are characteristic of
        # tables/model scores:
        #
        # 20.8 GPT-5.4
        # 8.3 GPT-5.2
        # 5.5 GPT
        #
        # We do NOT reject them heuristically. We ask the VLM.
        if (
            len(parts) == 2
            and len(heading) <= 28
            and any(c.isdigit() for c in heading)
        ):
            return True

        return False

    def verify(
        self,
        pdf_path,
        page_number,
        candidate,
    ):
        image = self._make_crop(
            pdf_path=pdf_path,
            page_number=page_number,
            candidate=candidate,
        )

        if image is None:
            # Could not locate line precisely.
            # Preserve recall.
            return True

        encoded = base64.b64encode(
            image
        ).decode("ascii")

        prompt = f"""
You are checking document structure in a scientific paper.

Look at the image crop and classify the candidate text.

Candidate:
{candidate}

HEADING means:
- section heading
- subsection heading
- named structural part of the scientific paper

OTHER means:
- table value or table row
- model score
- affiliation
- author information
- reference entry
- numbered instruction/list item
- ordinary body text
- figure/table content

Return exactly one word:

HEADING

or

OTHER
""".strip()

        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [encoded],
                }
            ],
            "options": {
                "temperature": 0,
            },
        }

        request = urllib.request.Request(
            self.ollama_url + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=self.timeout,
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

        answer = (
            data
            .get("message", {})
            .get("content", "")
            .strip()
            .upper()
        )

        if self.verbose:
            print(
                "[glm-ocr] raw:",
                repr(answer[:200]),
            )

        if "OTHER" in answer:
            return False

        if "HEADING" in answer:
            return True

        # Unclear model answer -> preserve recall.
        return True

    def _make_crop(
        self,
        pdf_path,
        page_number,
        candidate,
    ):
        with fitz.open(pdf_path) as pdf:
            page = pdf[page_number - 1]

            hits = page.search_for(candidate)

            # PyMuPDF occasionally differs in punctuation.
            if not hits:
                simplified = re.sub(
                    r"^\s*\d+(?:\.\d+)*\.?\s+",
                    "",
                    candidate,
                ).strip()

                if simplified:
                    hits = page.search_for(
                        simplified
                    )

            if not hits:
                return None

            rect = hits[0]

            margin_x = 60
            margin_y = 35

            clip = fitz.Rect(
                max(
                    page.rect.x0,
                    rect.x0 - margin_x,
                ),
                max(
                    page.rect.y0,
                    rect.y0 - margin_y,
                ),
                min(
                    page.rect.x1,
                    rect.x1 + margin_x,
                ),
                min(
                    page.rect.y1,
                    rect.y1 + margin_y,
                ),
            )

            pix = page.get_pixmap(
                matrix=fitz.Matrix(2.0, 2.0),
                clip=clip,
                alpha=False,
            )

            return pix.tobytes("png")
