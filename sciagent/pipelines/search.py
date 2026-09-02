from ..sources.arxiv import ArxivSource


def run_search(config, db, query: str, date_from: str, date_to: str, collection_name: str, max_results: int = 100):
    run_id = db.start_research_run(query, "arxiv", date_from, date_to)
    collection_id = db.create_collection(
        collection_name,
        description="arXiv search: %s (%s..%s)" % (query, date_from, date_to),
        active=True,
    )
    source = ArxivSource(config.user_agent, config.arxiv_api_delay)
    try:
        papers = source.search(query, date_from, date_to, max_results=max_results)
        for rank, paper in enumerate(papers, 1):
            db.upsert_paper(paper)
            db.attach_paper(collection_id, paper.arxiv_id, rank)
        db.finish_research_run(run_id, collection_id, "completed")
        db.set_session("active_collection", collection_name)
        db.log_event("search.completed", {"run_id": run_id, "collection": collection_name, "count": len(papers)})
        return papers
    except Exception:
        db.finish_research_run(run_id, collection_id, "failed")
        raise
