import argparse
import asyncio
import json
import sys
from datetime import date

from .cells.registry import CellRegistry
from .config import Config
from .db import Database
from .llm.providers import make_llm
from .pipelines.route import run_route
from .pipelines.search import run_search
from .pipelines.summarize import run_summarize
from .pipelines.synthesize import run_synthesize
from .rag.answer import answer_question
from .rag.retriever import Retriever
from .memory.research_workspace import ResearchWorkspace
from .research.session import ResearchSession


def setup():
    config = Config()
    config.ensure_dirs()
    db = Database(config.db_path)
    db.init()
    return config, db


def cmd_init(args):
    config, db = setup()
    print("Initialized:", config.home)
    print("Database:", config.db_path)


def cmd_search(args):
    config, db = setup()
    papers = run_search(config, db, args.query, args.date_from, args.date_to, args.name, args.max_results)
    print("Collection:", args.name)
    print("Found:", len(papers))
    for paper in papers[: args.print_limit]:
        print("-", paper.arxiv_id, paper.published[:10], paper.title)


def cmd_collections(args):
    _, db = setup()
    rows = db.list_collections()
    if not rows:
        print("No collections")
        return
    for row in rows:
        marker = "*" if row["active"] else " "
        print("%s %-28s papers=%s created=%s" % (marker, row["name"], row["paper_count"], row["created_at"]))


def cmd_papers(args):
    _, db = setup()
    rows = db.collection_papers(args.collection, limit=args.limit)
    for row in rows:
        print("%s\t%s\t%s" % (row["arxiv_id"], (row["published"] or "")[:10], row["title"]))
    print("Total shown:", len(rows))


def cmd_summarize(args):
    config, db = setup()
    if args.provider:
        config.llm_provider = args.provider
    if args.model:
        config.model = args.model
    results = asyncio.run(run_summarize(config, db, args.collection, args.limit, args.deep, args.force))
    for paper_id, summary, source in results:
        print("\n=== %s [%s] ===\n%s" % (paper_id, source, summary))


def cmd_synthesize(args):
    config, db = setup()
    if args.provider:
        config.llm_provider = args.provider
    if args.model:
        config.model = args.model
    print(run_synthesize(config, db, args.collection, args.goal or ""))


def cmd_route(args):
    _, db = setup()
    results = run_route(db, args.collection)
    for paper_id, routes in results:
        if routes:
            print(paper_id, "->", ", ".join("%s:%.2f" % (name, score) for name, score, _ in routes))


def cmd_cells(args):
    _, db = setup()
    registry = CellRegistry(db)
    if args.cell_command == "create":
        row = registry.create(args.name, args.description or "", args.parent)
        print("Created cell:", row["name"])
    elif args.cell_command == "split":
        rows = registry.split(args.parent, args.children)
        print("Split", args.parent, "->", ", ".join(r["name"] for r in rows))
    else:
        for row in registry.list():
            print("%-20s parent=%-20s papers=%s" % (row["name"], row["parent_name"] or "-", row["paper_count"]))


def cmd_rag(args):
    config, db = setup()
    if args.provider:
        config.llm_provider = args.provider
    if args.model:
        config.model = args.model
    collection = args.collection
    if not collection:
        active = db.get_collection(None)
        collection = active["name"] if active else None
    rows = Retriever(db).search(args.question, collection_name=collection, cell_name=args.cell, limit=args.limit)
    if not rows:
        print("No relevant records found. Summarize papers first for better retrieval.")
        return
    llm = make_llm(config.llm_provider, config.model, config.ollama_url)
    print(answer_question(llm, args.question, rows))


