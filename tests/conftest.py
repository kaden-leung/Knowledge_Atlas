import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


_OVERSEER_SCHEMA_PATH = (
    ROOT / "contracts" / "schemas" / "dependency_overseer" / "dependency_overseer.sql"
)
_AEPL_SCHEMA_PATH = (
    ROOT / "contracts" / "schemas" / "article_epistemic_layer.sql"
)


@pytest.fixture
def aepl_db_path(tmp_path):
    """Provide a fresh on-disk SQLite DB file with the article-epistemic-layer
    schema applied. Returns the Path, not a connection — most builder/verifier
    code paths open their own connections."""
    db_path = tmp_path / "aepl_test.db"
    schema_sql = _AEPL_SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.fixture
def aepl_db(aepl_db_path):
    """Same DB but as an open Connection for tests that need to query directly."""
    conn = sqlite3.connect(aepl_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def overseer_db(tmp_path):
    """Provide a fresh on-disk SQLite DB with the dependency_overseer schema applied.

    Yields a sqlite3.Connection in autocommit mode (isolation_level=None) so
    explicit BEGIN IMMEDIATE / COMMIT in overseer.db.transaction() works.
    """
    db_path = tmp_path / "overseer_test.db"
    schema_sql = _OVERSEER_SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    conn.isolation_level = None
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
    yield conn
    conn.close()
