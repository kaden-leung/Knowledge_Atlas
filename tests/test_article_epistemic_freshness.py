"""Freshness / stale-dependency detection tests.

Authority: docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md §4, §10.
"""

from __future__ import annotations

from scripts import build_article_epistemic_layer as builder
from tests._article_epistemic_fixtures import (
    abstract_only_record,
    complete_record,
    record_with_stale_pnu,
)


def _build(paper_id, rec):
    return builder.build_record_for_paper(paper_id, rec, "aepl-20260523-000001")


def test_fresh_pnu_yields_fresh_record():
    rec = complete_record("P1")
    out = _build("P1", rec)
    assert out["record"]["freshness_status"] == "fresh"
    bn = next(c for c in out["components"] if c["component_type"] == "belief_network_context")
    assert bn["freshness_status"] == "fresh"
    assert bn["status"] == "present"


def test_stale_pnu_is_enrichment_not_record_stale():
    """Graceful degradation (2026-05-25): a stale PNU leaves the belief-network
    section pending but does NOT make the record stale — record freshness is
    computed from CORE (PNU-independent) components only."""
    rec = record_with_stale_pnu("P1")
    out = _build("P1", rec)
    bn = next(c for c in out["components"] if c["component_type"] == "belief_network_context")
    assert bn["freshness_status"] == "stale"   # the section itself is stale
    assert bn["status"] == "stale"
    assert out["record"]["freshness_status"] == "fresh"   # but the record is not


def test_stale_pnu_emits_warning_not_blocking_queue_entry():
    """PNU repair is enrichment, so its completion-queue item is a non-blocking
    warning — it must not appear in the record's blocking_failures."""
    rec = record_with_stale_pnu("P1")
    out = _build("P1", rec)
    bn_repairs = [r for r in out["repair_items"]
                  if r["component_type"] == "belief_network_context"]
    assert len(bn_repairs) == 1
    assert bn_repairs[0]["severity"] == "warning"
    assert bn_repairs[0]["reason"] == "pnu_requires_repair"
    import json as _json
    blocking = _json.loads(out["record"]["blocking_failures_json"])
    assert not any(b.get("reason") == "pnu_requires_repair" for b in blocking)


def test_render_renderable_when_only_enrichment_pending():
    """With core fresh and only PNU pending, the page renders now; the
    belief-network section is shown as pending, not the page suppressed."""
    rec = record_with_stale_pnu("P1")
    out = _build("P1", rec)
    assert out["record"]["render_status"] == "renderable"


def test_missing_pnu_marks_belief_network_source_missing():
    rec = complete_record("P1")
    rec["pnu"] = {}
    out = _build("P1", rec)
    bn = next(c for c in out["components"] if c["component_type"] == "belief_network_context")
    assert bn["status"] == "source_missing"
    assert bn["absence_reason"] == "pnu_row_missing"


def test_unknown_pnu_status_yields_withheld_low_confidence():
    rec = complete_record("P1")
    rec["pnu"]["status"] = "weird_unknown_value"
    rec["pnu"]["requires_repair"] = False
    out = _build("P1", rec)
    bn = next(c for c in out["components"] if c["component_type"] == "belief_network_context")
    assert bn["status"] == "withheld_low_confidence"
    assert bn["freshness_status"] == "unknown"


def test_release_eligible_always_false_in_stage1():
    """Spec §13: release gate is in Phase 4; Stage 1 keeps release_eligible=0."""
    for rec_factory in (complete_record, record_with_stale_pnu, abstract_only_record):
        rec = rec_factory("P1")
        out = _build("P1", rec)
        assert out["record"]["release_eligible"] == 0, \
            f"{rec_factory.__name__} produced release_eligible=1 in Stage 1"
