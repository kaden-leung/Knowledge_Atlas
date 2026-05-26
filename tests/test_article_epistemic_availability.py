"""Graceful-degradation / availability-tier tests (2026-05-25).

The principle: show the best we have now, label the rest, and never gate the
whole layer on a single not-yet-ready input. PNU is one enrichment section, not
a blocker; claim facets and limitations are filled from data available today.

Authority: docs/AEPL_GRACEFUL_DEGRADATION_2026-05-25.md
"""

from __future__ import annotations

from scripts import build_article_epistemic_layer as builder
from tests._article_epistemic_fixtures import (
    complete_record,
    production_typical_record,
)

BR = "aepl-20260525-000001"


def _build(pid, rec):
    return builder.build_record_for_paper(pid, rec, BR)


# ---- claim facets from the signal field (100% coverage, PNU-independent) ----
def test_claim_facets_derived_from_signal():
    rec = complete_record("P1")
    rec["top_claims"][0]["signal"] = "Indicator To Construct Inference"
    out = _build("P1", rec)
    rows = next(c for c in out["components"]
                if c["component_type"] == "claim_rows")["content_json"]["rows"]
    assert rows[0]["claim_type"] == "construct_inference"
    assert rows[0]["epistemic_status"] == "inferred"


def test_claim_facets_direct_measurement():
    ct, ep = builder.derive_claim_facets("Direct Measured Result")
    assert ct == "empirical_measurement" and ep == "directly_measured"


def test_claim_facets_unknown_signal_is_not_invented():
    ct, ep = builder.derive_claim_facets(None)
    assert ct == "unknown" and ep == "unknown"


# ---- limitations surfaced into argument support (100% coverage) -------------
def test_limitations_surfaced_in_argument_support():
    rec = complete_record("P1")
    rec["science_summary"]["limitations"] = "Small convenience sample."
    out = _build("P1", rec)
    ev = next(c for c in out["components"]
              if c["component_type"] == "evidence_strength")
    assert ev["content_json"]["limitations_text"] == "Small convenience sample."


# ---- availability tiers ------------------------------------------------------
def test_availability_summary_core_available_pnu_pending():
    """A stale-PNU (production-typical) record: core sections available now,
    belief-network pending upstream, Stage-2 sections advertised as planned."""
    out = _build("P1", production_typical_record("P1"))
    summary = builder.derive_availability_summary(out["components"])
    assert "primary_claim" in summary["available_now"]
    assert "evidence_strength" in summary["available_now"]
    pending_types = {p["component_type"] for p in summary["pending_upstream"]}
    assert pending_types == {"belief_network_context"}
    assert summary["pending_upstream"][0]["reason"] == "pnu_requires_repair"
    assert "warrant_explanation" in summary["planned_enrichment"]


def test_fresh_pnu_record_has_no_pending_components():
    out = _build("P1", complete_record("P1"))
    summary = builder.derive_availability_summary(out["components"])
    assert summary["pending_upstream"] == []
    assert "belief_network_context" in summary["available_now"]


def test_component_availability_tiering():
    out = _build("P1", production_typical_record("P1"))
    bn = next(c for c in out["components"]
              if c["component_type"] == "belief_network_context")
    pc = next(c for c in out["components"]
              if c["component_type"] == "primary_claim")
    assert builder.derive_component_availability(bn) == "pending_upstream"
    assert builder.derive_component_availability(pc) == "available"
