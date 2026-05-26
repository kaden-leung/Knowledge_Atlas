"""Build and seed a simulator-only Article Finder database.

This module creates a small AF-shaped SQLite DB used only for simulator runs.
It deliberately writes to a separate sim DB and never to the real AF DB.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from overseer.article_finder_connector import connect_readonly as connect_real_af_readonly


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIM_AF_DB_PATH = REPO_ROOT / "data" / "sim" / "sim_article_finder.db"

SIM_AF_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    doi TEXT,
    title TEXT,
    canonical_paper_id TEXT,
    status TEXT,
    atlas_intake_decision TEXT,
    ae_corpus_match_status TEXT,
    updated_at TEXT,
    created_at TEXT,
    source TEXT,
    abstract TEXT,
    pdf_path TEXT,
    pdf_sha256 TEXT,
    ae_run_id TEXT,
    atlas_primary_topic TEXT
);

CREATE INDEX IF NOT EXISTS idx_sim_af_status ON papers(status);
CREATE INDEX IF NOT EXISTS idx_sim_af_intake ON papers(atlas_intake_decision);
CREATE INDEX IF NOT EXISTS idx_sim_af_match_status ON papers(ae_corpus_match_status);
"""


SIM_AF_COLUMNS = (
    "paper_id",
    "doi",
    "title",
    "canonical_paper_id",
    "status",
    "atlas_intake_decision",
    "ae_corpus_match_status",
    "updated_at",
    "created_at",
    "source",
    "abstract",
    "pdf_path",
    "pdf_sha256",
    "ae_run_id",
    "atlas_primary_topic",
)


def resolve_sim_af_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is None:
        return DEFAULT_SIM_AF_DB_PATH
    path = Path(db_path).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def init_sim_af_db(db_path: str | Path | None = None) -> Path:
    path = resolve_sim_af_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SIM_AF_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    return path


def connect_sim_af(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = init_sim_af_db(db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def upsert_papers(
    rows: Iterable[dict[str, object]],
    *,
    db_path: str | Path | None = None,
) -> int:
    path = init_sim_af_db(db_path)
    placeholders = ", ".join("?" for _ in SIM_AF_COLUMNS)
    changed = 0
    conn = sqlite3.connect(path)
    try:
        for row in rows:
            values = [row.get(column) for column in SIM_AF_COLUMNS]
            conn.execute(
                f"""
                INSERT INTO papers ({", ".join(SIM_AF_COLUMNS)})
                VALUES ({placeholders})
                ON CONFLICT(paper_id) DO UPDATE SET
                    doi=excluded.doi,
                    title=excluded.title,
                    canonical_paper_id=excluded.canonical_paper_id,
                    status=excluded.status,
                    atlas_intake_decision=excluded.atlas_intake_decision,
                    ae_corpus_match_status=excluded.ae_corpus_match_status,
                    updated_at=excluded.updated_at,
                    created_at=excluded.created_at,
                    source=excluded.source,
                    abstract=excluded.abstract,
                    pdf_path=excluded.pdf_path,
                    pdf_sha256=excluded.pdf_sha256,
                    ae_run_id=excluded.ae_run_id,
                    atlas_primary_topic=excluded.atlas_primary_topic
                """,
                values,
            )
            changed += 1
        conn.commit()
    finally:
        conn.close()
    return changed


def seed_from_snapshot(
    *,
    sim_db_path: str | Path | None = None,
    af_db_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    """Copy a subset of real AF rows into the simulator DB.

    This function reads the real AF DB read-only and writes only to the sim DB.
    """
    sim_path = init_sim_af_db(sim_db_path)
    af_conn = connect_real_af_readonly(af_db_path)
    af_conn.row_factory = sqlite3.Row
    query = f"SELECT {', '.join(SIM_AF_COLUMNS)} FROM papers ORDER BY updated_at DESC, paper_id"
    params: list[object] = []
    if limit is not None:
        query += " LIMIT ?"
        params.append(int(limit))
    try:
        rows = [dict(row) for row in af_conn.execute(query, params).fetchall()]
    finally:
        af_conn.close()
    written = upsert_papers(rows, db_path=sim_path)
    return {
        "sim_db_path": str(sim_path),
        "rows_read": len(rows),
        "rows_written": written,
    }

