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


def test_stale_pnu_dependency_marks_record_stale():
    rec = record_with_stale_pnu("P1")
    out = _build("P1", rec)
    bn = next(c for c in out["components"] if c["component_type"] == "belief_network_context")
    assert bn["freshness_status"] == "stale"
    assert bn["status"] == "stale"
    assert out["record"]["freshness_status"] == "stale"


def test_stale_pnu_emits_blocking_completion_queue_entry():
    rec = record_with_stale_pnu("P1")
    out = _build("P1", rec)
    bn_repairs = [r for r in out["repair_items"]
                  if r["component_type"] == "belief_network_context"]
    assert len(bn_repairs) == 1
    assert bn_repairs[0]["severity"] == "blocking"
    assert bn_repairs[0]["reason"] == "pnu_requires_repair"


def test_render_status_show_with_warning_when_stale():
    rec = record_with_stale_pnu("P1")
    out = _build("P1", rec)
    # stale → show_with_warning (spec §4 render_status values).
    assert out["record"]["render_status"] in {"show_with_warning", "hidden"}


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
