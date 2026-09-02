import asyncio
import json
from pathlib import Path
from typing import Optional

from ..browser.runtime import BrowserRuntime
from ..browser.arxiv_reader import read_arxiv_html
from ..context.builder import ContextBuilder
from ..llm.providers import make_llm
from ..research.summarizer import summarize_paper


async def run_summarize(config, db, collection_name: Optional[str] = None, limit: Optional[int] = None, deep: bool = False, force: bool = False):
    collection = db.get_collection(collection_name)
    if not collection:
        raise ValueError("Collection not found; run search first or pass --collection")
    collection_name = collection["name"]
    papers = db.collection_papers(collection_name, limit=limit)
    run_id = db.create_pipeline_run("summarize", "collection", collection_name, len(papers))
    llm = make_llm(config.llm_provider, config.model, config.ollama_url)
    context_builder = ContextBuilder(config.context_tokens, config.output_reserve)
    browser = None
    done = 0
    results = []
    try:
        if deep:
            browser = BrowserRuntime(config.arxiv_browser_delay, headless=True)
            await browser.start()
        for row in papers:
            existing = db.paper_memory(row["arxiv_id"])
            if existing and not force:
                done += 1
                db.update_pipeline_run(run_id, done)
                results.append((row["arxiv_id"], existing["summary"], "cached"))
                continue
            sections = None
            if deep:
                try:
                    title, sections, clean_text, final_url, paper_dir = await read_arxiv_html(
                        browser, row["arxiv_id"], config.artifacts_dir
                    )
                    base = Path(paper_dir)
                    db.update_paper_artifacts(
                        row["arxiv_id"],
                        str(base / "raw.html"),
                        str(base / "clean.txt"),
                        str(base / "sections.json"),
                        final_url,
                    )
                except Exception as exc:
                    # Some papers have no HTML representation; abstract-only summary remains valid.
                    sections = None
            context_text, block_names, tokens = context_builder.paper_summary_context(
                row["title"], row["abstract"], sections=sections, research_goal="Collection: %s" % collection_name
            )
            memory, evidence = summarize_paper(llm, context_text, row["arxiv_id"])
            db.save_paper_memory(memory, model="%s:%s" % (llm.name, config.model))
            db.replace_evidence(row["arxiv_id"], evidence)
            db.log_event(
                "paper.summarized",
                {"paper_id": row["arxiv_id"], "collection": collection_name, "deep": deep, "context_tokens_est": tokens, "blocks": block_names},
            )
            done += 1
            db.update_pipeline_run(run_id, done)
            results.append((row["arxiv_id"], memory.summary, llm.name))
        db.update_pipeline_run(run_id, done, status="completed", details={"llm": llm.name, "deep": deep})
        return results
    except Exception as exc:
        db.update_pipeline_run(run_id, done, status="failed", details={"error": str(exc)})
        raise
    finally:
        if browser:
            await browser.close()
