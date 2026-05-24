"""Round-trip proofs for Phase 1 of the dependency overseer.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §13 acceptance #8/#9

The two proofs:
  Positive (acceptance #8):
    PNU semantic_hash change → invalidation enqueues rebuild → worker
    claims → builder runs → artefact becomes fresh → verifier passes.

  Negative (acceptance #9):
    PNU raw_hash change only (semantic_hash unchanged) → invalidation
    no-op → no rebuild_queue rows → cosmetic change visible in
    content_hashes history → verifier passes.
"""

from __future__ import annotations

import sqlite3

from overseer.artefact_registry import (
    get,
    increment_fencing_token,
    mark_fresh,
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
from overseer.dependency_edges import add_edge
from overseer.invalidator import invalidate_on_source_change
from overseer.rebuild_queue import claim_one, complete, enqueue as rq_enqueue
from overseer.verifier_data import verify_strict


def _seed_artefact_kind(conn, kind_name):
    conn.execute(
        "INSERT OR IGNORE INTO artefact_kinds (kind_name, owner_pipeline, "
        "support_rule_module, schema_version, active, created_at) VALUES "
        "(?, 'p', 'm', 'v1', 1, '2026-05-23T00:00:00Z')",
        (kind_name,),
    )


def _build_paper(conn, paper_id: str, pnu_artefact_id: str, pnu_hash: str,
                 claim_text: str = "Color reduces stress"):
    """Helper: register article_epistemic_record + claim + run builder."""
    paper = register(
        conn, kind="article_epistemic_record", entity_type="paper",
        entity_id=paper_id, field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    token = increment_fencing_token(conn, paper.artefact_id)
    brid = start_build_run(
        conn, builder_name=BUILDER_NAME, builder_version=BUILDER_VERSION,
        input_snapshot_hash="sha256:snap",
    )
    inputs = PaperInputs(
        paper_id=paper_id,
        support_members=[(pnu_artefact_id, pnu_hash)],
        structured_core_finding=claim_text,
    )
    return build_one(conn, paper_id=paper_id, inputs=inputs,
                     build_run_id=brid, fencing_token=token), paper.artefact_id


def test_positive_round_trip_pnu_change_invalidates_paper_rebuild_passes_verifier(
    overseer_db,
):
    _seed_artefact_kind(overseer_db, "pnu_row")
    _seed_artefact_kind(overseer_db, "article_epistemic_record")

    # 1. PNU registered and fresh with hashes.
    pnu = register(
        overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-RT",
        field_path=None, schema_version="pnu_row.v1",
    )
    pnu_token = increment_fencing_token(overseer_db, pnu.artefact_id)
    pnu_hash_initial = "sha256:pnu_initial"
    update_with_hashes(
        overseer_db, artefact_id=pnu.artefact_id,
        raw_hash="sha256:raw_initial", semantic_hash=pnu_hash_initial,
        build_run_id="br:seed:001", fencing_token=pnu_token,
    )

    # 2. Article epistemic record built from the PNU; dependency edge added.
    build_result, paper_aid = _build_paper(
        overseer_db, "PDF-RT-001", pnu.artefact_id, pnu_hash_initial,
        claim_text="initial claim",
    )
    add_edge(overseer_db, parent_artefact_id=pnu.artefact_id,
             child_artefact_id=paper_aid, edge_kind="supports")
    assert get(overseer_db, paper_aid).freshness_status == "fresh"

    # 3. PNU's semantic content changes (new hash).
    pnu_new_token = increment_fencing_token(overseer_db, pnu.artefact_id)
    pnu_hash_changed = "sha256:pnu_changed"
    update_with_hashes(
        overseer_db, artefact_id=pnu.artefact_id,
        raw_hash="sha256:raw_changed", semantic_hash=pnu_hash_changed,
        build_run_id="br:seed:002", fencing_token=pnu_new_token,
    )

    # 4. Invalidation propagates: dependent paper is marked stale and queued.
    report = invalidate_on_source_change(
        overseer_db, source_artefact_id=pnu.artefact_id, semantic_changed=True,
    )
    assert paper_aid in report.dependents_invalidated
    assert len(report.queue_ids) == 1
    assert get(overseer_db, paper_aid).freshness_status == "stale"

    # 5. Worker claims the rebuild.
    claim = claim_one(overseer_db, worker_id="worker_rt")
    assert claim is not None
    assert claim.artefact_id == paper_aid

    # 6. Builder runs with the updated PNU hash.
    brid = start_build_run(
        overseer_db, builder_name=BUILDER_NAME, builder_version=BUILDER_VERSION,
        input_snapshot_hash="sha256:snap_updated",
    )
    inputs = PaperInputs(
        paper_id="PDF-RT-001",
        support_members=[(pnu.artefact_id, pnu_hash_changed)],
        structured_core_finding="initial claim",
    )
    build_result_2 = build_one(
        overseer_db, paper_id="PDF-RT-001", inputs=inputs,
        build_run_id=brid, fencing_token=claim.fencing_token,
    )

    # 7. Mark queue complete; paper is fresh again.
    complete(overseer_db, claim, worker_id="worker_rt")
    assert get(overseer_db, paper_aid).freshness_status == "fresh"

    # 8. Verifier passes.
    vreport = verify_strict(overseer_db)
    failures = [(c.name, c.failures) for c in vreport.checks if not c.passed]
    assert vreport.overall_passed, f"failures: {failures}"


def test_negative_round_trip_raw_only_change_does_not_invalidate(overseer_db):
    _seed_artefact_kind(overseer_db, "pnu_row")
    _seed_artefact_kind(overseer_db, "article_epistemic_record")

    pnu = register(
        overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-COS",
        field_path=None, schema_version="pnu_row.v1",
    )
    pnu_token = increment_fencing_token(overseer_db, pnu.artefact_id)
    semantic = "sha256:pnu_semantic_stable"
    update_with_hashes(
        overseer_db, artefact_id=pnu.artefact_id,
        raw_hash="sha256:raw_v1", semantic_hash=semantic,
        build_run_id="br:cos:001", fencing_token=pnu_token,
    )

    build_result, paper_aid = _build_paper(
        overseer_db, "PDF-COS-001", pnu.artefact_id, semantic,
    )
    add_edge(overseer_db, parent_artefact_id=pnu.artefact_id,
             child_artefact_id=paper_aid, edge_kind="supports")
    assert get(overseer_db, paper_aid).freshness_status == "fresh"

    # Snapshot rebuild_queue row count before the cosmetic change.
    queue_count_before = overseer_db.execute(
        "SELECT COUNT(*) FROM rebuild_queue"
    ).fetchone()[0]

    # Cosmetic change: same semantic_hash, new raw_hash.
    pnu_new_token = increment_fencing_token(overseer_db, pnu.artefact_id)
    update_with_hashes(
        overseer_db, artefact_id=pnu.artefact_id,
        raw_hash="sha256:raw_v2_DIFFERENT",  # raw changed
        semantic_hash=semantic,              # semantic unchanged
        build_run_id="br:cos:002", fencing_token=pnu_new_token,
    )

    # Invalidator called with semantic_changed=False (caller has decided).
    report = invalidate_on_source_change(
        overseer_db, source_artefact_id=pnu.artefact_id, semantic_changed=False,
    )
    assert report.dependents_invalidated == []
    assert report.queue_ids == []

    # Dependent stays fresh; rebuild_queue gained no new rows.
    assert get(overseer_db, paper_aid).freshness_status == "fresh"
    queue_count_after = overseer_db.execute(
        "SELECT COUNT(*) FROM rebuild_queue"
    ).fetchone()[0]
    assert queue_count_after == queue_count_before

    # Cosmetic change is visible on the artefact: raw_hash changed,
    # semantic_hash unchanged. (Per-PNU content_hashes history is owned by
    # a separate PNU builder which is out of Phase 1 scope; the artefact_registry
    # row is the authoritative point of comparison.)
    pnu_now = get(overseer_db, pnu.artefact_id)
    assert pnu_now.raw_hash == "sha256:raw_v2_DIFFERENT"
    assert pnu_now.semantic_hash == semantic

    # Verifier still passes.
    vreport = verify_strict(overseer_db)
    failures = [(c.name, c.failures) for c in vreport.checks if not c.passed]
    assert vreport.overall_passed, f"failures: {failures}"
