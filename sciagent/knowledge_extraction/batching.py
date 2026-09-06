from dataclasses import dataclass
from typing import Iterator


@dataclass
class DocumentBatch:
    batch_id: int
    page_start: int
    page_end: int
    text: str


def iter_document_batches(
    document,
    max_chars: int = 18000,
    overlap_pages: int = 1,
) -> Iterator[DocumentBatch]:
    """
    Iterate through the complete document without truncating it.

    Batches are page-aware. A single unusually large page is allowed
    to exceed max_chars rather than silently losing source text.
    """

    pages = document.pages

    if not pages:
        return

    start_index = 0
    batch_id = 1

    while start_index < len(pages):
        current = []
        current_chars = 0
        index = start_index

        while index < len(pages):
            page = pages[index]

            piece = (
                "[PAGE {}]\n{}\n".format(
                    page.number,
                    page.text,
                )
            )

            if (
                current
                and current_chars
                + len(piece)
                > max_chars
            ):
                break

            current.append(piece)
            current_chars += len(piece)
            index += 1

        # Safety for pathological input.
        if not current:
            page = pages[start_index]

            current.append(
                "[PAGE {}]\n{}\n".format(
                    page.number,
                    page.text,
                )
            )

            index = start_index + 1

        page_start = (
            pages[start_index].number
        )

        page_end = (
            pages[index - 1].number
        )

        yield DocumentBatch(
            batch_id=batch_id,
            page_start=page_start,
            page_end=page_end,
            text="\n".join(current),
        )

        batch_id += 1

        if index >= len(pages):
            break

        next_index = (
            index - overlap_pages
        )

        # Guarantee forward progress.
        start_index = max(
            start_index + 1,
            next_index,
        )
