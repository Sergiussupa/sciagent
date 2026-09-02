from typing import List, Optional

from ..db import Database, utcnow


class CellRegistry:
    def __init__(self, db: Database):
        self.db = db

    def create(self, name: str, description: str = "", parent: Optional[str] = None):
        with self.db.connect() as conn:
            parent_id = None
            if parent:
                row = conn.execute("SELECT id FROM research_cells WHERE name=?", (parent,)).fetchone()
                if not row:
                    raise ValueError("Unknown parent cell: %s" % parent)
                parent_id = row["id"]
            conn.execute(
                "INSERT OR IGNORE INTO research_cells(name,parent_id,description,status,created_at) VALUES(?,?,?,?,?)",
                (name, parent_id, description, "active", utcnow()),
            )
            return conn.execute("SELECT * FROM research_cells WHERE name=?", (name,)).fetchone()

    def split(self, parent: str, children: List[str]):
        self.create(parent)
        return [self.create(child, parent=parent) for child in children]

    def list(self):
        with self.db.connect() as conn:
            return conn.execute(
                """
                SELECT c.*, p.name AS parent_name,
                  (SELECT COUNT(*) FROM domain_assignments d WHERE d.cell_id=c.id) AS paper_count
                FROM research_cells c LEFT JOIN research_cells p ON p.id=c.parent_id
                ORDER BY COALESCE(c.parent_id, c.id), c.id
                """
            ).fetchall()

    def assign(self, paper_id: str, cell_name: str, score: float = 1.0, rationale: str = ""):
        cell = self.create(cell_name)
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO domain_assignments(paper_id,cell_id,score,rationale,created_at) VALUES(?,?,?,?,?)",
                (paper_id, cell["id"], score, rationale, utcnow()),
            )
