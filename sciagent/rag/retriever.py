import re
from typing import Optional

from ..db import Database


def _terms(question: str):
    return [
        x.lower()
        for x in re.findall(
            r"[A-Za-zА-Яа-я0-9_-]{3,}",
            question,
        )
    ]


class Retriever:
    def __init__(self, db: Database):
        self.db = db

    def search(
        self,
        question: str,
        collection_name: Optional[str] = None,
        cell_name: Optional[str] = None,
        limit: int = 8,
    ):
        terms = _terms(question)

        rows = []

        with self.db.connect() as conn:

            sql = """
                SELECT
                    p.arxiv_id,
                    p.title,
                    p.abstract,
                    pm.summary,
                    pm.main_results_json,
                    GROUP_CONCAT(
                        e.claim,
                        ' | '
                    ) AS evidence_claims

                FROM papers p

                LEFT JOIN paper_memory pm
                    ON pm.paper_id=p.arxiv_id

                LEFT JOIN evidence e
                    ON e.paper_id=p.arxiv_id
            """

            joins = []
            where = []
            params = []

            if collection_name:
                joins.append(
                    """
                    JOIN collection_papers cp
                        ON cp.paper_id=p.arxiv_id

                    JOIN collections c
                        ON c.id=cp.collection_id
                    """
                )

                where.append("c.name=?")
                params.append(collection_name)

            if cell_name:
                joins.append(
                    """
                    JOIN domain_assignments da
                        ON da.paper_id=p.arxiv_id

                    JOIN research_cells rc
                        ON rc.id=da.cell_id
                    """
                )

                where.append("rc.name=?")
                params.append(cell_name)

            sql += " " + " ".join(joins)

            if where:
                sql += (
                    " WHERE "
                    + " AND ".join(where)
                )

            sql += " GROUP BY p.arxiv_id"

            candidates = conn.execute(
                sql,
                tuple(params),
            ).fetchall()

        for row in candidates:

            hay = " ".join(
                [
                    row["title"] or "",
                    row["abstract"] or "",
                    row["summary"] or "",
                    row["evidence_claims"] or "",
                ]
            ).lower()

            score = sum(
                hay.count(term)
                for term in terms
            )

            if score:
                rows.append(
                    (score, row)
                )

        rows.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        if rows:
            return [
                row
                for _, row
                in rows[:limit]
            ]

        # Cross-language fallback:
        # если lexical search ничего не нашёл,
        # возвращаем уже изученные статьи коллекции.
        summarized = [
            row
            for row in candidates
            if (row["summary"] or "").strip()
        ]

        if summarized:
            return summarized[:limit]

        return []
