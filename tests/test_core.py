import tempfile
from pathlib import Path

from sciagent.context.budget import ContextBudget
from sciagent.cells.router import heuristic_routes
from sciagent.db import Database
from sciagent.models import ContextBlock, Paper
from sciagent.sources.arxiv import parse_feed


SAMPLE = '''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2608.12345v1</id>
    <updated>2026-08-20T00:00:00Z</updated>
    <published>2026-08-20T00:00:00Z</published>
    <title>Agent Memory Test</title>
    <summary>A paper about persistent memory for autonomous agents.</summary>
    <author><name>Alice</name></author>
    <category term="cs.AI" />
  </entry>
</feed>'''


def test_feed():
    papers = parse_feed(SAMPLE)
    assert len(papers) == 1
    assert papers[0].arxiv_id == "2608.12345"
    assert papers[0].title == "Agent Memory Test"


def test_db_collection_memory():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "x.sqlite3")
        db.init()
        cid = db.create_collection("august")
        paper = Paper(
            arxiv_id="2608.12345", title="Agent Memory", authors=["Alice"], abstract="test",
            published="2026-08-20T00:00:00Z", updated="2026-08-20T00:00:00Z", categories=["cs.AI"],
            abs_url="https://arxiv.org/abs/2608.12345", pdf_url="https://arxiv.org/pdf/2608.12345"
        )
        db.upsert_paper(paper)
        db.attach_paper(cid, paper.arxiv_id, 1)
        rows = db.collection_papers("august")
        assert len(rows) == 1
        assert rows[0]["title"] == "Agent Memory"


def test_context_budget():
    budget = ContextBudget(total_tokens=1000, output_reserve=200)
    text, names, used = budget.pack([
        ContextBlock("required", "x" * 500, priority=100, required=True),
        ContextBlock("optional", "y" * 5000, priority=10),
    ])
    assert "required" in names
    assert "optional" not in names


def test_router_multidomain():
    routes = heuristic_routes("Seismic wave agent", "An autonomous agent studies geological rock physics")
    names = [x[0] for x in routes]
    assert "geology" in names
    assert "physics" in names
    assert "ai_agents" in names
