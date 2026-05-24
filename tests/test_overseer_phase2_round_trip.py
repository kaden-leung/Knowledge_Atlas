"""Phase 2 end-to-end round-trip proof.

Source authority:
    docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md §10 acceptance #8

Flow:
    1. AF DB has an accepted paper.
    2. Reconciler tick → article_finder_candidate registered; pending event.
    3. State machine walks metadata_only → ... → extracted (each transition
       creates the appropriate kind artefact + derived_from edge).
    4. Phase 1 article-epistemic builder produces the article_epistemic_record.
    5. Reconciler tick (re-run) → upgrades pending event to matched.
    6. Strict verifier passes every check.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from overseer.article_finder_reconciler import tick as reconciler_tick
from overseer.artefact_registry import (
    increment_fencing_token,
    register,
    update_with_hashes,
)
from overseer.article_epistemic_builder import (
    BUILDER_NAME,
    BUILDER_VERSION,
    PaperInputs,
    build_one,
)
from overseer.build_runs import start as start_build_run
from overseer.candidate_pdf_state import transition
from overseer.verifier_data import verify_strict


def _seed_kind(conn, kind_name):
    conn.execute(
        "INSERT OR IGNORE INTO artefact_kinds (kind_name, owner_pipeline, "
        "support_rule_module, schema_version, active, created_at) VALUES "
        "(?, 'p', 'm', 'v1', 1, '2026-05-23T00:00:00Z')",
        (kind_name,),
    )


def _fake_af_with_one_accepted_paper(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "phase2_round_trip_af.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY,
            doi TEXT, title TEXT, canonical_paper_id TEXT, status TEXT
        );
        INSERT OR IGNORE INTO papers (id, doi, title, canonical_paper_id, status)
        VALUES (1, '10.1/rt', 'Round-trip paper', 'PDF-RT2', 'processed_partial');
    """)
    conn.commit()
    conn.close()
    af = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    af.row_factory = sqlite3.Row
    return af


def test_phase2_round_trip_af_to_extracted_passes_verifier(overseer_db, tmp_path):
    # Register all kinds the round-trip needs.
    for k in (
        "pnu_row", "article_epistemic_record", "article_detail_json",
        "article_finder_candidate", "abstract", "pdf_artifact", "ocr_artifact",
    ):
        _seed_kind(overseer_db, k)

    af_conn = _fake_af_with_one_accepted_paper(tmp_path)
    try:
        # 1. Reconciler picks up the AF paper.
        r1 = reconciler_tick(overseer_db, af_conn=af_conn)
    finally:
        af_conn.close()
    assert r1.af_papers_seen == 1
    assert r1.inserted_pending == 1
    # Pending event exists.
    status = overseer_db.execute(
        "SELECT status FROM cross_db_sync_events "
        "WHERE lifecycle_payload_hash = 'paper:PDF-RT2'"
    ).fetchone()[0]
    assert status == "pending"

    # 2. State machine walks the 5 transitions.
    paper_id = "PDF-RT2"
    transition(overseer_db, paper_id=paper_id,
               from_state="metadata_only", to_state="abstract_only")
    transition(overseer_db, paper_id=paper_id,
               from_state="abstract_only", to_state="candidate_pdf_unverified")
    transition(overseer_db, paper_id=paper_id,
               from_state="candidate_pdf_unverified", to_state="pdf_verified")
    transition(overseer_db, paper_id=paper_id,
               from_state="pdf_verified", to_state="ocr_ready")
    transition(overseer_db, paper_id=paper_id,
               from_state="ocr_ready", to_state="extracted")

    # 3. Phase 1 builder produces the article_epistemic_record content.
    # The state-machine transition to 'extracted' already registered the
    # article_epistemic_record artefact (field_path='extracted'). We can
    # claim it and run the builder.
    epistemic = overseer_db.execute(
        "SELECT artefact_id FROM artefact_registry "
        "WHERE kind = 'article_epistemic_record' AND entity_id = ? "
        "AND active = 1 ORDER BY field_path",
        (paper_id,),
    ).fetchall()
    # Two rows may exist: one without field_path (used by build_one's
    # idempotent register), and one with field_path='extracted' from state
    # transition. The builder writes to the no-field_path row.
    # Register/claim the article_epistemic_record (no field_path).
    record_art = register(
        overseer_db, kind="article_epistemic_record", entity_type="paper",
        entity_id=paper_id, field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    token = increment_fencing_token(overseer_db, record_art.artefact_id)
    brid = start_build_run(
        overseer_db, builder_name=BUILDER_NAME, builder_version=BUILDER_VERSION,
        input_snapshot_hash="sha256:rt2",
    )
    build_one(
        overseer_db, paper_id=paper_id,
        inputs=PaperInputs(
            paper_id=paper_id, support_members=[],
            structured_core_finding="Round-trip claim",
        ),
        build_run_id=brid, fencing_token=token,
    )

    # 4. Second reconciler tick upgrades the pending event to matched.
    af_conn = _fake_af_with_one_accepted_paper(tmp_path)
    try:
        r2 = reconciler_tick(overseer_db, af_conn=af_conn)
    finally:
        af_conn.close()
    assert r2.upgraded_to_matched == 1
    final_status = overseer_db.execute(
        "SELECT status FROM cross_db_sync_events "
        "WHERE lifecycle_payload_hash = 'paper:PDF-RT2'"
    ).fetchone()[0]
    assert final_status == "matched"

    # 5. Strict verifier passes every check.
    report = verify_strict(overseer_db)
    failed = [(c.name, c.failures) for c in report.checks if not c.passed]
    assert report.overall_passed, f"failed: {failed}"
