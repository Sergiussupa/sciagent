import json
import re
from pathlib import Path
from typing import List, Tuple

from ..models import PaperSection


def _safe_id(paper_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", paper_id)


def _clean_text(text: str) -> str:
    text = text.replace("\\uselogo", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def read_arxiv_html(runtime, paper_id: str, artifacts_dir: Path) -> Tuple[str, List[PaperSection], str, str, str]:
    url = "https://arxiv.org/html/%s" % paper_id
    await runtime.goto(url)
    page = runtime.page
    final_url = page.url
    raw_html = await page.content()

    title = await page.title()
    for selector in ["h1.ltx_title_document", "article h1", "main h1", "h1"]:
        locator = page.locator(selector).first
        if await locator.count():
            try:
                value = (await locator.inner_text()).strip()
                if value:
                    title = value
                    break
            except Exception:
                pass

    # Prefer top-level LaTeXML sections to avoid nested duplication.
    selectors = [
        "section.ltx_section",
        "section.ltx_appendix",
        "article > section",
        "main > section",
    ]
    section_nodes = None
    for selector in selectors:
        nodes = page.locator(selector)
        if await nodes.count():
            section_nodes = nodes
            break

    sections = []
    if section_nodes is not None:
        for i in range(await section_nodes.count()):
            node = section_nodes.nth(i)
            heading = ""
            h = node.locator(":scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > .ltx_title").first
            if await h.count():
                try:
                    heading = (await h.inner_text()).strip()
                except Exception:
                    heading = ""
            # Direct textual content is hard in DOM; clone and remove nested sections.
            try:
                text = await node.evaluate(
                    """el => {
                        const clone = el.cloneNode(true);
                        clone.querySelectorAll('section section').forEach(n => n.remove());
                        return clone.innerText || '';
                    }"""
                )
            except Exception:
                text = await node.inner_text()
            text = _clean_text(text)
            if len(text) >= 120:
                sections.append(PaperSection(heading=heading, text=text, level=2))

    content = page.locator("article").first
    if not await content.count():
        content = page.locator("main").first
    if not await content.count():
        content = page.locator("body").first
    clean_text = _clean_text(await content.inner_text())

    paper_dir = artifacts_dir / "papers" / _safe_id(paper_id)
    paper_dir.mkdir(parents=True, exist_ok=True)
    raw_path = paper_dir / "raw.html"
    clean_path = paper_dir / "clean.txt"
    sections_path = paper_dir / "sections.json"
    raw_path.write_text(raw_html, encoding="utf-8")
    clean_path.write_text(clean_text, encoding="utf-8")
    sections_path.write_text(
        json.dumps([{"heading": s.heading, "text": s.text, "level": s.level} for s in sections], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return title, sections, clean_text, final_url, str(paper_dir)
