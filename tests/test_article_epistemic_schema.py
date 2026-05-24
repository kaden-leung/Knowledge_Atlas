"""Schema-level tests for the article_epistemic_layer (Stage 1).

Authority: docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md §4, §5.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _expected_tables() -> set[str]:
    return {
        "article_epistemic_records",
        "article_epistemic_components",
        "article_epistemic_support_sets",
        "article_epistemic_build_runs",
        "article_epistemic_completion_queue",
        "article_epistemic_verification_events",
    }


def test_schema_creates_all_six_tables(aepl_db):
    names = {
        r["name"] for r in aepl_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'article_epistemic%'"
        )
    }
    assert _expected_tables() <= names


def test_schema_is_idempotent(aepl_db_path):
    schema_sql = (Path(__file__).resolve().parents[1] /
                  "contracts" / "schemas" / "article_epistemic_layer.sql"
                  ).read_text()
    conn = sqlite3.connect(aepl_db_path)
    try:
        # Re-applying should not raise — IF NOT EXISTS everywhere.
        conn.executescript(schema_sql)
        conn.executescript(schema_sql)
    finally:
        conn.close()


def test_extraction_status_check_rejects_bad_vocab(aepl_db):
    # Set up minimal parent rows.
    aepl_db.execute(
        "INSERT INTO article_epistemic_build_runs(build_run_id, builder_version, "
        "started_at, status) VALUES ('br1', 'v1', '2026-05-23T00:00:00Z', 'running')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        aepl_db.execute(
            "INSERT INTO article_epistemic_records("
            "  record_id, build_run_id, paper_id, schema_version, "
            "  extraction_status, enrichment_status, freshness_status, "
            "  review_status, render_status, input_fingerprint, payload_hash"
            ") VALUES ('rec1','br1','P1','v1','BOGUS_STATUS','none','fresh',"
            "          'not_required','renderable','fp','ph')"
        )


def test_source_mode_check_rejects_bad_vocab(aepl_db):
    aepl_db.execute(
        "INSERT INTO article_epistemic_build_runs(build_run_id, builder_version, "
        "started_at, status) VALUES ('br1', 'v1', '2026-05-23T00:00:00Z', 'running')"
    )
    aepl_db.execute(
        "INSERT INTO article_epistemic_support_sets(support_set_id, support_set_hash, "
        "members_json) VALUES ('ss1','h','[]')"
    )
    aepl_db.execute(
        "INSERT INTO article_epistemic_records("
        "  record_id, build_run_id, paper_id, schema_version, "
        "  extraction_status, enrichment_status, freshness_status, "
        "  review_status, render_status, input_fingerprint, payload_hash"
        ") VALUES ('rec1','br1','P1','v1','complete','none','fresh',"
        "          'not_required','renderable','fp','ph')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        aepl_db.execute(
            "INSERT INTO article_epistemic_components("
            "  component_id, build_run_id, record_id, paper_id, component_type, "
            "  component_status, source_mode, field_policy, review_status, "
            "  freshness_status, render_policy, content_hash, support_set_id"
            ") VALUES ('c1','br1','rec1','P1','primary_claim','present',"
            "          'NOT_A_SOURCE_MODE','extracted_only','unreviewed',"
            "          'fresh','render','h','ss1')"
        )


def test_partial_unique_index_enforces_one_active_per_paper_schema(aepl_db):
    """Spec §3: one active record per (paper_id, schema_version)."""
    aepl_db.execute(
        "INSERT INTO article_epistemic_build_runs(build_run_id, builder_version, "
        "started_at, status) VALUES ('br1','v1','2026-05-23T00:00:00Z','running')"
    )
    aepl_db.execute(
        "INSERT INTO article_epistemic_build_runs(build_run_id, builder_version, "
        "started_at, status) VALUES ('br2','v1','2026-05-23T00:00:01Z','running')"
    )
    aepl_db.execute(
        "INSERT INTO article_epistemic_records("
        "  record_id, build_run_id, paper_id, schema_version, "
        "  extraction_status, enrichment_status, freshness_status, "
        "  review_status, render_status, input_fingerprint, payload_hash"
        ") VALUES ('rec1','br1','P1','v1','complete','none','fresh',"
        "          'not_required','renderable','fp','ph')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        aepl_db.execute(
            "INSERT INTO article_epistemic_records("
            "  record_id, build_run_id, paper_id, schema_version, active, "
            "  extraction_status, enrichment_status, freshness_status, "
            "  review_status, render_status, input_fingerprint, payload_hash"
            ") VALUES ('rec1','br2','P1','v1', 1, 'complete','none','fresh',"
            "          'not_required','renderable','fp','ph')"
        )


def test_historical_versions_allowed_when_only_one_active(aepl_db):
    aepl_db.execute(
        "INSERT INTO article_epistemic_build_runs(build_run_id, builder_version, "
        "started_at, status) VALUES ('br1','v1','2026-05-23T00:00:00Z','running')"
    )
    aepl_db.execute(
        "INSERT INTO article_epistemic_build_runs(build_run_id, builder_version, "
        "started_at, status) VALUES ('br2','v1','2026-05-23T00:00:01Z','running')"
    )
    aepl_db.execute(
        "INSERT INTO article_epistemic_records("
        "  record_id, build_run_id, paper_id, schema_version, active, "
        "  extraction_status, enrichment_status, freshness_status, "
        "  review_status, render_status, input_fingerprint, payload_hash"
        ") VALUES ('rec1','br1','P1','v1', 0, 'complete','none','fresh',"
        "          'not_required','renderable','fp','ph')"
    )
    # Second row active=1 inserts cleanly because the first is active=0.
    aepl_db.execute(
        "INSERT INTO article_epistemic_records("
        "  record_id, build_run_id, paper_id, schema_version, active, "
        "  extraction_status, enrichment_status, freshness_status, "
        "  review_status, render_status, input_fingerprint, payload_hash"
        ") VALUES ('rec1','br2','P1','v1', 1, 'complete','none','fresh',"
        "          'not_required','renderable','fp','ph')"
    )
    rows = aepl_db.execute(
        "SELECT build_run_id, active FROM article_epistemic_records "
        "WHERE paper_id='P1' AND schema_version='v1' ORDER BY build_run_id"
    ).fetchall()
    assert len(rows) == 2
    assert [r["active"] for r in rows] == [0, 1]


def test_completion_queue_partial_unique_dedupes_open_items(aepl_db):
    aepl_db.execute(
        "INSERT INTO article_epistemic_completion_queue("
        "  paper_id, component_type, reason, severity, next_action, status"
        ") VALUES ('P1','primary_claim','primary_claim_not_extracted','blocking',"
        "          'rebuild','open')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        aepl_db.execute(
            "INSERT INTO article_epistemic_completion_queue("
            "  paper_id, component_type, reason, severity, next_action, status"
            ") VALUES ('P1','primary_claim','primary_claim_not_extracted','blocking',"
            "          'rebuild','open')"
        )
