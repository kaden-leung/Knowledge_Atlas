from __future__ import annotations

import sqlite3
from pathlib import Path

from sim import sim_af_db


def test_init_sim_af_db_creates_expected_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_af.db"
    created = sim_af_db.init_sim_af_db(db_path)
    assert created == db_path
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='papers'"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


def test_upsert_papers_writes_and_updates_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_af.db"
    sim_af_db.init_sim_af_db(db_path)
    written = sim_af_db.upsert_papers(
        [
            {
                "paper_id": "SIM-0001",
                "title": "Initial title",
                "status": "candidate",
                "atlas_intake_decision": None,
            }
        ],
        db_path=db_path,
    )
    assert written == 1
    sim_af_db.upsert_papers(
        [
            {
                "paper_id": "SIM-0001",
                "title": "Updated title",
                "status": "candidate",
                "atlas_intake_decision": "accept_candidate",
            }
        ],
        db_path=db_path,
    )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT title, atlas_intake_decision FROM papers WHERE paper_id='SIM-0001'").fetchone()
        assert row["title"] == "Updated title"
        assert row["atlas_intake_decision"] == "accept_candidate"
    finally:
        conn.close()

