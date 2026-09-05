from pathlib import Path

import fitz


class PyMuPDFBackend:
    name = "pymupdf"

    def parse(self, pdf_path: str):
        path = Path(pdf_path)

        if not path.exists():
            raise FileNotFoundError(path)

        pages = []

        with fitz.open(path) as document:
            for index, page in enumerate(document):
                text = page.get_text("text").strip()

                blocks = []

                raw = page.get_text("dict")

                for block in raw.get("blocks", []):
                    if block.get("type") != 0:
                        continue

                    lines = []

                    for line in block.get("lines", []):
                        spans = line.get("spans", [])

                        line_text = "".join(
                            span.get("text", "")
                            for span in spans
                        ).strip()

                        if not line_text:
                            continue

                        sizes = [
                            float(span.get("size", 0))
                            for span in spans
                            if span.get("text", "").strip()
                        ]

                        lines.append(
                            {
                                "text": line_text,
                                "font_size": max(sizes) if sizes else 0.0,
                                "bbox": line.get("bbox"),
                            }
                        )

                    if lines:
                        blocks.append(
                            {
                                "lines": lines,
                                "bbox": block.get("bbox"),
                            }
                        )

                pages.append(
                    {
                        "number": index + 1,
                        "text": text,
                        "blocks": blocks,
                    }
                )

        return {
            "pages": pages,
        }
