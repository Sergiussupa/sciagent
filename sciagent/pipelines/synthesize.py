import json
from typing import Optional

from ..context.builder import ContextBuilder
from ..llm.providers import make_llm
from ..research.synthesis import build_synthesis


def run_synthesize(config, db, collection_name: Optional[str] = None, goal: str = ""):
    collection = db.get_collection(collection_name)
    if not collection:
        raise ValueError("Collection not found")
    collection_name = collection["name"]
    rows = db.collection_papers(collection_name)
    summaries = []
    with db.connect() as conn:
        for row in rows:
            pm = conn.execute("SELECT * FROM paper_memory WHERE paper_id=?", (row["arxiv_id"],)).fetchone()
            if pm:
                summaries.append("[arXiv:%s] %s\n%s" % (row["arxiv_id"], row["title"], pm["summary"]))
    evidence_rows = db.evidence_for_collection(collection_name)
    evidence_text = "\n".join(
        "[arXiv:%s] %s :: %s" % (r["paper_id"], r["claim"], r["result"] or "") for r in evidence_rows
    )
    previous = db.get_synthesis("collection", collection_name)
    previous_text = previous["synthesis"] if previous else ""
    goal = goal or ("Synthesize the scientific picture represented by collection %s" % collection_name)
    builder = ContextBuilder(config.context_tokens, config.output_reserve)
    context_text, block_names, tokens = builder.synthesis_context(
        goal, "\n\n".join(summaries), evidence_text, previous_synthesis=previous_text
    )
    llm = make_llm(config.llm_provider, config.model, config.ollama_url)
    synthesis = build_synthesis(llm, context_text)
    db.save_synthesis("collection", collection_name, synthesis, len(evidence_rows))
    db.log_event("synthesis.updated", {"collection": collection_name, "evidence_count": len(evidence_rows), "context_tokens_est": tokens})
    return synthesis
