"""Tests for overseer.candidate_pdf_state."""

from __future__ import annotations

import pytest

from overseer.candidate_pdf_state import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    STATES,
    STATE_TO_RELATED_KIND,
    ensure_candidate,
    is_terminal,
    successor_states,
    transition,
)


def test_states_match_spec_order():
    assert STATES == (
        "metadata_only",
        "abstract_only",
        "candidate_pdf_unverified",
        "pdf_verified",
        "ocr_ready",
        "extracted",
    )


def test_is_terminal_only_for_extracted():
    assert is_terminal("extracted") is True
    for s in STATES:
        if s != "extracted":
            assert is_terminal(s) is False


def test_successor_states_match_allowed_transitions():
    for s in STATES:
        assert set(successor_states(s)) == set(ALLOWED_TRANSITIONS[s])


def test_ensure_candidate_is_idempotent(overseer_db):
    a = ensure_candidate(overseer_db, "PDF-CAND-001")
    b = ensure_candidate(overseer_db, "PDF-CAND-001")
    assert a.artefact_id == b.artefact_id
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM artefact_registry WHERE entity_id = 'PDF-CAND-001'"
    ).fetchone()[0]
    assert n == 1


def test_transition_metadata_to_abstract_creates_abstract_artefact(overseer_db):
    result = transition(
        overseer_db, paper_id="PDF-S1",
        from_state="metadata_only", to_state="abstract_only",
    )
    assert result.from_state == "metadata_only"
    assert result.to_state == "abstract_only"
    assert result.related_artefact_id is not None
    row = overseer_db.execute(
        "SELECT kind, entity_id, field_path FROM artefact_registry WHERE artefact_id = ?",
        (result.related_artefact_id,),
    ).fetchone()
    assert row["kind"] == "abstract"
    assert row["entity_id"] == "PDF-S1"
    assert row["field_path"] == "abstract_only"


def test_transition_adds_dependency_edge(overseer_db):
    result = transition(
        overseer_db, paper_id="PDF-S2",
        from_state="metadata_only", to_state="abstract_only",
    )
    edge = overseer_db.execute(
        """
        SELECT edge_kind FROM dependency_edges
        WHERE parent_artefact_id = ? AND child_artefact_id = ?
        """,
        (result.candidate_artefact_id, result.related_artefact_id),
    ).fetchone()
    assert edge is not None
    assert edge["edge_kind"] == "derived_from"


def test_each_documented_transition_succeeds(overseer_db):
    seq = [
        ("metadata_only", "abstract_only"),
        ("abstract_only", "candidate_pdf_unverified"),
        ("candidate_pdf_unverified", "pdf_verified"),
        ("pdf_verified", "ocr_ready"),
        ("ocr_ready", "extracted"),
    ]
    for from_s, to_s in seq:
        result = transition(
            overseer_db, paper_id="PDF-FULL",
            from_state=from_s, to_state=to_s,
        )
        assert result.to_state == to_s


def test_invalid_transition_is_rejected(overseer_db):
    with pytest.raises(InvalidTransitionError):
        transition(
            overseer_db, paper_id="PDF-BAD",
            from_state="metadata_only", to_state="pdf_verified",  # skipping states
        )


def test_unknown_state_is_rejected(overseer_db):
    with pytest.raises(InvalidTransitionError):
        transition(
            overseer_db, paper_id="PDF-?",
            from_state="metadata_only", to_state="not_a_state",
        )


def test_terminal_state_has_no_successors():
    assert successor_states("extracted") == ()


def test_state_to_related_kind_mapping_covers_post_metadata_states():
    # metadata_only itself doesn't have a related kind (it IS the candidate).
    for s in STATES:
        if s == "metadata_only":
            assert s not in STATE_TO_RELATED_KIND
        else:
            assert s in STATE_TO_RELATED_KIND
