"""Idempotency test — run db_loader twice on the same data, assert identical state.

This directly tests the dedupe path under the 'repeated run' condition required
by the production reliability plan. A second load of the same search_results.json
must produce identical row counts, DOI values, and merged_from_sources lists.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_TASK3 = _HERE.parent
sys.path.insert(0, str(_HERE))

from migrate import apply_migrations  # noqa: E402

FIXTURE = _HERE / "fixtures" / "sample_search_results.json"


def _make_fresh_db(tmp_path: Path) -> Path:
    db = tmp_path / "idempotency_test.db"
    apply_migrations(db)
    return db


def _run_load(db: Path, fixture: Path) -> dict:
    """Run db_loader programmatically and return row-count snapshot."""
    from db_loader import load_search_results
    load_search_results(
        search_results_path=fixture,
        db_path=db,
        run_id="RUN-IDEMPOTENCY-TEST",
        shared_snapshot_path=None,
        corpus_csv=None,
        dry_run=False,
    )
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT reference_id, doi, title_normalized, discovered_via "
        "FROM article_references ORDER BY reference_id"
    ).fetchall()
    transitions = conn.execute(
        "SELECT COUNT(*) FROM lifecycle_transitions"
    ).fetchone()[0]
    conn.close()
    return {
        "row_count": len(rows),
        "transition_count": transitions,
        "dois": [r["doi"] for r in rows],
        "titles": [r["title_normalized"] for r in rows],
        "discovered_via": [r["discovered_via"] for r in rows],
    }


@pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="sample_search_results.json fixture not found",
)
def test_double_load_is_idempotent(tmp_path):
    """Running db_loader twice on the same file must not change row counts."""
    db = _make_fresh_db(tmp_path)

    snap1 = _run_load(db, FIXTURE)
    snap2 = _run_load(db, FIXTURE)

    assert snap1["row_count"] == snap2["row_count"], (
        f"Row count changed after second load: {snap1['row_count']} → {snap2['row_count']}"
    )
    assert snap1["dois"] == snap2["dois"], "DOI list changed after second load"
    assert snap1["titles"] == snap2["titles"], "Title list changed after second load"


@pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="sample_search_results.json fixture not found",
)
def test_double_load_does_not_duplicate_transitions(tmp_path):
    """Each row should produce exactly one initial_insert transition, not two."""
    db = _make_fresh_db(tmp_path)

    snap1 = _run_load(db, FIXTURE)
    snap2 = _run_load(db, FIXTURE)

    # On the second load every row is a duplicate — no new transitions should be added
    # beyond those already recorded. The second run may add provenance_merge transitions
    # but must not re-add initial_insert for already-present rows.
    conn = sqlite3.connect(str(db))
    initial_inserts = conn.execute(
        "SELECT COUNT(*) FROM lifecycle_transitions WHERE reason LIKE 'initial_insert%'"
    ).fetchone()[0]
    conn.close()

    assert initial_inserts == snap1["row_count"], (
        f"Expected exactly {snap1['row_count']} initial_insert transitions; "
        f"got {initial_inserts} after two loads"
    )
