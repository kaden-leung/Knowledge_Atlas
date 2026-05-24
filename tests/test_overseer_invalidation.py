"""Tests for invalidation propagation (overseer.invalidator)."""

from __future__ import annotations

from overseer.artefact_registry import (
    get,
    increment_fencing_token,
    register,
    update_with_hashes,
)
from overseer.dependency_edges import add_edge
from overseer.invalidator import (
    CASCADE_BOUND,
    InvalidationReport,
    invalidate_on_source_change,
)


def _register_pnu(conn, pnu_id="PNU-1"):
    a = register(conn, kind="pnu_row", entity_type="pnu", entity_id=pnu_id,
                 field_path=None, schema_version="pnu_row.v1")
    return a.artefact_id


def _register_paper(conn, paper_id="PDF-1"):
    a = register(conn, kind="article_epistemic_record", entity_type="paper",
                 entity_id=paper_id, field_path=None,
                 schema_version="article_epistemic_layer.v1")
    return a.artefact_id


def _make_dep(conn, pnu_id="PNU-1", paper_id="PDF-1"):
    p = _register_pnu(conn, pnu_id)
    c = _register_paper(conn, paper_id)
    add_edge(conn, parent_artefact_id=p, child_artefact_id=c, edge_kind="supports")
    return p, c


def test_invalidation_noop_when_semantic_unchanged(overseer_db):
    p, c = _make_dep(overseer_db)
    report = invalidate_on_source_change(
        overseer_db, source_artefact_id=p, semantic_changed=False,
    )
    assert isinstance(report, InvalidationReport)
    assert report.semantic_changed is False
    assert report.dependents_invalidated == []
    assert report.queue_ids == []
    # Child remains in its prior freshness state (default 'unknown' here).
    assert get(overseer_db, c).freshness_status == "unknown"


def test_invalidation_marks_dependents_stale_and_enqueues_rebuilds(overseer_db):
    p, c = _make_dep(overseer_db)
    report = invalidate_on_source_change(
        overseer_db, source_artefact_id=p, semantic_changed=True,
    )
    assert report.semantic_changed is True
    assert c in report.dependents_invalidated
    assert len(report.queue_ids) == 1
    assert get(overseer_db, c).freshness_status == "stale"
    # Queue row exists.
    state = overseer_db.execute(
        "SELECT state FROM rebuild_queue WHERE queue_id = ?", (report.queue_ids[0],)
    ).fetchone()[0]
    assert state == "queued"


def test_invalidation_only_touches_direct_children(overseer_db):
    # Build a chain: A -> B -> C. Invalidating A reaches B but not C.
    a = register(overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-A",
                 field_path=None, schema_version="pnu_row.v1").artefact_id
    b = register(overseer_db, kind="article_epistemic_record", entity_type="paper",
                 entity_id="PDF-B", field_path=None,
                 schema_version="article_epistemic_layer.v1").artefact_id
    c = register(overseer_db, kind="article_detail_json", entity_type="paper",
                 entity_id="PDF-B", field_path=None,
                 schema_version="article_detail.v1").artefact_id
    add_edge(overseer_db, parent_artefact_id=a, child_artefact_id=b, edge_kind="supports")
    add_edge(overseer_db, parent_artefact_id=b, child_artefact_id=c, edge_kind="derived_from")
    report = invalidate_on_source_change(
        overseer_db, source_artefact_id=a, semantic_changed=True,
    )
    assert b in report.dependents_invalidated
    assert c not in report.dependents_invalidated


def test_invalidation_raises_cascade_alert_when_exceeds_bound(overseer_db):
    p = _register_pnu(overseer_db, "PNU-W")
    # Register CASCADE_BOUND + 1 children edges from the same parent.
    for i in range(CASCADE_BOUND + 5):
        child = register(
            overseer_db, kind="article_epistemic_record", entity_type="paper",
            entity_id=f"PDF-FAN-{i:03d}", field_path=None,
            schema_version="article_epistemic_layer.v1",
        ).artefact_id
        add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=child,
                 edge_kind="supports")
    report = invalidate_on_source_change(
        overseer_db, source_artefact_id=p, semantic_changed=True,
    )
    assert report.cascade_alert_raised is True
    alert = overseer_db.execute(
        """
        SELECT severity, reason FROM completion_queue
        WHERE artefact_id = ? AND status IN ('open','in_review')
        """,
        (p,),
    ).fetchone()
    assert alert is not None
    assert alert["severity"] == "high"
    assert "cascade_threshold_exceeded" in alert["reason"]