def cmd_ask(args):
    config = Config()
    config.ensure_dirs()

    if args.provider:
        config.llm_provider = args.provider

    if args.model:
        config.model = args.model

    run_dir = (
        config.home
        / "research_runs"
        / args.run_id
    )

    workspace_path = (
        run_dir
        / "workspace.sqlite3"
    )

    manifest_path = (
        run_dir
        / "papers.json"
    )

    if not workspace_path.exists():
        raise SystemExit(
            "ResearchWorkspace not found: "
            + str(workspace_path)
        )

    if not manifest_path.exists():
        raise SystemExit(
            "ResearchRun manifest not found: "
            + str(manifest_path)
        )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    llm = make_llm(
        config.llm_provider,
        config.model,
        config.ollama_url,
    )

    with ResearchWorkspace(
        workspace_path
    ) as workspace:
        session = ResearchSession(
            workspace=workspace,
            llm=llm,
            run_id=args.run_id,
            run_dir=run_dir,
            manifest=manifest,
            max_items=args.limit,
        )

        if args.question:
            print(
                session.answer(
                    args.question
                )
            )
        else:
            session.repl()


def cmd_doctor(args):
    config, db = setup()
    print("Python:", sys.version.split()[0])
    print("State:", config.home)
    print("DB: OK")
    try:
        from playwright.async_api import async_playwright  # noqa
        print("Playwright import: OK")
    except Exception as exc:
        print("Playwright import: FAIL", exc)
    try:
        llm = make_llm(config.llm_provider, config.model, config.ollama_url)
        print("LLM:", llm.name, "model=", config.model)
    except Exception as exc:
        print("LLM: unavailable", exc)


def build_parser():
    parser = argparse.ArgumentParser(prog="sciagent", description="Extensible scientific research agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("search", help="Search arXiv and save a persistent collection")
    p.add_argument("--query", required=True)
    p.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    p.add_argument("--name", required=True)
    p.add_argument("--max", dest="max_results", type=int, default=100)
    p.add_argument("--print-limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("collections")
    p.set_defaults(func=cmd_collections)

    p = sub.add_parser("papers")
    p.add_argument("--collection")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_papers)

    p = sub.add_parser("summarize", help="Summarize papers from a saved collection; defaults to active collection")
    p.add_argument("--collection")
    p.add_argument("--limit", type=int)
    p.add_argument("--deep", action="store_true", help="Use Playwright to read full arXiv HTML; otherwise abstract-only")
    p.add_argument("--force", action="store_true")
    p.add_argument("--provider", choices=["auto", "ollama", "extractive"])
    p.add_argument("--model")
    p.set_defaults(func=cmd_summarize)

    p = sub.add_parser("synthesize", help="Build collection-level synthesis from paper memory/evidence")
    p.add_argument("--collection")
    p.add_argument("--goal")
    p.add_argument("--provider", choices=["auto", "ollama", "extractive"])
    p.add_argument("--model")
    p.set_defaults(func=cmd_synthesize)

    p = sub.add_parser("route", help="Attach papers to ResearchCells without moving/copying canonical papers")
    p.add_argument("--collection")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("cells")
    cell_sub = p.add_subparsers(dest="cell_command")
    c = cell_sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("--description")
    c.add_argument("--parent")
    c = cell_sub.add_parser("split")
    c.add_argument("parent")
    c.add_argument("children", nargs="+")
    cell_sub.add_parser("list")
    p.set_defaults(func=cmd_cells)

    p = sub.add_parser("rag", help="Ask saved paper memory/evidence; defaults to active collection")
    p.add_argument("--question", required=True)
    p.add_argument("--collection")
    p.add_argument("--cell")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--provider", choices=["auto", "ollama", "extractive"])
    p.add_argument("--model")
    p.set_defaults(func=cmd_rag)

    p = sub.add_parser(
        "ask",
        help=(
            "Ask questions against a persistent "
            "ResearchRun workspace"
        ),
    )
    p.add_argument(
        "--run-id",
        required=True,
    )
    p.add_argument(
        "--question",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=30,
    )
    p.add_argument(
        "--provider",
        choices=[
            "auto",
            "ollama",
            "extractive",
        ],
    )
    p.add_argument(
        "--model",
    )
    p.set_defaults(
        func=cmd_ask
    )

    p = sub.add_parser("doctor")
    p.set_defaults(func=cmd_doctor)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
