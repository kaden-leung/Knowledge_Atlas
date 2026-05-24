"""Tests for overseer.vocabulary_registry."""

from __future__ import annotations

import pytest

from overseer.vocabulary_registry import (
    add_candidate,
    canonical_for,
    get,
    list_candidates,
    list_canonicals,
    mark_as_synonym,
)


def _seed_canonical(conn, kind: str, value: str, seeded_from: str = "test.v1") -> str:
    """Helper to insert a canonical row for testing (not via the seeder script)."""
    import hashlib
    h = hashlib.sha256(f"{kind}\x1f{value}".encode()).hexdigest()[:16]
    vid = f"vocab:{kind}:{h}"
    conn.execute(
        """
        INSERT INTO vocabulary_registry (
            value_id, kind, value, canonical_value, first_seen_in_paper,
            first_observed_at, first_observed_build_run_id, review_status,
            canonicalization_source, seeded_from
        ) VALUES (?, ?, ?, NULL, NULL, '2026-05-23T00:00:00Z', NULL, 'canonical', NULL, ?)
        """,
        (vid, kind, value, seeded_from),
    )
    return vid


def test_get_returns_none_when_missing(overseer_db):
    assert get(overseer_db, "instrument_name", "Imaginary Test") is None


def test_add_candidate_inserts_new_candidate_row(overseer_db):
    row = add_candidate(
        overseer_db,
        kind="instrument_name",
        value="Novel Cognitive Battery",
        first_seen_in_paper="PDF-0123",
        first_observed_build_run_id="br:test:001",
    )
    assert row.review_status == "candidate"
    assert row.first_seen_in_paper == "PDF-0123"
    assert row.first_observed_build_run_id == "br:test:001"
    assert row.canonical_value is None


def test_add_candidate_is_idempotent_on_kind_value(overseer_db):
    a = add_candidate(
        overseer_db, kind="construct_label", value="executive function",
        first_seen_in_paper="PDF-0100", first_observed_build_run_id=None,
    )
    b = add_candidate(
        overseer_db, kind="construct_label", value="executive function",
        first_seen_in_paper="PDF-0200", first_observed_build_run_id=None,
    )
    assert a.value_id == b.value_id
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM vocabulary_registry WHERE value = 'executive function'"
    ).fetchone()[0]
    assert n == 1


def test_list_canonicals_returns_canonical_rows(overseer_db):
    _seed_canonical(overseer_db, "instrument_name", "Stroop Task")
    _seed_canonical(overseer_db, "instrument_name", "N-Back Task")
    add_candidate(
        overseer_db, kind="instrument_name", value="Novel Test",
        first_seen_in_paper="PDF-X", first_observed_build_run_id=None,
    )
    canonicals = list_canonicals(overseer_db, "instrument_name")
    values = sorted(c.value for c in canonicals)
    assert values == ["N-Back Task", "Stroop Task"]


def test_list_candidates_returns_candidate_rows(overseer_db):
    _seed_canonical(overseer_db, "instrument_name", "Stroop Task")
    add_candidate(
        overseer_db, kind="instrument_name", value="Novel Test",
        first_seen_in_paper="PDF-X", first_observed_build_run_id=None,
    )
    candidates = list_candidates(overseer_db, "instrument_name")
    assert [c.value for c in candidates] == ["Novel Test"]


def test_canonical_for_returns_value_when_row_is_canonical(overseer_db):
    _seed_canonical(overseer_db, "measure_name", "salivary cortisol")
    assert canonical_for(overseer_db, "measure_name", "salivary cortisol") == "salivary cortisol"


def test_canonical_for_returns_canonical_value_when_row_is_synonym(overseer_db):
    _seed_canonical(overseer_db, "measure_name", "salivary cortisol")
    add_candidate(
        overseer_db, kind="measure_name", value="cortisol (saliva)",
        first_seen_in_paper="PDF-99", first_observed_build_run_id=None,
    )
    mark_as_synonym(
        overseer_db, kind="measure_name", value="cortisol (saliva)",
        canonical_value="salivary cortisol",
        canonicalization_source="deterministic.normalization.v1",
    )
    assert canonical_for(overseer_db, "measure_name", "cortisol (saliva)") == "salivary cortisol"


def test_canonical_for_returns_none_for_candidate(overseer_db):
    add_candidate(
        overseer_db, kind="instrument_name", value="Untouched Candidate",
        first_seen_in_paper="PDF-?", first_observed_build_run_id=None,
    )
    assert canonical_for(overseer_db, "instrument_name", "Untouched Candidate") is None


def test_canonical_for_returns_none_for_missing_value(overseer_db):
    assert canonical_for(overseer_db, "instrument_name", "Never Heard Of It") is None


def test_mark_as_synonym_rejects_non_canonical_target(overseer_db):
    add_candidate(
        overseer_db, kind="instrument_name", value="Pending Candidate",
        first_seen_in_paper="PDF-7", first_observed_build_run_id=None,
    )
    # Target value is itself a candidate, not canonical — should reject.
    add_candidate(
        overseer_db, kind="instrument_name", value="Also Candidate",
        first_seen_in_paper="PDF-8", first_observed_build_run_id=None,
    )
    with pytest.raises(ValueError):
        mark_as_synonym(
            overseer_db,
            kind="instrument_name",
            value="Pending Candidate",
            canonical_value="Also Candidate",
            canonicalization_source="test",
        )


def test_mark_as_synonym_updates_status_and_canonical_value(overseer_db):
    _seed_canonical(overseer_db, "construct_label", "stress")
    add_candidate(
        overseer_db, kind="construct_label", value="psychological stress",
        first_seen_in_paper="PDF-22", first_observed_build_run_id=None,
    )
    mark_as_synonym(
        overseer_db, kind="construct_label", value="psychological stress",
        canonical_value="stress",
        canonicalization_source="deterministic.normalization.v1",
    )
    row = get(overseer_db, "construct_label", "psychological stress")
    assert row.review_status == "synonym"
    assert row.canonical_value == "stress"
    assert row.canonicalization_source == "deterministic.normalization.v1"
