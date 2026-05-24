"""SQLite connection helper for the dependency overseer.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §2
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P1, P9)
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DB_CANDIDATES = (
    REPO_ROOT / "data" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "data" / "ka_payloads" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "160sp" / "pipeline_lifecycle_full.db",
)


def resolve_db_path(explicit: str | Path | None = None) -> Path:
    """Resolve the lifecycle DB path. Mirrors scripts/dependency_overseer_init.py."""
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = REPO_ROOT / p
        return p
    for cand in DEFAULT_DB_CANDIDATES:
        if cand.exists() and cand.stat().st_size > 0:
            return cand
    return DEFAULT_DB_CANDIDATES[-1]


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the lifecycle DB with WAL mode and foreign keys ON."""
    path = resolve_db_path(db_path) if db_path is None or not isinstance(db_path, sqlite3.Connection) else db_path
    if isinstance(path, sqlite3.Connection):
        return path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a transactional block. Rolls back on exception."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
