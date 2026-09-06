import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


def _now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_pages(pages):
    if not pages:
        return []

    return sorted(
        {
            int(page)
            for page in pages
            if int(page) >= 1
        }
    )


class ResearchWorkspace:
    """
    Persistent temporary knowledge base scoped to a ResearchRun.

    This is memory, not LLM context.

    The workspace stores structured artifacts incrementally while a
    research task is running. A later reconciliation stage decides what
    should be promoted into long-term SciAgent knowledge.
    """

    def __init__(self, path):
        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.connection = sqlite3.connect(
            str(self.path)
        )

        self.connection.row_factory = (
            sqlite3.Row
        )

        self._initialize()

    def _initialize(self):
        self.connection.execute(
            "PRAGMA journal_mode=WAL"
        )

        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source_pages_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,

                UNIQUE(run_id, fingerprint)
            )
            """
        )

        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_workspace_artifacts_run
            ON artifacts(run_id)
            """
        )

        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_workspace_artifacts_paper
            ON artifacts(run_id, paper_id)
            """
        )

        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_workspace_artifacts_kind
            ON artifacts(run_id, kind)
            """
        )

        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                run_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                last_page INTEGER,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                PRIMARY KEY (
                    run_id,
                    paper_id,
                    stage
                )
            )
            """
        )

        self.connection.commit()

    def _fingerprint(
        self,
        paper_id,
        kind,
        payload,
    ):
        material = (
            str(paper_id)
            + "\n"
            + str(kind)
            + "\n"
            + _canonical_json(payload)
        )

        return hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()

    def add_artifact(
        self,
        run_id: str,
        paper_id: str,
        kind: str,
        payload: Dict,
        source_pages: Optional[List[int]] = None,
    ) -> str:
        """
        Append one structured knowledge artifact.

        Identical artifacts inside one run are deduplicated.
        If the same artifact is observed on additional pages,
        provenance pages are merged.
        """

        pages = _normalize_pages(
            source_pages
        )

        fingerprint = self._fingerprint(
            paper_id=paper_id,
            kind=kind,
            payload=payload,
        )

        existing = self.connection.execute(
            """
            SELECT id, source_pages_json
            FROM artifacts
            WHERE run_id = ?
              AND fingerprint = ?
            """,
            (
                run_id,
                fingerprint,
            ),
        ).fetchone()

        if existing is not None:
            old_pages = json.loads(
                existing[
                    "source_pages_json"
                ]
            )

            merged_pages = _normalize_pages(
                old_pages + pages
            )

            self.connection.execute(
                """
                UPDATE artifacts
                SET source_pages_json = ?
                WHERE id = ?
                """,
                (
                    _canonical_json(
                        merged_pages
                    ),
                    existing["id"],
                ),
            )

            self.connection.commit()

            return fingerprint

        self.connection.execute(
            """
            INSERT INTO artifacts (
                run_id,
                paper_id,
                kind,
                payload_json,
                source_pages_json,
                fingerprint,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                paper_id,
                kind,
                _canonical_json(payload),
                _canonical_json(pages),
                fingerprint,
                _now(),
            ),
        )

        self.connection.commit()

        return fingerprint

    def list_artifacts(
        self,
        run_id: str,
        paper_id: Optional[str] = None,
        kind: Optional[str] = None,
    ):
        clauses = [
            "run_id = ?"
        ]

        params = [
            run_id
        ]

        if paper_id is not None:
            clauses.append(
                "paper_id = ?"
            )
            params.append(
                paper_id
            )

        if kind is not None:
            clauses.append(
                "kind = ?"
            )
            params.append(
                kind
            )

        query = """
            SELECT *
            FROM artifacts
            WHERE {}
            ORDER BY id
        """.format(
            " AND ".join(clauses)
        )

        rows = self.connection.execute(
            query,
            params,
        ).fetchall()

        output = []

        for row in rows:
            output.append(
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "paper_id": row["paper_id"],
                    "kind": row["kind"],
                    "payload": json.loads(
                        row["payload_json"]
                    ),
                    "source_pages": json.loads(
                        row[
                            "source_pages_json"
                        ]
                    ),
                    "fingerprint": row[
                        "fingerprint"
                    ],
                    "created_at": row[
                        "created_at"
                    ],
                }
            )

        return output

    def save_checkpoint(
        self,
        run_id: str,
        paper_id: str,
        stage: str,
        last_page: Optional[int],
        status: str,
    ):
        self.connection.execute(
            """
            INSERT INTO checkpoints (
                run_id,
                paper_id,
                stage,
                last_page,
                status,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(
                run_id,
                paper_id,
                stage
            )
            DO UPDATE SET
                last_page = excluded.last_page,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                run_id,
                paper_id,
                stage,
                last_page,
                status,
                _now(),
            ),
        )

        self.connection.commit()

    def get_checkpoint(
        self,
        run_id: str,
        paper_id: str,
        stage: str,
    ):
        row = self.connection.execute(
            """
            SELECT *
            FROM checkpoints
            WHERE run_id = ?
              AND paper_id = ?
              AND stage = ?
            """,
            (
                run_id,
                paper_id,
                stage,
            ),
        ).fetchone()

        if row is None:
            return None

        return dict(row)

    def counts(
        self,
        run_id: str,
    ):
        rows = self.connection.execute(
            """
            SELECT kind, COUNT(*) AS count
            FROM artifacts
            WHERE run_id = ?
            GROUP BY kind
            ORDER BY kind
            """,
            (run_id,),
        ).fetchall()

        return {
            row["kind"]: row["count"]
            for row in rows
        }

    def snapshot(
        self,
        run_id: str,
    ):
        checkpoint_rows = (
            self.connection.execute(
                """
                SELECT *
                FROM checkpoints
                WHERE run_id = ?
                ORDER BY paper_id, stage
                """,
                (run_id,),
            ).fetchall()
        )

        return {
            "run_id": run_id,
            "counts": self.counts(
                run_id
            ),
            "artifacts": self.list_artifacts(
                run_id
            ),
            "checkpoints": [
                dict(row)
                for row
                in checkpoint_rows
            ],
        }

    def delete_run(
        self,
        run_id: str,
    ):
        self.connection.execute(
            """
            DELETE FROM artifacts
            WHERE run_id = ?
            """,
            (run_id,),
        )

        self.connection.execute(
            """
            DELETE FROM checkpoints
            WHERE run_id = ?
            """,
            (run_id,),
        )

        self.connection.commit()

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.close()
