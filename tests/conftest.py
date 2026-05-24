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


@pytest.fixture
def overseer_db(tmp_path):
    """Provide a fresh on-disk SQLite DB with the dependency_overseer schema applied.

    Yields a sqlite3.Connection with row_factory=Row, foreign_keys ON, WAL mode.
    """
    db_path = tmp_path / "overseer_test.db"
    schema_sql = _OVERSEER_SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql)
    yield conn
    conn.close()
