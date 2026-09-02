import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .models import Evidence, Paper, PaperMemory


def utcnow():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS research_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    source TEXT NOT NULL,
    date_from TEXT,
    date_to TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    collection_id INTEGER
);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS papers (
    arxiv_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors_json TEXT NOT NULL,
    abstract TEXT NOT NULL,
    published TEXT,
    updated TEXT,
    categories_json TEXT NOT NULL,
    abs_url TEXT NOT NULL,
    pdf_url TEXT NOT NULL,
    html_url TEXT DEFAULT '',
    raw_path TEXT DEFAULT '',
    clean_path TEXT DEFAULT '',
    sections_path TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_papers (
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(arxiv_id) ON DELETE CASCADE,
    rank INTEGER,
    added_at TEXT NOT NULL,
    PRIMARY KEY(collection_id, paper_id)
);

CREATE TABLE IF NOT EXISTS paper_memory (
    paper_id TEXT PRIMARY KEY REFERENCES papers(arxiv_id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    research_question TEXT DEFAULT '',
    method TEXT DEFAULT '',
    datasets_json TEXT NOT NULL DEFAULT '[]',
    baselines_json TEXT NOT NULL DEFAULT '[]',
    main_results_json TEXT NOT NULL DEFAULT '[]',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    relevance REAL NOT NULL DEFAULT 0,
    model TEXT DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL REFERENCES papers(arxiv_id) ON DELETE CASCADE,
    claim TEXT NOT NULL,
    evidence_type TEXT DEFAULT 'claim',
    result TEXT DEFAULT '',
    section TEXT DEFAULT '',
    quote TEXT DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS synthesis_memory (
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    synthesis TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(scope_type, scope_id)
);

CREATE TABLE IF NOT EXISTS research_cells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES research_cells(id) ON DELETE SET NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS domain_assignments (
    paper_id TEXT NOT NULL REFERENCES papers(arxiv_id) ON DELETE CASCADE,
    cell_id INTEGER NOT NULL REFERENCES research_cells(id) ON DELETE CASCADE,
    score REAL NOT NULL,
    rationale TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY(paper_id, cell_id)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    status TEXT NOT NULL,
    progress_done INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = str(path)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self):
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def log_event(self, event_type: str, payload: dict):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO event_log(event_type,payload_json,created_at) VALUES(?,?,?)",
                (event_type, json.dumps(payload, ensure_ascii=False), utcnow()),
            )

    def create_collection(self, name: str, description: str = "", active: bool = True) -> int:
        with self.connect() as conn:
            if active:
                conn.execute("UPDATE collections SET active=0")
            conn.execute(
                "INSERT OR IGNORE INTO collections(name,description,created_at,active) VALUES(?,?,?,?)",
                (name, description, utcnow(), 1 if active else 0),
            )
            if active:
                conn.execute("UPDATE collections SET active=1 WHERE name=?", (name,))
            row = conn.execute("SELECT id FROM collections WHERE name=?", (name,)).fetchone()
            return int(row["id"])

    def get_collection(self, name: Optional[str] = None):
        with self.connect() as conn:
            if name:
                return conn.execute("SELECT * FROM collections WHERE name=?", (name,)).fetchone()
            return conn.execute("SELECT * FROM collections WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()

    def list_collections(self):
        with self.connect() as conn:
            return conn.execute(
                "SELECT c.*, COUNT(cp.paper_id) AS paper_count FROM collections c LEFT JOIN collection_papers cp ON cp.collection_id=c.id GROUP BY c.id ORDER BY c.id DESC"
            ).fetchall()

    def start_research_run(self, query: str, source: str, date_from: str, date_to: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO research_runs(query,source,date_from,date_to,status,created_at) VALUES(?,?,?,?,?,?)",
                (query, source, date_from, date_to, "running", utcnow()),
            )
            return int(cur.lastrowid)

    def finish_research_run(self, run_id: int, collection_id: int, status: str = "completed"):
        with self.connect() as conn:
            conn.execute(
                "UPDATE research_runs SET status=?,completed_at=?,collection_id=? WHERE id=?",
                (status, utcnow(), collection_id, run_id),
            )

    def upsert_paper(self, paper: Paper):
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO papers(arxiv_id,title,authors_json,abstract,published,updated,categories_json,abs_url,pdf_url,html_url,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(arxiv_id) DO UPDATE SET
                  title=excluded.title, authors_json=excluded.authors_json, abstract=excluded.abstract,
                  published=excluded.published, updated=excluded.updated, categories_json=excluded.categories_json,
                  abs_url=excluded.abs_url, pdf_url=excluded.pdf_url, html_url=excluded.html_url, updated_at=excluded.updated_at
                """,
                (
                    paper.arxiv_id,
                    paper.title,
                    json.dumps(paper.authors, ensure_ascii=False),
                    paper.abstract,
                    paper.published,
                    paper.updated,
                    json.dumps(paper.categories, ensure_ascii=False),
                    paper.abs_url,
                    paper.pdf_url,
                    paper.html_url,
                    now,
                    now,
                ),
            )

    def attach_paper(self, collection_id: int, paper_id: str, rank: int):
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO collection_papers(collection_id,paper_id,rank,added_at) VALUES(?,?,?,?)",
                (collection_id, paper_id, rank, utcnow()),
            )

    def collection_papers(self, collection_name: Optional[str] = None, limit: Optional[int] = None):
        collection = self.get_collection(collection_name)
        if not collection:
            return []
        sql = """
            SELECT p.*, cp.rank FROM papers p
            JOIN collection_papers cp ON cp.paper_id=p.arxiv_id
            WHERE cp.collection_id=? ORDER BY cp.rank ASC, p.published DESC
        """
        params = [collection["id"]]
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def paper(self, paper_id: str):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM papers WHERE arxiv_id=?", (paper_id,)).fetchone()

    def update_paper_artifacts(self, paper_id: str, raw_path: str, clean_path: str, sections_path: str, html_url: str = ""):
        with self.connect() as conn:
            conn.execute(
                "UPDATE papers SET raw_path=?,clean_path=?,sections_path=?,html_url=CASE WHEN ?<>'' THEN ? ELSE html_url END,updated_at=? WHERE arxiv_id=?",
                (raw_path, clean_path, sections_path, html_url, html_url, utcnow(), paper_id),
            )

    def save_paper_memory(self, memory: PaperMemory, model: str = ""):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_memory(paper_id,summary,research_question,method,datasets_json,baselines_json,main_results_json,limitations_json,relevance,model,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(paper_id) DO UPDATE SET
                  summary=excluded.summary,research_question=excluded.research_question,method=excluded.method,
                  datasets_json=excluded.datasets_json,baselines_json=excluded.baselines_json,
                  main_results_json=excluded.main_results_json,limitations_json=excluded.limitations_json,
                  relevance=excluded.relevance,model=excluded.model,updated_at=excluded.updated_at
                """,
                (
                    memory.paper_id, memory.summary, memory.research_question, memory.method,
                    json.dumps(memory.datasets, ensure_ascii=False), json.dumps(memory.baselines, ensure_ascii=False),
                    json.dumps(memory.main_results, ensure_ascii=False), json.dumps(memory.limitations, ensure_ascii=False),
                    memory.relevance, model, utcnow(),
                ),
            )

    def paper_memory(self, paper_id: str):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM paper_memory WHERE paper_id=?", (paper_id,)).fetchone()

    def add_evidence(self, evidence: Evidence):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO evidence(paper_id,claim,evidence_type,result,section,quote,confidence,tags_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    evidence.paper_id, evidence.claim, evidence.evidence_type, evidence.result,
                    evidence.section, evidence.quote, evidence.confidence,
                    json.dumps(evidence.tags, ensure_ascii=False), utcnow(),
                ),
            )

    def replace_evidence(self, paper_id: str, items: Sequence[Evidence]):
        with self.connect() as conn:
            conn.execute("DELETE FROM evidence WHERE paper_id=?", (paper_id,))
            for evidence in items:
                conn.execute(
                    "INSERT INTO evidence(paper_id,claim,evidence_type,result,section,quote,confidence,tags_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        evidence.paper_id, evidence.claim, evidence.evidence_type, evidence.result,
                        evidence.section, evidence.quote, evidence.confidence,
                        json.dumps(evidence.tags, ensure_ascii=False), utcnow(),
                    ),
                )

    def evidence_for_collection(self, collection_name: str):
        collection = self.get_collection(collection_name)
        if not collection:
            return []
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT e.*, p.title FROM evidence e
                JOIN papers p ON p.arxiv_id=e.paper_id
                JOIN collection_papers cp ON cp.paper_id=p.arxiv_id
                WHERE cp.collection_id=? ORDER BY e.id
                """,
                (collection["id"],),
            ).fetchall()

    def save_synthesis(self, scope_type: str, scope_id: str, synthesis: str, evidence_count: int):
        with self.connect() as conn:
            old = conn.execute(
                "SELECT version FROM synthesis_memory WHERE scope_type=? AND scope_id=?",
                (scope_type, scope_id),
            ).fetchone()
            version = int(old["version"]) + 1 if old else 1
            conn.execute(
                """
                INSERT INTO synthesis_memory(scope_type,scope_id,synthesis,evidence_count,version,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(scope_type,scope_id) DO UPDATE SET synthesis=excluded.synthesis,evidence_count=excluded.evidence_count,version=excluded.version,updated_at=excluded.updated_at
                """,
                (scope_type, scope_id, synthesis, evidence_count, version, utcnow()),
            )

    def get_synthesis(self, scope_type: str, scope_id: str):
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM synthesis_memory WHERE scope_type=? AND scope_id=?",
                (scope_type, scope_id),
            ).fetchone()

    def set_session(self, key: str, value: str):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO session_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, value, utcnow()),
            )

    def get_session(self, key: str, default: str = "") -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM session_state WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def create_pipeline_run(self, pipeline: str, scope_type: str, scope_id: str, total: int = 0) -> int:
        now = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO pipeline_runs(pipeline,scope_type,scope_id,status,progress_total,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (pipeline, scope_type, scope_id, "running", total, now, now),
            )
            return int(cur.lastrowid)

    def update_pipeline_run(self, run_id: int, done: int, status: Optional[str] = None, details: Optional[dict] = None):
        with self.connect() as conn:
            if status is None:
                row = conn.execute("SELECT status FROM pipeline_runs WHERE id=?", (run_id,)).fetchone()
                status = row["status"] if row else "running"
            conn.execute(
                "UPDATE pipeline_runs SET progress_done=?,status=?,details_json=?,updated_at=? WHERE id=?",
                (done, status, json.dumps(details or {}, ensure_ascii=False), utcnow(), run_id),
            )
