from __future__ import annotations

import sqlite3
from pathlib import Path

from sim import sim_ka_db


def test_init_sim_ka_db_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_ka.db"
    created = sim_ka_db.init_sim_ka_db(db_path)
    assert created == db_path
    conn = sqlite3.connect(db_path)
    try:
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "artefact_registry" in names
        assert "cross_db_sync_events" in names
        assert "reconciler_event_log" in names
    finally:
        conn.close()
