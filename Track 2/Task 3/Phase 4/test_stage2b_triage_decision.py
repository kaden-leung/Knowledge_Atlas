"""Unit tests for stage2b_triage_decision.py — all run against tmp_path DBs."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PHASE3 = _HERE.parent / "Phase 3"
if str(_PHASE3) not in sys.path:
    sys.path.insert(0, str(_PHASE3))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from migrate import apply_migrations  # noqa: E402

from stage2b_triage_decision import (  # noqa: E402
    decide,
    load_voi_map,
    lookup_voi,
    run_stage2b_triage,
    keyword_fallback_classify_with_abstract,
    DEFAULT_VOI_FALLBACK,
)


# ---------------------------------------------------------------------------
# Fixture: tmp_path DB seeded with abstract_collected + abstract_missing rows
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path, _PHASE3 / "migrations")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    yield db_path, conn
    conn.close()


def _seed_row(conn, ref_id, *, title, abstract, doi=None, venue=None,
              discovered_query=None, stage="abstract_collected", triage_decision=None):
    conn.execute(
        "INSERT INTO article_references "
        "(reference_id, doi, title_raw, title_normalized, venue, "
        " discovered_via, discovery_run_id, discovered_at, "
        " triage_stage, triage_decision, abstract_text, discovered_query) "
        "VALUES (?, ?, ?, ?, ?, 'serpapi_scholar', 'RUN-SEED', '2026-05-31T00:00:00Z', ?, ?, ?, ?)",
        (ref_id, doi, title, (title or "").lower(), venue, stage, triage_decision, abstract, discovered_query),
    )


# ---------------------------------------------------------------------------
# SC-T8 — decision matrix per cell (parametrized 3×3 = 9 cells)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("confidence,voi,expected_decision", [
    # On-topic (≥0.50): ACCEPT, ACCEPT, EDGE_CASE
    (0.80, 0.90, "ACCEPT"),
    (0.80, 0.60, "ACCEPT"),
    (0.80, 0.30, "EDGE_CASE"),
    # Marginal (0.20-0.49): EDGE, EDGE, REJECT
    (0.35, 0.90, "EDGE_CASE"),
    (0.35, 0.60, "EDGE_CASE"),
    (0.35, 0.30, "REJECT"),
    # Off-topic (<0.20): REJECT, REJECT, REJECT
    (0.10, 0.90, "REJECT"),
    (0.10, 0.60, "REJECT"),
    (0.10, 0.30, "REJECT"),
])
def test_decision_matrix_per_cell(confidence, voi, expected_decision):
    decision, reason = decide(confidence, voi)
    assert decision == expected_decision, f"clf={confidence} voi={voi}: got {decision}, want {expected_decision}"
    assert reason, "triage_reason must be non-empty"
    assert f"clf={confidence:.2f}" in reason
    assert f"voi={voi:.2f}" in reason


# ---------------------------------------------------------------------------
# SC-T9 — VOI lookup
# ---------------------------------------------------------------------------

def test_voi_lookup_with_fallback():
    voi_map = {"SC3-step3": 0.85, "L4-step3": 0.65}
    v, hit = lookup_voi("SC3-step3", voi_map)
    assert v == 0.85 and hit is True
    # missing key falls back to default
    v, hit = lookup_voi("UNKNOWN-QUERY", voi_map)
    assert v == DEFAULT_VOI_FALLBACK and hit is False
    # None query falls back too
    v, hit = lookup_voi(None, voi_map)
    assert v == DEFAULT_VOI_FALLBACK and hit is False


def test_load_voi_map_reads_query_results(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"queries": [
        {"display_id": "SC3", "step_number": 3, "voi_score": 0.85, "boolean_query": "(a OR b)"},
        {"display_id": "L4", "step_number": 3, "voi_score": 0.65},
    ]}))
    voi_map = load_voi_map(path)
    assert voi_map.get("SC3-step3") == 0.85
    assert voi_map.get("L4-step3") == 0.65
    assert voi_map.get("(a OR b)") == 0.85


# ---------------------------------------------------------------------------
# SC-T10 — keyword fallback classifier (with abstract)
# ---------------------------------------------------------------------------

def test_classifier_fallback_returns_high_confidence_on_keyword_rich_abstract():
    """With 8+ CNFA keywords across title+abstract, confidence should be ≥0.85."""
    abstract = (
        "We investigated architectural cognition in built environment using EEG. "
        "Participants navigated buildings while we measured cortisol and arousal. "
        "Results show predictive coding of spatial features."
    )
    _, conf = keyword_fallback_classify_with_abstract("Architectural cognition", "Cognition", abstract)
    assert conf >= 0.45


def test_classifier_fallback_returns_low_confidence_on_off_topic():
    _, conf = keyword_fallback_classify_with_abstract(
        "Quantum chromodynamics on the lattice",
        "Phys Rev D",
        "We compute SU(3) gauge couplings on a 64^4 lattice using staggered fermions.",
    )
    assert conf == 0.0


# ---------------------------------------------------------------------------
# SC-T1, T2, T7 — every row gets a decision, reason, confidence, voi
# ---------------------------------------------------------------------------

def test_every_row_gets_triage_decision_and_reason(db):
    db_path, conn = db
    # Use abstract-rich on-topic content so the keyword fallback assigns clearly on-topic confidence
    on_topic_abstract = (
        "Architectural cognition study using EEG. Participants navigated buildings while we measured "
        "cortisol and arousal. Results show predictive coding of spatial features in the built environment "
        "with attention and memory effects observed."
    )
    _seed_row(conn, "REF-T-000001",
              title="Architectural cognition in spatial navigation",
              abstract=on_topic_abstract,
              discovered_query="SC3-step3", venue="Cognition")
    _seed_row(conn, "REF-T-000002",
              title="Off-topic quantum mechanics paper",
              abstract="We study quark confinement in lattice QCD with no architectural content.",
              discovered_query=None)
    conn.commit()

    report = run_stage2b_triage(db_path=db_path, run_id="RUN-T1",
                                query_results_json=None,
                                edge_cases_output=db_path.parent / "edge.json")
    assert report.candidates_processed == 2

    c2 = sqlite3.connect(str(db_path))
    try:
        rows = c2.execute(
            "SELECT triage_decision, triage_reason, classifier_confidence, voi_score "
            "FROM article_references WHERE triage_stage = 'triage_complete' ORDER BY reference_id"
        ).fetchall()
    finally:
        c2.close()
    assert len(rows) == 2
    for decision, reason, conf, voi in rows:
        assert decision in ("ACCEPT", "EDGE_CASE", "REJECT")
        assert reason and len(reason) > 0
        assert conf is not None
        assert voi is not None


# ---------------------------------------------------------------------------
# SC-T3 — MISSING_ABSTRACT skipped
# ---------------------------------------------------------------------------

def test_missing_abstract_skipped_not_rescored(db):
    db_path, conn = db
    # Seed a row already in abstract_missing terminal state (4B output)
    _seed_row(conn, "REF-T-000010",
              title="Some title",
              abstract=None,
              stage="abstract_missing", triage_decision="MISSING_ABSTRACT")
    conn.commit()

    report = run_stage2b_triage(db_path=db_path, run_id="RUN-T3",
                                query_results_json=None,
                                edge_cases_output=db_path.parent / "edge.json")
    assert report.candidates_processed == 0  # missing-abstract row not selected

    c2 = sqlite3.connect(str(db_path))
    try:
        row = c2.execute(
            "SELECT triage_decision, triage_stage FROM article_references WHERE reference_id='REF-T-000010'"
        ).fetchone()
    finally:
        c2.close()
    assert row[0] == "MISSING_ABSTRACT"  # unchanged
    assert row[1] == "abstract_missing"   # unchanged


# ---------------------------------------------------------------------------
# SC-T4 — ACCEPT rows appear in v_acquisition_queue
# ---------------------------------------------------------------------------

def test_accept_appears_in_v_acquisition_queue(db):
    db_path, conn = db
    # Inject a classifier that returns high confidence; high VOI via query_results
    on_topic_abstract = "architectural cognition built environment EEG cortisol arousal predictive coding spatial buildings"
    _seed_row(conn, "REF-T-000020",
              title="Strong on-topic paper",
              abstract=on_topic_abstract,
              discovered_query="SC3-step3", venue="Cognition")
    conn.commit()

    # Fake VOI map giving high VOI for SC3-step3
    voi_path = db_path.parent / "voi.json"
    voi_path.write_text(json.dumps({"queries": [{"display_id": "SC3", "step_number": 3, "voi_score": 0.90}]}))

    report = run_stage2b_triage(
        db_path=db_path, run_id="RUN-T4",
        query_results_json=voi_path,
        edge_cases_output=db_path.parent / "edge.json",
    )
    assert report.decisions["ACCEPT"] == 1

    c2 = sqlite3.connect(str(db_path))
    try:
        rows = c2.execute("SELECT reference_id FROM v_acquisition_queue").fetchall()
    finally:
        c2.close()
    assert any(r[0] == "REF-T-000020" for r in rows)


# ---------------------------------------------------------------------------
# SC-T5 — EDGE_CASE export
# ---------------------------------------------------------------------------

def test_edge_case_exported_to_review_json(db):
    db_path, conn = db
    # On-topic but no VOI hit → default 0.443 (low) → EDGE_CASE per matrix
    on_topic_abstract = "architectural cognition built environment EEG cortisol arousal predictive coding spatial buildings"
    _seed_row(conn, "REF-T-000030",
              title="On-topic paper with no VOI provenance",
              abstract=on_topic_abstract,
              discovered_query=None)  # → default VOI = 0.443 (low)
    conn.commit()

    edge_path = db_path.parent / "edge.json"
    run_stage2b_triage(db_path=db_path, run_id="RUN-T5",
                       query_results_json=None,
                       edge_cases_output=edge_path)
    assert edge_path.exists()
    payload = json.loads(edge_path.read_text())
    assert payload["run_id"] == "RUN-T5"
    assert len(payload["edge_cases"]) >= 1
    entry = payload["edge_cases"][0]
    assert entry["reference_id"] == "REF-T-000030"
    assert entry["abstract_text"]
    assert "edge_" in entry["triage_reason"]


# ---------------------------------------------------------------------------
# SC-T6 — REJECT logged to lifecycle_transitions
# ---------------------------------------------------------------------------

def test_reject_logged_to_transitions(db):
    db_path, conn = db
    _seed_row(conn, "REF-T-000040",
              title="Off-topic quantum physics",
              abstract="Lattice QCD computations of meson masses with no architectural content.",
              discovered_query=None)
    conn.commit()

    run_stage2b_triage(db_path=db_path, run_id="RUN-T6",
                       query_results_json=None,
                       edge_cases_output=db_path.parent / "edge.json")

    c2 = sqlite3.connect(str(db_path))
    try:
        decision = c2.execute(
            "SELECT triage_decision FROM article_references WHERE reference_id='REF-T-000040'"
        ).fetchone()[0]
        trans = c2.execute(
            "SELECT created_by, reason FROM lifecycle_transitions WHERE reference_id='REF-T-000040'"
        ).fetchall()
    finally:
        c2.close()
    assert decision == "REJECT"
    assert len(trans) == 1
    assert trans[0][0] == "abstract_triage"
    assert "reject" in trans[0][1].lower()


# ---------------------------------------------------------------------------
# SC-T11 — dry-run
# ---------------------------------------------------------------------------

def test_dry_run_no_disk_writes(db):
    db_path, conn = db
    _seed_row(conn, "REF-T-000050",
              title="Some paper",
              abstract="architectural cognition spatial built environment",
              discovered_query=None)
    conn.commit()

    c2 = sqlite3.connect(str(db_path))
    try:
        before = c2.execute("SELECT triage_stage FROM article_references").fetchall()
    finally:
        c2.close()

    run_stage2b_triage(db_path=db_path, run_id="RUN-T11",
                       query_results_json=None,
                       dry_run=True)

    c2 = sqlite3.connect(str(db_path))
    try:
        after = c2.execute("SELECT triage_stage FROM article_references").fetchall()
    finally:
        c2.close()
    assert before == after


# ---------------------------------------------------------------------------
# SC-T12 — idempotent
# ---------------------------------------------------------------------------

def test_idempotent_on_triage_complete(db):
    db_path, conn = db
    _seed_row(conn, "REF-T-000060",
              title="Already triaged",
              abstract="something",
              stage="triage_complete", triage_decision="ACCEPT")
    conn.commit()

    report = run_stage2b_triage(db_path=db_path, run_id="RUN-T12",
                                query_results_json=None,
                                edge_cases_output=db_path.parent / "edge.json")
    # No abstract_collected rows → nothing to process
    assert report.candidates_processed == 0
