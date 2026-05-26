"""Build and seed a simulator-only Knowledge Atlas lifecycle database.

This applies the dependency-overseer schema to a separate SQLite DB used only
for simulator runs. It never writes to the live Knowledge Atlas lifecycle DB.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIM_KA_DB_PATH = REPO_ROOT / "data" / "sim" / "sim_pipeline_lifecycle.db"
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "dependency_overseer" / "dependency_overseer.sql"
OBSERVABILITY_SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "dependency_overseer" / "observability_layer.sql"


def resolve_sim_ka_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is None:
        return DEFAULT_SIM_KA_DB_PATH
    path = Path(db_path).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def _schema_sql() -> str:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    if OBSERVABILITY_SCHEMA_PATH.exists():
        sql += "\n\n"
        sql += OBSERVABILITY_SCHEMA_PATH.read_text(encoding="utf-8")
    return sql


def init_sim_ka_db(db_path: str | Path | None = None) -> Path:
    path = resolve_sim_ka_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_schema_sql())
        conn.execute(
            """
            INSERT OR IGNORE INTO artefact_kinds (
                kind_name, owner_pipeline, support_rule_module,
                schema_version, active, created_at
            ) VALUES (
                'article_finder_candidate',
                'dependency_overseer_simulator',
                'overseer.article_finder_reconciler',
                'article_finder_candidate.v1',
                1,
                '2026-05-25T00:00:00Z'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    return path


def connect_sim_ka(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = init_sim_ka_db(db_path)
    conn = sqlite3.connect(path)
    conn.isolation_level = None
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn
