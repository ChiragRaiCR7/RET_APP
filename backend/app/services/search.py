"""Full-text row index over datasets (SQLite FTS5, BM25 ranking).

Why lexical instead of embeddings: questions about Oracle extracts are dominated by exact
identifiers (ledger names, org codes, column names), where BM25 is strong, it needs no
external service, and it indexes ~100k rows/s locally. Dense retrieval can be layered on
later if evaluation shows paraphrase misses.

The ``workspace`` column is *indexed* and every query is ANDed with it, so tenant scoping is
enforced inside the FTS query itself rather than by post-filtering.
"""

import csv
import logging
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import new_session
from app.models import Dataset, Workspace, utcnow
from app.services import jobs

log = logging.getLogger("ret.search")

ROW_CHARS = 2_000
INSERT_BATCH = 2_000
_WORD = re.compile(r"[\w][\w.\-/]{1,63}", re.UNICODE)
_STOP = frozenset(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "by",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "what",
        "which",
        "who",
        "how",
        "many",
        "much",
        "show",
        "list",
        "give",
        "me",
        "all",
        "any",
        "from",
        "that",
        "this",
        "these",
        "those",
        "do",
        "does",
        "there",
        "their",
        "it",
        "its",
        "as",
        "at",
        "please",
        "find",
        "tell",
        "about",
    ]
)


@dataclass(frozen=True)
class Hit:
    dataset_id: str
    row: int
    content: str
    score: float


def _row_text(ds: Dataset, header: list[str], row: list[str]) -> str:
    cells = "; ".join(f"{h}: {v}" for h, v in zip(header, row, strict=False) if v.strip())
    return f"[{ds.group}] {ds.name} | {cells}"[:ROW_CHARS]


def drop_workspace(db: Session, workspace_id: str) -> None:
    db.execute(text("DELETE FROM row_index WHERE workspace = :w"), {"w": workspace_id})


def _insert_dataset(db: Session, ds: Dataset, budget: int) -> int:
    from app.services.workspaces import dataset_path  # local: avoids import cycle

    inserted = 0
    batch: list[dict[str, object]] = []
    with dataset_path(ds).open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        for i, row in enumerate(reader):
            if inserted + len(batch) >= budget:
                break
            batch.append(
                {"c": _row_text(ds, header, row), "w": ds.workspace_id, "d": ds.id, "r": i}
            )
            if len(batch) >= INSERT_BATCH:
                db.execute(text("INSERT INTO row_index VALUES (:c, :w, :d, :r)"), batch)
                inserted += len(batch)
                batch = []
    if batch:
        db.execute(text("INSERT INTO row_index VALUES (:c, :w, :d, :r)"), batch)
        inserted += len(batch)
    return inserted


def drop_dataset(db: Session, ds: Dataset) -> None:
    db.execute(
        text("DELETE FROM row_index WHERE workspace = :w AND dataset_id = :d"),
        {"w": ds.workspace_id, "d": ds.id},
    )


def reindex_dataset(db: Session, ds: Dataset) -> None:
    """Refresh one dataset's rows after an edit (only if the workspace is indexed)."""
    ws = db.get(Workspace, ds.workspace_id)
    if ws is None or ws.indexed_at is None:
        return
    drop_dataset(db, ds)
    _insert_dataset(db, ds, get_settings().index_max_rows_per_workspace)


def build_index(job_id: str, workspace_id: str) -> str:
    budget = get_settings().index_max_rows_per_workspace
    with new_session() as db:
        ws = db.get(Workspace, workspace_id)
        if ws is None:
            raise RuntimeError("Workspace was deleted.")
        drop_workspace(db, ws.id)
        ws.indexed_rows, ws.indexed_at = 0, None  # chat refuses a half-built index
        db.commit()
        total = 0
        datasets = list(ws.datasets)
        for n, ds in enumerate(datasets, 1):
            if total >= budget:
                break
            total += _insert_dataset(db, ds, budget - total)
            # Commit before reporting: progress is written from another session, and SQLite
            # allows one writer, so holding this transaction open would deadlock.
            db.commit()
            jobs.report_progress(job_id, n, len(datasets))
        ws.indexed_rows, ws.indexed_at = total, utcnow()
        db.commit()
    capped = " (row cap reached)" if total >= budget else ""
    return f"Indexed {total:,} rows from {len(datasets)} datasets{capped}."


def fts_query(question: str) -> str | None:
    """Build a safe FTS5 expression: every term quoted (no operator injection), ORed."""
    terms = []
    for raw in _WORD.findall(question):
        term = raw.strip(".-/").lower()
        if len(term) < 2 or term in _STOP:
            continue
        terms.append('"' + term.replace('"', "") + '"')
    if not terms:
        return None
    return " OR ".join(dict.fromkeys(terms[:24]))


def search(db: Session, workspace_id: str, question: str, k: int) -> list[Hit]:
    expr = fts_query(question)
    if expr is None:
        return []
    rows = db.execute(
        text(
            "SELECT dataset_id, row_num, content, bm25(row_index) AS score FROM row_index "
            "WHERE row_index MATCH :q ORDER BY score LIMIT :k"
        ),
        {"q": f'workspace : "{workspace_id}" AND ({expr})', "k": k},
    ).all()
    return [Hit(r.dataset_id, int(r.row_num), r.content, float(r.score)) for r in rows]
