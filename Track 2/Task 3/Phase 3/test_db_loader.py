"""DB-loader tests for Phase 3 (Pass 3)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from db_loader import LoadReport, load_search_results

_HERE = Path(__file__).resolve().parent
FIXTURE = _HERE / "fixtures" / "sample_search_results.json"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row_count(db_path: Path, table: str) -> int:
    conn = _connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Loads fixture (basic happy path)
# ---------------------------------------------------------------------------

def test_loads_fixture_search_results(tmp_path):
    db_path = tmp_path / "out.db"
    report = load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path,
        shared_snapshot_path=None,
        corpus_csv=None,
    )
    assert report.input_candidate_count == 4
    assert _row_count(db_path, "article_references") == 4
    assert report.errors == []


# ---------------------------------------------------------------------------
# 2. voi_score copies forward
# ---------------------------------------------------------------------------

def test_voi_score_copied_forward(tmp_path):
    db_path = tmp_path / "voi.db"
    load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path,
        shared_snapshot_path=None,
        corpus_csv=None,
    )
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT voi_score FROM article_references").fetchall()
    finally:
        conn.close()
    # Fixture has voi_score=0.85 for every result
    assert all(r[0] == 0.85 for r in rows)


# ---------------------------------------------------------------------------
# 3. run_id stamped on every row
# ---------------------------------------------------------------------------

def test_run_id_stamped_on_every_row(tmp_path):
    db_path = tmp_path / "runid.db"
    load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path,
        shared_snapshot_path=None,
        corpus_csv=None,
        run_id="RUN-CUSTOM",
    )
    conn = _connect(db_path)
    try:
        runs = {r[0] for r in conn.execute("SELECT discovery_run_id FROM article_references").fetchall()}
    finally:
        conn.close()
    assert runs == {"RUN-CUSTOM"}


# ---------------------------------------------------------------------------
# 4. Every transition has created_by='db_loader'
# ---------------------------------------------------------------------------

def test_initial_transition_logged_per_row(tmp_path):
    db_path = tmp_path / "trans.db"
    load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path,
        shared_snapshot_path=None,
        corpus_csv=None,
    )
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT reference_id, created_by, reason FROM lifecycle_transitions").fetchall()
    finally:
        conn.close()
    assert len(rows) == 4
    assert all(r[1] == "db_loader" for r in rows)
    assert all(r[2].startswith("initial_insert:") for r in rows)


# ---------------------------------------------------------------------------
# 5. Idempotent: same JSON, same run_id → no new rows on rerun
# ---------------------------------------------------------------------------

def test_loader_idempotent_with_same_run_id(tmp_path):
    db_path = tmp_path / "idem.db"
    load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path, shared_snapshot_path=None, corpus_csv=None,
        run_id="RUN-IDEM",
    )
    first_count = _row_count(db_path, "article_references")
    # Re-run identical input
    load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path, shared_snapshot_path=None, corpus_csv=None,
        run_id="RUN-IDEM",
    )
    second_count = _row_count(db_path, "article_references")
    assert second_count == first_count


# ---------------------------------------------------------------------------
# 6. Re-load with a different run_id → DOI rows merge (no new rows for DOI hits)
# ---------------------------------------------------------------------------

def test_loader_with_new_run_id_dedupes_via_doi(tmp_path):
    db_path = tmp_path / "merge.db"
    load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path, shared_snapshot_path=None, corpus_csv=None,
        run_id="RUN-A",
    )
    first_count = _row_count(db_path, "article_references")

    report = load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path, shared_snapshot_path=None, corpus_csv=None,
        run_id="RUN-B",
    )
    second_count = _row_count(db_path, "article_references")

    # DOI-bearing rows (2 in fixture) should merge; no-DOI rows (2) should match by title and merge too
    assert second_count == first_count
    assert report.merged_doi_count >= 2


# ---------------------------------------------------------------------------
# 7. Invalid schema is rejected
# ---------------------------------------------------------------------------

def test_invalid_json_schema_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    # Missing required `metadata.schema_version` field
    bad.write_text(json.dumps({"metadata": {"run_id": "RUN-BAD"}, "results": []}))
    with pytest.raises(Exception):
        load_search_results(
            search_results_path=bad,
            db_path=tmp_path / "x.db",
            shared_snapshot_path=None, corpus_csv=None,
            validate_schema=True,
        )


# ---------------------------------------------------------------------------
# 8. Report counts match DB state
# ---------------------------------------------------------------------------

def test_load_report_counts_match_actual_db_state(tmp_path):
    db_path = tmp_path / "counts.db"
    report = load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path, shared_snapshot_path=None, corpus_csv=None,
    )
    actual = _row_count(db_path, "article_references")
    summed = (report.inserted_count + report.merged_doi_count
              + report.merged_title_count + report.enriched_doi_count
              + report.marked_duplicate_count)
    assert summed == report.input_candidate_count
    assert actual == report.inserted_count + report.marked_duplicate_count
    # transitions logged == every candidate that wasn't an error
    assert report.transitions_logged_count == report.input_candidate_count


# ---------------------------------------------------------------------------
# 9. Zero-candidate input → empty DB, no errors, no crash
# ---------------------------------------------------------------------------

def test_loads_zero_candidate_input(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({
        "metadata": {
            "schema_version": "1.1.0",
            "run_id": "RUN-20260528-000000",
            "generated_at": "2026-05-28T00:00:00Z",
            "input_query_count": 0,
            "queries_processed": 0,
            "queries_skipped": {},
            "sources_enabled": [],
            "per_source_stats": {},
            "credits_used": 0,
            "credits_max": 50,
            "candidates_total_raw": 0,
            "candidates_after_dedupe": 0,
            "null_result_queries": 0,
            "mock_mode": True,
            "serpapi_engine": "google_scholar"
        },
        "results": [],
        "null_results": [],
        "skipped_queries": []
    }))
    db_path = tmp_path / "empty.db"
    report = load_search_results(
        search_results_path=empty,
        db_path=db_path, shared_snapshot_path=None, corpus_csv=None,
    )
    assert report.input_candidate_count == 0
    assert _row_count(db_path, "article_references") == 0
    assert report.errors == []


# ---------------------------------------------------------------------------
# 10. Run ID is read from JSON when --run-id is omitted
# ---------------------------------------------------------------------------

def test_loader_reads_run_id_from_json(tmp_path):
    db_path = tmp_path / "frj.db"
    report = load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path, shared_snapshot_path=None, corpus_csv=None,
        run_id=None,
    )
    # Fixture's metadata.run_id is RUN-20260527-143200
    assert report.run_id == "RUN-20260527-143200"


# ---------------------------------------------------------------------------
# 11. --dry-run does not write to the on-disk DB
# ---------------------------------------------------------------------------

def test_dry_run_does_not_write_to_disk_db(tmp_path):
    db_path = tmp_path / "dry.db"
    report = load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path, shared_snapshot_path=None, corpus_csv=None,
        dry_run=True,
    )
    # The on-disk file should not exist (we wrote to :memory:)
    assert not db_path.exists()
    # But the report still reflects planned inserts
    assert report.dry_run is True
    assert report.input_candidate_count == 4


# ---------------------------------------------------------------------------
# 12. merged_from_sources lists are joined into the DB's discovered_via
# ---------------------------------------------------------------------------

def test_merged_from_sources_joined_in_discovered_via(tmp_path):
    db_path = tmp_path / "join.db"
    load_search_results(
        search_results_path=FIXTURE,
        db_path=db_path, shared_snapshot_path=None, corpus_csv=None,
    )
    conn = _connect(db_path)
    try:
        # Result #4 in fixture has merged_from_sources=["serpapi_scholar", "scholarly_search"]
        # — should land in DB as the sorted comma-join.
        row = conn.execute(
            "SELECT discovered_via FROM article_references WHERE doi = '10.1016/j.neuron.2012.09.005'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "scholarly_search, serpapi_scholar"
