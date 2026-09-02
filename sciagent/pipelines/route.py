from typing import Optional

from ..cells.registry import CellRegistry
from ..cells.router import heuristic_routes


def run_route(db, collection_name: Optional[str] = None):
    collection = db.get_collection(collection_name)
    if not collection:
        raise ValueError("Collection not found")
    registry = CellRegistry(db)
    results = []
    for row in db.collection_papers(collection["name"]):
        routes = heuristic_routes(row["title"], row["abstract"])
        for cell, score, rationale in routes:
            registry.assign(row["arxiv_id"], cell, score, rationale)
        results.append((row["arxiv_id"], routes))
    db.log_event("collection.routed", {"collection": collection["name"], "papers": len(results)})
    return results
