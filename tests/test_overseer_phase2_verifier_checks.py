"""Tests for the Phase 2 verifier extensions (_check_cross_db_sync and
_check_abstract_source_provenance)."""

from __future__ import annotations

from overseer.artefact_registry import register
from overseer.candidate_pdf_state import transition
from overseer.verifier_data import verify_strict


def test_check_cross_db_sync_passes_on_clean_db(overseer_db):
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "cross_db_sync"][0]
    assert res.passed


def test_check_cross_db_sync_passes_when_unresolved_row_is_fresh(overseer_db):
    overseer_db.execute(
        """
        INSERT INTO cross_db_sync_events (
            event_id, event_kind, lifecycle_payload_hash,
            article_finder_payload_hash, status, created_at
        ) VALUES ('ev:test', 'accept_candidate', 'paper:PDF-X',
                  'sha256:test', 'unresolved', datetime('now'))
        """,
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "cross_db_sync"][0]
    # Fresh unresolved row (just now) doesn't trip the 300s threshold.
    assert res.passed


def test_check_cross_db_sync_fails_when_unresolved_row_is_stale(overseer_db):
    overseer_db.execute(
        """
        INSERT INTO cross_db_sync_events (
            event_id, event_kind, lifecycle_payload_hash,
            article_finder_payload_hash, status, created_at
        ) VALUES ('ev:stale', 'accept_candidate', 'paper:PDF-Y',
                  'sha256:test', 'unresolved', datetime('now', '-600 seconds'))
        """,
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "cross_db_sync"][0]
    assert not res.passed
    assert any(f["event_id"] == "ev:stale" for f in res.failures)


def test_check_cross_db_sync_passes_on_matched_status(overseer_db):
    overseer_db.execute(
        """
        INSERT INTO cross_db_sync_events (
            event_id, event_kind, lifecycle_payload_hash,
            article_finder_payload_hash, status, created_at, resolved_at
        ) VALUES ('ev:m', 'accept_candidate', 'paper:PDF-M',
                  'sha256:test', 'matched',
                  datetime('now', '-600 seconds'),
                  datetime('now', '-500 seconds'))
        """,
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "cross_db_sync"][0]
    # Matched rows past the threshold are fine — only 'unresolved' fails.
    assert res.passed


def _register_kind(conn, kind_name):
    conn.execute(
        "INSERT OR IGNORE INTO artefact_kinds (kind_name, owner_pipeline, "
        "support_rule_module, schema_version, active, created_at) VALUES "
        "(?, 'p', 'm', 'v1', 1, '2026-05-23T00:00:00Z')",
        (kind_name,),
    )


def test_check_abstract_source_provenance_passes_when_no_abstracts(overseer_db):
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "abstract_source_provenance"][0]
    assert res.passed


def test_check_abstract_source_provenance_passes_after_proper_transition(overseer_db):
    _register_kind(overseer_db, "article_finder_candidate")
    _register_kind(overseer_db, "abstract")
    transition(
        overseer_db, paper_id="PDF-AB",
        from_state="metadata_only", to_state="abstract_only",
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "abstract_source_provenance"][0]
    assert res.passed


def test_check_abstract_source_provenance_fails_for_orphan_abstract(overseer_db):
    _register_kind(overseer_db, "abstract")
    # Register an abstract artefact directly WITHOUT going through the state
    # machine — no parent dependency_edge.
    register(
        overseer_db, kind="abstract", entity_type="paper", entity_id="PDF-ORPHAN",
        field_path="abstract_only", schema_version="abstract.v1",
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "abstract_source_provenance"][0]
    assert not res.passed
    assert any(f["entity_id"] == "PDF-ORPHAN" for f in res.failures)
