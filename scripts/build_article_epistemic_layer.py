#!/usr/bin/env python3
"""Deterministic Stage 1 builder for the article-detail epistemic layer.

Reads existing article-detail payloads, derives a per-paper epistemic record,
writes lifecycle-DB rows (records, components, support_sets, build_runs,
completion_queue), and emits a sibling JSON payload for downstream tooling.

This builder NEVER calls an LLM and NEVER invokes a provider SDK. All content
is either lifted directly from existing extracted fields or computed by
deterministic rules; everything else is marked with a typed absence reason.

Authorities:
    docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md   (controlling)
    docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_PANEL_SYNTHESIS_2026-05-23.md
    docs/HANDOFF_EPISTEMIC_LAYER_IMPLEMENTATION_2026-05-23.md

Usage:
    python3 scripts/build_article_epistemic_layer.py
    python3 scripts/build_article_epistemic_layer.py --paper-ids PDF-0007 PDF-0181
    python3 scripts/build_article_epistemic_layer.py --input PATH --output PATH --db PATH
    python3 scripts/build_article_epistemic_layer.py --dry-run    # no DB / JSON writes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "data" / "ka_payloads" / "article_details.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "ka_payloads" / "article_epistemic_layer.json"
DEFAULT_DB_CANDIDATES = (
    REPO_ROOT / "data" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "data" / "ka_payloads" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "160sp" / "pipeline_lifecycle_full.db",
)

SCHEMA_VERSION = "article_epistemic_layer.v1"
BUILDER_VERSION = "article_epistemic_builder.v1"

COMPONENT_TYPES = (
    "primary_claim",
    "claim_rows",
    "evidence_strength",
    "defeaters",
    "belief_network_context",
    "answer_shape_status",
    "provenance_summary",
)

# PNU statuses considered "fresh" for belief-network-context purposes.
# 'needs_review' is treated as fresh-but-unreviewed (the row exists, the
# review queue has it, the snapshot has not moved). 'requires_repair' or any
# value that indicates the row is broken is downstream-handled as stale.
PNU_FRESH_STATUSES = frozenset({"verified", "approved", "review_passed", "needs_review"})
PNU_STALE_STATUSES = frozenset({"stale", "needs_repair", "missing"})

# Field-policy defaults. Stage 1 only emits deterministic_only or
# extracted_only content. llm_enrichable / human_only fields are not produced
# here but the policy is declared on each component for downstream stages.
FIELD_POLICY_BY_COMPONENT = {
    "primary_claim": "extracted_only",
    "claim_rows": "extracted_only",
    "evidence_strength": "deterministic_only",
    "defeaters": "extracted_only",
    "belief_network_context": "deterministic_only",
    "answer_shape_status": "deterministic_only",
    "provenance_summary": "deterministic_only",
}

# Defeater target/defeat-kind vocabularies (spec §8; Pollock's rebutting vs.
# undercutting distinction). Stage 1 extracts no defeater rows, but the row
# contract is fixed NOW so that any future row carries a target and a defeat
# kind, and so the two builders in this repo cannot disagree about what a
# defeater is. Mirrored in verify_article_epistemic_layer_contract.py and in
# overseer/article_epistemic_builder.py:_classify_defeaters — keep in sync.
DEFEATER_TARGET_KINDS = (
    "claim", "warrant", "method", "measurement",
    "interpretation", "generalizability", "mechanism", "application",
)
DEFEATER_DEFEAT_KINDS = ("rebutting", "undercutting")

# The shape every defeater row must satisfy once extraction lands. Embedded in
# the defeaters component content so downstream code and the renderer can read
# the contract from the artefact itself.
DEFEATER_ROW_CONTRACT = {
    "required_fields": ["target_kind", "defeat_kind", "content"],
    "target_kinds": list(DEFEATER_TARGET_KINDS),
    "defeat_kinds": list(DEFEATER_DEFEAT_KINDS),
}

# Graceful-degradation availability tiers (2026-05-25 design decision: show the
# best we have now, label the rest, don't gate the whole layer on any one input).
#   CORE components are derivable from extracted/deterministic fields available
#   today; they alone determine record freshness and renderability.
#   ENRICHMENT components depend on upstream work not yet done (PNU repair); when
#   unavailable they render as a typed "pending" section and DO NOT block the
#   record or the page.
#   PLANNED sections are Stage-2 LLM enrichment, advertised as "coming" so the
#   page shows its full intended shape honestly.
CORE_COMPONENT_TYPES = frozenset({
    "primary_claim", "claim_rows", "evidence_strength", "defeaters",
    "answer_shape_status", "provenance_summary",
})
ENRICHMENT_COMPONENT_TYPES = frozenset({"belief_network_context"})
PLANNED_STAGE2_SECTIONS = (
    "warrant_explanation", "rebuttal_synthesis",
    "competing_account_summary", "plain_language_interpretation",
)

# Map the upstream `signal` label to a claim type + epistemic character. This is
# deterministic and PNU-independent; it replaces the hardcoded "unknown" facets
# with real values for the 100% of papers that carry a signal.
SIGNAL_TO_FACETS = {
    "direct measured result": ("empirical_measurement", "directly_measured"),
    "table or figure reported result": ("reported_result", "directly_measured"),
    "direct participant report": ("participant_report", "self_reported"),
    "indicator to construct inference": ("construct_inference", "inferred"),
    "synthesis across claims": ("synthesis", "synthesized"),
    "discussion level interpretation": ("interpretation", "interpreted"),
}


def derive_claim_facets(signal: str | None) -> tuple[str, str]:
    """Return (claim_type, epistemic_status) from the upstream signal label."""
    if not signal:
        return "unknown", "unknown"
    claim_type, epistemic = SIGNAL_TO_FACETS.get(signal.strip().lower(), (signal, "unknown"))
    return claim_type, epistemic


# ---------------------------------------------------------------------------
# Canonical JSON + hashing
# ---------------------------------------------------------------------------

def canonical_dumps(obj: Any) -> bytes:
    """Canonical JSON: UTF-8, sorted keys, compact separators (spec §6)."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_canonical(obj: Any) -> str:
    return sha256_hex(canonical_dumps(obj))


def normalize_claim_text(text: str | None) -> str:
    """Whitespace-canonical form used for claim identity hashing."""
    if text is None:
        return ""
    return " ".join(text.split())


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# ID constructors (spec §3)
# ---------------------------------------------------------------------------

def make_record_id(paper_id: str) -> str:
    return f"{SCHEMA_VERSION}:{paper_id}"


def make_component_id(record_id: str, component_type: str, local_id: str = "0") -> str:
    return f"{record_id}:{component_type}:{local_id}"


def make_claim_id(paper_id: str, claim_text: str) -> str:
    canonical = normalize_claim_text(claim_text)
    digest = sha256_hex(canonical.encode("utf-8"))[:16]
    return f"claim:{paper_id}:{digest}"


def make_support_set_id(members: Sequence[dict]) -> str:
    """`support_set_id` is derived only from the canonical member identities,
    not from human-volatile fields. Members must be a list of dicts; the
    function sorts them deterministically before hashing."""
    canonical_members = sorted(
        members,
        key=lambda m: (
            m.get("source_artifact_id", ""),
            m.get("source_field_path", ""),
        ),
    )
    digest = sha256_hex(canonical_dumps(canonical_members))[:16]
    return f"support_set:{digest}"


def make_build_run_id(started_at: str, conn: sqlite3.Connection | None = None) -> str:
    """Spec-format build_run_id: aepl-YYYYMMDD-NNNNNN.

    NNNNNN is the next available sequence for that UTC date. With a connection
    we query the DB so concurrent same-day runs get monotonically increasing
    IDs. Without a connection (dry runs, fresh DB) we use microseconds so two
    in-process builds in the same second still get distinct IDs.
    """
    date_part = started_at[:10].replace("-", "")  # YYYYMMDD
    prefix = f"aepl-{date_part}-"
    if conn is not None:
        row = conn.execute(
            "SELECT build_run_id FROM article_epistemic_build_runs "
            "WHERE build_run_id LIKE ? ORDER BY build_run_id DESC LIMIT 1",
            (prefix + "%",),
        ).fetchone()
        next_seq = 1 if row is None else int(row[0].rsplit("-", 1)[-1]) + 1
    else:
        # Microsecond fallback for dry-run callers and unit tests.
        next_seq = datetime.now(timezone.utc).microsecond or 1
    return f"{prefix}{next_seq:06d}"


# ---------------------------------------------------------------------------
# Support-set builders
# ---------------------------------------------------------------------------

def _source_artifact_id_for_field(paper_id: str, field: str) -> str:
    return f"article_details_json:{paper_id}:{field}"


def _member(
    paper_id: str,
    field: str,
    value: Any,
    source_record_id: str | None = None,
    source_kind: str = "article_details_field",
) -> dict:
    """Build one support-set member.

    `value` is the value the support set is derived from; we hash it so that
    edits to that value invalidate downstream freshness.
    """
    member = {
        "source_artifact_id": _source_artifact_id_for_field(paper_id, field),
        "source_kind": source_kind,
        "source_path_or_table": "data/ka_payloads/article_details.json",
        "source_record_id": source_record_id or paper_id,
        "source_field_path": f"details.{paper_id}.{field}",
        "source_hash": sha256_canonical(value),
    }
    return member


def support_set_for_primary_claim(paper_id: str, rec: dict) -> list[dict]:
    members = [
        _member(paper_id, "top_claims", rec.get("top_claims", [])),
        _member(paper_id, "science_summary.core_finding",
                rec.get("science_summary", {}).get("core_finding")),
        _member(paper_id, "article_meta.main_conclusion",
                rec.get("article_meta", {}).get("main_conclusion")),
    ]
    return members


def support_set_for_claim_rows(paper_id: str, rec: dict) -> list[dict]:
    return [_member(paper_id, "top_claims", rec.get("top_claims", []))]


def support_set_for_evidence_strength(paper_id: str, rec: dict) -> list[dict]:
    # Includes the study-record sources (article_meta, instruments,
    # science_summary) so the surfaced sample size / design / instruments /
    # limitations are covered by this component's freshness, not orphaned.
    return [
        _member(paper_id, "top_claims", rec.get("top_claims", [])),
        _member(paper_id, "argumentation", rec.get("argumentation", {})),
        _member(paper_id, "evidence_profile", rec.get("evidence_profile", {})),
        _member(paper_id, "article_meta", rec.get("article_meta", {})),
        _member(paper_id, "instruments", rec.get("instruments", [])),
        _member(paper_id, "science_summary", rec.get("science_summary", {})),
    ]


def support_set_for_defeaters(paper_id: str, rec: dict) -> list[dict]:
    return [
        _member(paper_id, "argumentation", rec.get("argumentation", {})),
        _member(paper_id, "top_claims", rec.get("top_claims", [])),
        _member(paper_id, "contradicting_papers", rec.get("contradicting_papers", [])),
    ]


def support_set_for_belief_network_context(paper_id: str, rec: dict) -> list[dict]:
    return [
        _member(paper_id, "pnu", rec.get("pnu", {}), source_kind="pnu_row"),
    ]


def support_set_for_answer_shape_status(paper_id: str, rec: dict) -> list[dict]:
    return [
        _member(paper_id, "top_claims", rec.get("top_claims", [])),
        _member(paper_id, "science_summary", rec.get("science_summary", {})),
        _member(paper_id, "evidence_profile", rec.get("evidence_profile", {})),
    ]


def support_set_for_provenance_summary(paper_id: str, rec: dict) -> list[dict]:
    """Provenance summary is derived from the full record; use a single member
    keyed at the record root to make staleness coarse but honest."""
    return [
        _member(paper_id, "<record>", {
            "top_claims": rec.get("top_claims", []),
            "argumentation": rec.get("argumentation", {}),
            "evidence_profile": rec.get("evidence_profile", {}),
            "pnu": rec.get("pnu", {}),
            "article_meta": rec.get("article_meta", {}),
            "science_summary": rec.get("science_summary", {}),
            "contradicting_papers": rec.get("contradicting_papers", []),
            "supporting_papers": rec.get("supporting_papers", []),
        }),
    ]


# ---------------------------------------------------------------------------
# Primary claim selection (spec §8)
# ---------------------------------------------------------------------------

def _is_nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def select_primary_claim(rec: dict) -> tuple[dict | None, str]:
    """Return (chosen_claim_dict, rule_name) per spec §8.

    The rule_name records WHICH rule fired so the assignment is auditable.
    """
    # Rule 1: explicit structured core finding (a flagged extracted field).
    # Current payloads have science_summary.core_finding (text), not a
    # structured one with explicit "is_core_finding": True markers. Rule 1 is
    # therefore not satisfiable from the current payload set and falls
    # through to rule 2.

    # Rule 2: top_claims sorted by (support_count desc, attack_count asc,
    # credence desc, source order asc, canonical text).
    top_claims = rec.get("top_claims") or []
    candidates = [c for c in top_claims if isinstance(c, dict) and _is_nonempty_str(c.get("finding"))]
    if candidates:
        def sort_key(item: tuple[int, dict]) -> tuple:
            idx, c = item
            support = int(c.get("support_count") or 0)
            attack = int(c.get("attack_count") or 0)
            credence = float(c.get("credence") or 0.0)
            return (
                -support,
                attack,
                -credence,
                idx,
                normalize_claim_text(c.get("finding", "")),
            )
        ordered = sorted(enumerate(candidates), key=sort_key)
        return ordered[0][1], "top_claims_ranked"

    # Rule 3: article-level main conclusion.
    main_conclusion = (rec.get("article_meta") or {}).get("main_conclusion")
    if _is_nonempty_str(main_conclusion):
        synthetic = {
            "finding": main_conclusion,
            "signal": "Article Main Conclusion",
            "warrant": "Article-Level Conclusion",
            "credence": None,
            "support_count": None,
            "attack_count": None,
            "qualifier": None,
        }
        return synthetic, "article_main_conclusion"

    # Rule 4: science_summary.core_finding.
    core_finding = (rec.get("science_summary") or {}).get("core_finding")
    if _is_nonempty_str(core_finding):
        synthetic = {
            "finding": core_finding,
            "signal": "Science Summary Core Finding",
            "warrant": "Science Summary Core Finding",
            "credence": None,
            "support_count": None,
            "attack_count": None,
            "qualifier": None,
        }
        return synthetic, "science_summary_core_finding"

    # Rule 5: none — emit missing primary-claim component.
    return None, "no_primary_claim_extracted"


# ---------------------------------------------------------------------------
# Component builders
# ---------------------------------------------------------------------------

def _component_base(
    record_id: str,
    paper_id: str,
    component_type: str,
    content: dict,
    support_set_id: str,
    support_set_hash: str,
    *,
    component_status: str,
    source_mode: str,
    freshness_status: str = "fresh",
    review_status: str = "unreviewed",
    render_policy: str = "render",
    provenance: dict | None = None,
    absence_reason: str | None = None,
    display_label: str | None = None,
) -> dict:
    """Assemble a component object used both for DB row and public payload."""
    component_id = make_component_id(record_id, component_type)
    field_policy = FIELD_POLICY_BY_COMPONENT[component_type]
    display = display_label or component_type.replace("_", " ").title()
    content_with_absence: dict = dict(content)
    if absence_reason is not None:
        content_with_absence["absence_reason"] = absence_reason
    content_hash = sha256_canonical(content_with_absence)
    return {
        "component_id": component_id,
        "component_type": component_type,
        "status": component_status,
        "source_mode": source_mode,
        "field_policy": field_policy,
        "review_status": review_status,
        "freshness_status": freshness_status,
        "render_policy": render_policy,
        "display_label": display,
        "content_json": content_with_absence,
        "content_hash": content_hash,
        "support_set_id": support_set_id,
        "support_set_hash": support_set_hash,
        "provenance": provenance or {},
        "verification": {},
        "absence_reason": absence_reason,
    }


def build_primary_claim_component(
    paper_id: str,
    record_id: str,
    rec: dict,
    chosen: dict | None,
    rule_name: str,
    support_set_id: str,
    support_set_hash: str,
) -> tuple[dict, dict | None]:
    """Return (component, repair_item_or_none)."""
    if chosen is None:
        component = _component_base(
            record_id, paper_id, "primary_claim",
            content={"claim_id": None, "rule": rule_name},
            support_set_id=support_set_id, support_set_hash=support_set_hash,
            component_status="not_extracted",
            source_mode="missing",
            freshness_status="fresh",
            review_status="unreviewed",
            render_policy="render_with_warning",
            provenance={"selection_rule": rule_name},
            absence_reason="primary_claim_not_extracted",
            display_label="Primary Claim",
        )
        repair = {
            "paper_id": paper_id,
            "component_type": "primary_claim",
            "reason": "primary_claim_not_extracted",
            "severity": "blocking",
            "next_action": "Run claim extraction on the paper and rebuild epistemic layer.",
        }
        return component, repair

    claim_text = chosen.get("finding", "")
    claim_id = make_claim_id(paper_id, claim_text)
    content = {
        "claim_id": claim_id,
        "rule": rule_name,
        "source_text": claim_text,
        "canonical_text": normalize_claim_text(claim_text),
        "signal": chosen.get("signal"),
        "warrant": chosen.get("warrant"),
        "qualifier": chosen.get("qualifier"),
        "source_credence": chosen.get("credence"),
        "support_count": chosen.get("support_count"),
        "attack_count": chosen.get("attack_count"),
    }
    component = _component_base(
        record_id, paper_id, "primary_claim",
        content=content,
        support_set_id=support_set_id, support_set_hash=support_set_hash,
        component_status="present",
        source_mode="extracted",
        freshness_status="fresh",
        review_status="unreviewed",
        render_policy="render",
        provenance={"selection_rule": rule_name, "source_field": "details.top_claims"},
        display_label="Primary Claim",
    )
    return component, None


def build_claim_rows_component(
    paper_id: str,
    record_id: str,
    rec: dict,
    support_set_id: str,
    support_set_hash: str,
) -> dict:
    top_claims = rec.get("top_claims") or []
    rows = []
    for c in top_claims:
        if not isinstance(c, dict):
            continue
        finding = c.get("finding") or ""
        claim_type, epistemic_status = derive_claim_facets(c.get("signal"))
        rows.append({
            "claim_id": make_claim_id(paper_id, finding),
            "source_text": finding,
            "canonical_text": normalize_claim_text(finding),
            "claim_scope": "unknown",
            "claim_type": claim_type,
            "claim_polarity": "unknown",
            "assertion_status": "asserted" if _is_nonempty_str(finding) else "unknown",
            "epistemic_status": epistemic_status,
            "signal": c.get("signal"),
            "warrant": c.get("warrant"),
            "qualifier": c.get("qualifier"),
            "source_credence": c.get("credence"),
            "support_count": c.get("support_count"),
            "attack_count": c.get("attack_count"),
        })

    if not rows:
        content = {"rows": [], "count": 0}
        absence_reason = "no_claims_extracted"
        status = "not_extracted"
        source_mode = "missing"
        render_policy = "render_with_warning"
    else:
        content = {"rows": rows, "count": len(rows)}
        absence_reason = None
        status = "present"
        source_mode = "extracted"
        render_policy = "render"

    return _component_base(
        record_id, paper_id, "claim_rows",
        content=content,
        support_set_id=support_set_id, support_set_hash=support_set_hash,
        component_status=status,
        source_mode=source_mode,
        freshness_status="fresh",
        review_status="unreviewed",
        render_policy=render_policy,
        provenance={"source_field": "details.top_claims"},
        absence_reason=absence_reason,
        display_label="Claim Rows",
    )


def build_evidence_strength_component(
    paper_id: str,
    record_id: str,
    rec: dict,
    primary: dict | None,
    support_set_id: str,
    support_set_hash: str,
) -> dict:
    """Evidence strength is tied to the primary claim, not to the article (spec §8).

    Confidence basis is recorded explicitly. Stage 1 never upgrades confidence
    on the basis of prose.
    """
    ev_profile = rec.get("evidence_profile") or {}
    arg = rec.get("argumentation") or {}
    article_meta = rec.get("article_meta") or {}
    sci = rec.get("science_summary") or {}
    instruments = [i for i in (rec.get("instruments") or []) if isinstance(i, str)]
    # Study record: PNU-independent context surfaced from data we already have
    # (article_meta 100%, science_summary 100%, instruments 39%, sample_n 66%).
    study_record = {
        "sample_n": article_meta.get("sample_n") or article_meta.get("sample_size"),
        "article_type": article_meta.get("article_type"),
        "study_design": sci.get("methods_and_design"),
        "key_statistics": sci.get("key_statistics"),
        "limitations_text": sci.get("limitations"),
        "instruments": instruments,
        "instrument_count": len(instruments),
    }
    if primary is None:
        content = {
            "claim_id": None,
            "source_credence": None,
            "confidence_basis": "no_primary_claim",
            # This component describes the SHAPE of the argument graph around the
            # claim (support/attack counts, atlas credence). It is NOT a measure
            # of how severely the claim has been tested (Mayo). The name is kept
            # for schema stability; the semantics are stated explicitly here.
            "measure_semantics": "argument_support_not_severity",
            "support_count": None,
            "attack_count": None,
            "atlas_credence_mean": ev_profile.get("atlas_credence_mean"),
            "atlas_credence_percentile": ev_profile.get("atlas_credence_percentile"),
            "study_record": study_record,
        }
        return _component_base(
            record_id, paper_id, "evidence_strength",
            content=content,
            support_set_id=support_set_id, support_set_hash=support_set_hash,
            component_status="not_applicable",
            source_mode="deterministic_derived",
            freshness_status="fresh",
            review_status="not_required",
            render_policy="render_with_warning",
            provenance={"basis": "deterministic_from_argumentation_and_evidence_profile"},
            absence_reason="depends_on_primary_claim",
            display_label="Argument Support",
        )

    primary_text = primary.get("finding") or ""
    claim_id = make_claim_id(paper_id, primary_text)
    content = {
        "claim_id": claim_id,
        "source_credence": primary.get("credence"),
        "confidence_basis": "extracted_per_claim_credence",
        # See note in the not_applicable branch: argument-graph support, not
        # severity. credence/support/attack counts are upstream bookkeeping.
        "measure_semantics": "argument_support_not_severity",
        # Study record: sample size, design, key stats, limitations, instruments
        # surfaced from data available today (PNU-independent).
        "study_record": study_record,
        "support_count": primary.get("support_count"),
        "attack_count": primary.get("attack_count"),
        "dominant_stance": arg.get("dominant_stance"),
        "atlas_credence_mean": ev_profile.get("atlas_credence_mean"),
        "atlas_credence_percentile": ev_profile.get("atlas_credence_percentile"),
        "search_target_count": arg.get("search_target_count"),
        "support_edge_count": arg.get("support_edge_count"),
        "attack_edge_count": arg.get("attack_edge_count"),
    }
    return _component_base(
        record_id, paper_id, "evidence_strength",
        content=content,
        support_set_id=support_set_id, support_set_hash=support_set_hash,
        component_status="present",
        source_mode="deterministic_derived",
        freshness_status="fresh",
        review_status="unreviewed",
        render_policy="render",
        provenance={"basis": "primary_claim_credence_plus_argumentation_counts"},
        display_label="Argument Support",
    )


def build_defeaters_component(
    paper_id: str,
    record_id: str,
    rec: dict,
    support_set_id: str,
    support_set_hash: str,
) -> tuple[dict, dict | None]:
    """Defeaters are target-specific. Stage 1 does not extract structured
    defeater rows from prose; it only reconciles counts against extracted rows.

    Returns (component, repair_or_None).
    """
    arg = rec.get("argumentation") or {}
    attack_count = int(arg.get("attack_edge_count") or 0)
    contradiction_count = int(arg.get("contradiction_count") or 0)
    contradicting_papers = rec.get("contradicting_papers") or []
    mapped_rows: list = []  # Stage 1 does not synthesize defeater rows.
    repair: dict | None = None

    if attack_count == 0 and contradiction_count == 0 and not contradicting_papers:
        content = {
            "rows": mapped_rows,
            "row_contract": DEFEATER_ROW_CONTRACT,
            "attack_count_argumentation": attack_count,
            "contradiction_count_argumentation": contradiction_count,
            "no_defeater_basis": "no_defeater_extracted",
            # Stage 1 never extracts defeater prose, so it can assert
            # "we did not extract any" but NOT "none exist" (Pollock).
            "defeater_existence": "no_defeater_extracted",
        }
        component = _component_base(
            record_id, paper_id, "defeaters",
            content=content,
            support_set_id=support_set_id, support_set_hash=support_set_hash,
            component_status="not_extracted",
            source_mode="missing",
            freshness_status="fresh",
            review_status="not_required",
            render_policy="render",
            provenance={"basis": "argumentation_counts"},
            absence_reason="no_defeater_extracted",
            display_label="Defeaters",
        )
        return component, None

    # Attack/contradiction count is non-zero but Stage 1 has no mapped rows.
    if attack_count > 0 and not mapped_rows:
        content = {
            "rows": mapped_rows,
            "row_contract": DEFEATER_ROW_CONTRACT,
            "attack_count_argumentation": attack_count,
            "contradiction_count_argumentation": contradiction_count,
            "contradicting_paper_count": len(contradicting_papers),
            "no_defeater_basis": None,
            "defeater_existence": "defeaters_likely_present_unextracted",
        }
        component = _component_base(
            record_id, paper_id, "defeaters",
            content=content,
            support_set_id=support_set_id, support_set_hash=support_set_hash,
            component_status="not_extracted",
            source_mode="missing",
            freshness_status="fresh",
            review_status="human_review_required",
            render_policy="render_with_warning",
            provenance={"basis": "argumentation_counts"},
            absence_reason="attack_count_without_mapped_rows",
            display_label="Defeaters",
        )
        repair = {
            "paper_id": paper_id,
            "component_type": "defeaters",
            "reason": "attack_count_without_mapped_rows",
            "severity": "warning",
            "next_action": (
                f"argumentation.attack_edge_count={attack_count} but no defeater "
                "rows are extracted; queue structured defeater extraction."
            ),
        }
        return component, repair

    # Contradicting papers exist but no per-claim defeater rows are extracted.
    content = {
        "rows": mapped_rows,
        "row_contract": DEFEATER_ROW_CONTRACT,
        "attack_count_argumentation": attack_count,
        "contradiction_count_argumentation": contradiction_count,
        "contradicting_paper_count": len(contradicting_papers),
        "no_defeater_basis": None,
        "defeater_existence": "defeaters_likely_present_unextracted",
    }
    component = _component_base(
        record_id, paper_id, "defeaters",
        content=content,
        support_set_id=support_set_id, support_set_hash=support_set_hash,
        component_status="not_extracted",
        source_mode="missing",
        freshness_status="fresh",
        review_status="unreviewed",
        render_policy="render_with_warning",
        provenance={"basis": "argumentation_counts_and_contradicting_papers"},
        absence_reason="defeater_rows_pending_extraction",
        display_label="Defeaters",
    )
    repair = {
        "paper_id": paper_id,
        "component_type": "defeaters",
        "reason": "defeater_rows_pending_extraction",
        "severity": "warning",
        "next_action": (
            f"contradicting_paper_count={len(contradicting_papers)}, "
            f"contradiction_count={contradiction_count}; extract structured "
            "defeater rows linked to claims."
        ),
    }
    return component, repair


def build_belief_network_context_component(
    paper_id: str,
    record_id: str,
    rec: dict,
    support_set_id: str,
    support_set_hash: str,
) -> tuple[dict, dict | None]:
    pnu = rec.get("pnu") or {}
    status_raw = pnu.get("status") or "missing"
    panel_status = pnu.get("panel_status")
    requires_repair = bool(pnu.get("requires_repair"))
    pnu_hash = sha256_canonical(pnu) if pnu else None

    pnu_freshness = "fresh"
    repair: dict | None = None
    if not pnu:
        component_status = "source_missing"
        absence_reason = "pnu_row_missing"
        pnu_freshness = "unknown"
    elif requires_repair or status_raw in PNU_STALE_STATUSES:
        component_status = "stale"
        absence_reason = "pnu_requires_repair" if requires_repair else "pnu_stale"
        pnu_freshness = "stale"
        repair = {
            "paper_id": paper_id,
            "component_type": "belief_network_context",
            "reason": absence_reason,
            # Enrichment, not a gate (2026-05-25 graceful-degradation decision):
            # PNU staleness leaves this ONE section pending; it does not block
            # the record, the page, or release of the core epistemic reading.
            "severity": "warning",
            "next_action": "Refresh PNU registry row and rebuild; belief-network "
                           "section renders as 'pending' until then (non-blocking).",
        }
    elif status_raw not in PNU_FRESH_STATUSES:
        component_status = "withheld_low_confidence"
        absence_reason = f"pnu_status_unknown:{status_raw}"
        pnu_freshness = "unknown"
    else:
        component_status = "present"
        absence_reason = None

    content = {
        "pnu_status": status_raw,
        "pnu_panel_status": panel_status,
        "pnu_short_status": pnu.get("short_status"),
        "pnu_long_status": pnu.get("long_status"),
        "pnu_verifier_status": pnu.get("verifier_status"),
        "pnu_requires_repair": requires_repair,
        "pnu_source_modality": pnu.get("source_modality"),
        "pnu_generation_method": pnu.get("generation_method"),
        "pnu_panel_basis_count": pnu.get("panel_basis_count"),
        "pnu_hash": pnu_hash,
    }

    component = _component_base(
        record_id, paper_id, "belief_network_context",
        content=content,
        support_set_id=support_set_id, support_set_hash=support_set_hash,
        component_status=component_status,
        source_mode="deterministic_derived" if pnu else "missing",
        freshness_status=pnu_freshness,
        review_status="unreviewed" if pnu else "not_required",
        render_policy="render_with_warning" if absence_reason else "render",
        provenance={"basis": "pnu_row_summary"},
        absence_reason=absence_reason,
        display_label="Belief Network Context",
    )
    return component, repair


def build_answer_shape_status_component(
    paper_id: str,
    record_id: str,
    rec: dict,
    primary: dict | None,
    support_set_id: str,
    support_set_hash: str,
) -> dict:
    """Assign one of: toulmin, field_map, comparison, mechanism, review_synthesis,
    mixed, unknown. The deterministic rule that fired is recorded."""
    sci = rec.get("science_summary") or {}
    arg = rec.get("argumentation") or {}
    article_meta = rec.get("article_meta") or {}
    article_type = (article_meta.get("article_type") or "").lower()

    # Rule order is deterministic; the first matching rule fires.
    if article_type in {"review", "systematic_review", "meta_analysis"}:
        shape, rule = "review_synthesis", "article_type_is_review"
    elif primary is not None and (primary.get("warrant") or "").lower().startswith("mechanism"):
        shape, rule = "mechanism", "primary_claim_warrant_is_mechanism"
    elif int(arg.get("contradiction_count") or 0) > 0:
        shape, rule = "comparison", "argumentation_has_contradictions"
    elif primary is not None and (primary.get("signal") or "").lower().startswith("direct measured"):
        shape, rule = "field_map", "primary_claim_is_direct_measurement"
    elif primary is not None and primary.get("warrant"):
        shape, rule = "toulmin", "primary_claim_has_warrant"
    else:
        shape, rule = "unknown", "no_rule_fired"

    content = {
        "answer_shape": shape,
        "rule": rule,
        "primary_claim_signal": (primary or {}).get("signal"),
        "primary_claim_warrant": (primary or {}).get("warrant"),
        "article_type": article_meta.get("article_type"),
    }
    return _component_base(
        record_id, paper_id, "answer_shape_status",
        content=content,
        support_set_id=support_set_id, support_set_hash=support_set_hash,
        component_status="present" if shape != "unknown" else "not_applicable",
        source_mode="deterministic_derived",
        freshness_status="fresh",
        review_status="not_required",
        render_policy="render" if shape != "unknown" else "render_with_warning",
        provenance={"basis": rule},
        absence_reason=None if shape != "unknown" else "no_answer_shape_rule_fired",
        display_label="Answer Shape",
    )


def build_provenance_summary_component(
    paper_id: str,
    record_id: str,
    rec: dict,
    components_so_far: list[dict],
    support_set_id: str,
    support_set_hash: str,
) -> dict:
    """Aggregate provenance: count present/absent components and list source
    artifact IDs the record depends on."""
    present = [c["component_type"] for c in components_so_far if c["status"] == "present"]
    absent = [c["component_type"] for c in components_so_far if c["status"] != "present"]
    content = {
        "components_present": sorted(present),
        "components_absent": sorted(absent),
        "builder_version": BUILDER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": [
            f"article_details_json:{paper_id}",
            f"pnu:{paper_id}",
        ],
    }
    return _component_base(
        record_id, paper_id, "provenance_summary",
        content=content,
        support_set_id=support_set_id, support_set_hash=support_set_hash,
        component_status="present",
        source_mode="deterministic_derived",
        freshness_status="fresh",
        review_status="not_required",
        render_policy="render",
        provenance={"basis": "aggregate_of_record_components"},
        display_label="Provenance Summary",
    )


# ---------------------------------------------------------------------------
# Record-level status derivation
# ---------------------------------------------------------------------------

def derive_record_statuses(components: list[dict]) -> dict:
    """Map component-level state up to record-level statuses (spec §4).

    Graceful degradation (2026-05-25): record freshness and renderability are
    computed from CORE components only. Enrichment components (belief_network_
    context / PNU) may be pending/stale without making the record stale, hidden,
    or unreleasable — they render as a typed "pending" section instead. This is
    the "show the best we have now, label the rest" principle.
    """
    statuses = {c["component_type"]: c["status"] for c in components}
    core_freshness = [c["freshness_status"] for c in components
                      if c["component_type"] in CORE_COMPONENT_TYPES]

    has_primary = statuses.get("primary_claim") == "present"
    has_claim_rows = statuses.get("claim_rows") == "present"
    has_evidence = statuses.get("evidence_strength") == "present"

    if has_primary and has_claim_rows and has_evidence:
        extraction_status = "complete"
    elif has_primary or has_claim_rows:
        extraction_status = "partial"
    elif any(s == "present" for s in statuses.values()):
        extraction_status = "minimal"
    elif all(s in ("source_missing", "extraction_failed") for s in statuses.values()):
        extraction_status = "failed"
    else:
        extraction_status = "absent"

    # Freshness reflects CORE only — PNU staleness no longer poisons the record.
    if "stale" in core_freshness:
        freshness_status = "stale"
    elif "unknown" in core_freshness:
        freshness_status = "unknown"
    else:
        freshness_status = "fresh"

    # Render status from core: hide only when there is no claim to show at all;
    # show-with-warning when core is stale or the primary claim is missing;
    # otherwise renderable even if enrichment sections are pending.
    if not has_primary and not has_claim_rows:
        render_status = "hidden"
    elif freshness_status == "stale" or not has_primary:
        render_status = "show_with_warning"
    else:
        render_status = "renderable"

    return {
        "extraction_status": extraction_status,
        "enrichment_status": "deferred",   # Stage 1: no LLM enrichment.
        "freshness_status": freshness_status,
        "review_status": "unreviewed",     # Verifier upgrades to machine_verified.
        "render_status": render_status,
        # release_eligible is gated by the rendered verifier + release gate
        # (Phase 4), neither of which is in Stage 1. Always 0 here.
        "release_eligible": 0,
    }


# ---------------------------------------------------------------------------
# Per-paper builder
# ---------------------------------------------------------------------------

def build_record_for_paper(
    paper_id: str,
    article_rec: dict,
    build_run_id: str,
) -> dict:
    """Return a dict with:
        record: dict suitable for DB INSERT and public payload
        components: list[dict]
        support_sets: dict[support_set_id -> {hash, members}]
        repair_items: list[dict] for completion_queue
    """
    record_id = make_record_id(paper_id)
    support_sets: dict[str, dict] = {}

    def register_support_set(members: list[dict]) -> tuple[str, str]:
        ss_id = make_support_set_id(members)
        if ss_id not in support_sets:
            support_set_hash = sha256_canonical(
                sorted(members, key=lambda m: (m["source_artifact_id"], m["source_field_path"]))
            )
            support_sets[ss_id] = {
                "support_set_id": ss_id,
                "support_set_hash": support_set_hash,
                "members": members,
            }
        return ss_id, support_sets[ss_id]["support_set_hash"]

    repair_items: list[dict] = []

    # Component support sets.
    ss_primary = register_support_set(support_set_for_primary_claim(paper_id, article_rec))
    ss_rows = register_support_set(support_set_for_claim_rows(paper_id, article_rec))
    ss_ev = register_support_set(support_set_for_evidence_strength(paper_id, article_rec))
    ss_def = register_support_set(support_set_for_defeaters(paper_id, article_rec))
    ss_bn = register_support_set(support_set_for_belief_network_context(paper_id, article_rec))
    ss_ans = register_support_set(support_set_for_answer_shape_status(paper_id, article_rec))
    ss_prov = register_support_set(support_set_for_provenance_summary(paper_id, article_rec))

    # Primary claim
    chosen, rule_name = select_primary_claim(article_rec)
    primary_component, primary_repair = build_primary_claim_component(
        paper_id, record_id, article_rec, chosen, rule_name, ss_primary[0], ss_primary[1]
    )
    if primary_repair:
        repair_items.append(primary_repair)

    # Claim rows
    claim_rows_component = build_claim_rows_component(
        paper_id, record_id, article_rec, ss_rows[0], ss_rows[1]
    )

    # Evidence strength (tied to primary claim)
    evidence_component = build_evidence_strength_component(
        paper_id, record_id, article_rec, chosen, ss_ev[0], ss_ev[1]
    )

    # Defeaters
    defeater_component, defeater_repair = build_defeaters_component(
        paper_id, record_id, article_rec, ss_def[0], ss_def[1]
    )
    if defeater_repair:
        repair_items.append(defeater_repair)

    # Belief-network context
    bn_component, bn_repair = build_belief_network_context_component(
        paper_id, record_id, article_rec, ss_bn[0], ss_bn[1]
    )
    if bn_repair:
        repair_items.append(bn_repair)

    # Answer shape
    answer_component = build_answer_shape_status_component(
        paper_id, record_id, article_rec, chosen, ss_ans[0], ss_ans[1]
    )

    # Provenance summary (must come last; depends on other components)
    interim_components = [
        primary_component,
        claim_rows_component,
        evidence_component,
        defeater_component,
        bn_component,
        answer_component,
    ]
    provenance_component = build_provenance_summary_component(
        paper_id, record_id, article_rec, interim_components, ss_prov[0], ss_prov[1]
    )
    components = interim_components + [provenance_component]

    # Record-level statuses
    statuses = derive_record_statuses(components)

    # input_fingerprint covers all support-set hashes PLUS the generating
    # activity's identity (builder_version, schema_version). Without the
    # version terms, bumping the builder with identical inputs yields an
    # identical fingerprint — a silent regression (Gil, panel finding;
    # supersedes the inputs-only spec §6 text, which is amended).
    input_fingerprint = "sha256:" + sha256_hex(canonical_dumps({
        "support_set_hashes": sorted(ss["support_set_hash"] for ss in support_sets.values()),
        "builder_version": BUILDER_VERSION,
        "schema_version": SCHEMA_VERSION,
    }))

    primary_claim_id = primary_component["content_json"].get("claim_id") if chosen else None

    # payload_hash covers IMMUTABLE CONTENT ONLY: identity + component content.
    # Mutable lifecycle/status state (extraction/enrichment/freshness/review/
    # render status, release_eligible) is deliberately EXCLUDED so that:
    #   (1) the published payload is recomputable from its own bytes — no
    #       bool-vs-int (false vs 0) divergence (Wright/Brooker finding);
    #   (2) Stage-4 promotion (flipping release_eligible) and verifier review
    #       (flipping review_status to machine_verified) and PNU repair
    #       (stale -> fresh) change lifecycle state WITHOUT rewriting content
    #       hashes or invalidating downstream caches (Wright's evolution trap).
    # Lifecycle state still travels in the public payload's envelope; it is
    # simply not part of the content identity. This supersedes spec §6/§7,
    # which are amended accordingly.
    content_for_hash = {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "paper_id": paper_id,
        "primary_claim_id": primary_claim_id,
        "components": {c["component_type"]: c["content_json"] for c in components},
    }
    payload_hash = "sha256:" + sha256_canonical(content_for_hash)

    blocking_failures = [r for r in repair_items if r["severity"] == "blocking"]

    record = {
        "record_id": record_id,
        "paper_id": paper_id,
        "schema_version": SCHEMA_VERSION,
        "active": 1,
        **statuses,
        "primary_claim_id": primary_claim_id,
        "build_run_id": build_run_id,
        "input_fingerprint": input_fingerprint,
        "payload_hash": payload_hash,
        "blocking_failures_json": json.dumps(
            [{"reason": r["reason"], "component_type": r["component_type"]} for r in blocking_failures]
        ),
    }

    # Derived display projections (no new component_type, no DB write):
    # Toulmin view assembled from components; related-work from source links.
    projections = {
        "toulmin": build_toulmin_view(components),
        "related_work": build_related_work(article_rec),
    }

    return {
        "record": record,
        "components": components,
        "support_sets": support_sets,
        "repair_items": repair_items,
        "projections": projections,
    }


# ---------------------------------------------------------------------------
# DB writes
# ---------------------------------------------------------------------------

def write_build_run_row(conn: sqlite3.Connection, build_run_id: str, started_at: str) -> None:
    conn.execute(
        """
        INSERT INTO article_epistemic_build_runs(
            build_run_id, builder_version, started_at, status
        ) VALUES (?, ?, ?, 'running')
        """,
        (build_run_id, BUILDER_VERSION, started_at),
    )


def finalize_build_run_row(
    conn: sqlite3.Connection,
    build_run_id: str,
    *,
    finished_at: str,
    input_snapshot_hash: str,
    record_count: int,
    success_count: int,
    failure_count: int,
    repair_count: int,
    status: str,
    report: dict,
) -> None:
    conn.execute(
        """
        UPDATE article_epistemic_build_runs
           SET finished_at = ?,
               input_snapshot_hash = ?,
               record_count = ?,
               success_count = ?,
               failure_count = ?,
               repair_count = ?,
               status = ?,
               report_json = ?
         WHERE build_run_id = ?
        """,
        (
            finished_at,
            input_snapshot_hash,
            record_count,
            success_count,
            failure_count,
            repair_count,
            status,
            json.dumps(report),
            build_run_id,
        ),
    )


def persist_record(
    conn: sqlite3.Connection,
    paper_record: dict,
    build_run_id: str,
) -> None:
    rec = paper_record["record"]
    components = paper_record["components"]
    support_sets = paper_record["support_sets"]
    repair_items = paper_record["repair_items"]

    # Upsert support sets first (FK target).
    for ss in support_sets.values():
        conn.execute(
            """
            INSERT OR IGNORE INTO article_epistemic_support_sets(
                support_set_id, support_set_hash, members_json
            ) VALUES (?, ?, ?)
            """,
            (
                ss["support_set_id"],
                ss["support_set_hash"],
                json.dumps(ss["members"], sort_keys=True),
            ),
        )

    # Deactivate any prior active record for this paper/schema before inserting.
    conn.execute(
        """
        UPDATE article_epistemic_records
           SET active = 0,
               updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
         WHERE paper_id = ? AND schema_version = ? AND active = 1
        """,
        (rec["paper_id"], rec["schema_version"]),
    )

    # Insert the new active record.
    conn.execute(
        """
        INSERT INTO article_epistemic_records(
            record_id, build_run_id, paper_id, schema_version, active,
            extraction_status, enrichment_status, freshness_status,
            review_status, render_status, release_eligible,
            primary_claim_id, input_fingerprint, payload_hash,
            blocking_failures_json
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rec["record_id"], build_run_id, rec["paper_id"], rec["schema_version"],
            rec["extraction_status"], rec["enrichment_status"], rec["freshness_status"],
            rec["review_status"], rec["render_status"], rec["release_eligible"],
            rec["primary_claim_id"], rec["input_fingerprint"], rec["payload_hash"],
            rec["blocking_failures_json"],
        ),
    )

    # Insert components.
    for c in components:
        conn.execute(
            """
            INSERT INTO article_epistemic_components(
                component_id, build_run_id, record_id, paper_id, component_type,
                component_status, source_mode, field_policy, review_status,
                freshness_status, render_policy, content_json, content_hash,
                support_set_id, provenance_json, verification_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                c["component_id"], build_run_id, rec["record_id"], rec["paper_id"],
                c["component_type"], c["status"], c["source_mode"],
                c["field_policy"], c["review_status"], c["freshness_status"],
                c["render_policy"],
                json.dumps(c["content_json"], sort_keys=True),
                c["content_hash"],
                c["support_set_id"],
                json.dumps(c["provenance"], sort_keys=True),
                json.dumps(c["verification"], sort_keys=True),
            ),
        )

    # Repair items via upsert.
    for r in repair_items:
        conn.execute(
            """
            INSERT INTO article_epistemic_completion_queue(
                paper_id, component_type, reason, severity, next_action, status,
                attempt_count
            ) VALUES (?, ?, ?, ?, ?, 'open', 1)
            ON CONFLICT(paper_id, component_type, reason)
              WHERE status IN ('open', 'in_progress')
              DO UPDATE SET
                last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                attempt_count = article_epistemic_completion_queue.attempt_count + 1,
                -- Re-detection updates severity in BOTH directions: a warning
                -- that becomes blocking escalates (Mayo), and a blocking item
                -- that is reclassified (e.g. PNU -> enrichment warning) de-escalates.
                severity = excluded.severity,
                next_action = excluded.next_action
            """,
            (r["paper_id"], r["component_type"], r["reason"], r["severity"], r["next_action"]),
        )


# ---------------------------------------------------------------------------
# Public payload writer
# ---------------------------------------------------------------------------

def build_public_payload(records: list[dict], build_run_id: str, started_at: str) -> dict:
    """Build the sibling payload (data/ka_payloads/article_epistemic_layer.json)."""
    layers = {}
    for pr in records:
        rec = pr["record"]
        components = pr["components"]
        ss_lookup = {ss["support_set_id"]: ss["support_set_hash"] for ss in pr["support_sets"].values()}
        counts = derive_counts(components)
        layers[rec["paper_id"]] = {
            "schema_version": SCHEMA_VERSION,
            "record_id": rec["record_id"],
            "paper_id": rec["paper_id"],
            "extraction_status": rec["extraction_status"],
            "enrichment_status": rec["enrichment_status"],
            "freshness_status": rec["freshness_status"],
            "review_status": rec["review_status"],
            "render_status": rec["render_status"],
            "release_eligible": bool(rec["release_eligible"]),
            "primary_claim_id": rec["primary_claim_id"],
            "build": {
                "build_run_id": build_run_id,
                "builder_version": BUILDER_VERSION,
                "input_fingerprint": rec["input_fingerprint"],
                "payload_hash": rec["payload_hash"],
            },
            "counts": counts,
            "components": {
                c["component_type"]: {
                    "component_id": c["component_id"],
                    "component_type": c["component_type"],
                    "status": c["status"],
                    "source_mode": c["source_mode"],
                    "field_policy": c["field_policy"],
                    "review_status": c["review_status"],
                    "freshness_status": c["freshness_status"],
                    "render_policy": c["render_policy"],
                    "display_label": c["display_label"],
                    "availability": derive_component_availability(c),
                    "content_json": c["content_json"],
                    "absence_reason": c["absence_reason"],
                    "support_set_id": c["support_set_id"],
                    "support_set_hash": ss_lookup[c["support_set_id"]],
                    "provenance": c["provenance"],
                    "verification": c["verification"],
                }
                for c in components
            },
            "availability_summary": derive_availability_summary(components),
            "toulmin": pr["projections"]["toulmin"],
            "related_work": pr["projections"]["related_work"],
            "blocking_failures": json.loads(rec["blocking_failures_json"]),
        }
    # Built != releasable. Surface the gap so "shipped" can never be misread as
    # "usable" (Brooker/Mayo panel finding). releasable counts records that are
    # actually promotable; renderable/stale/blocked break down the rest.
    recs = [pr["record"] for pr in records]
    built = len(recs)
    releasable = sum(1 for r in recs if r["release_eligible"] == 1)
    renderable = sum(1 for r in recs if r["render_status"] == "renderable")
    stale = sum(1 for r in recs if r["freshness_status"] == "stale")
    blocked = sum(1 for r in recs if json.loads(r["blocking_failures_json"]))
    return {
        "summary": {
            "schema_version": SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "build_run_id": build_run_id,
            "generated_at": started_at,
            "record_count": built,
            "coverage": {
                "built": built,
                "releasable": releasable,
                "renderable": renderable,
                "stale": stale,
                "blocked": blocked,
            },
        },
        "details": layers,
    }


def derive_component_availability(component: dict) -> str:
    """Tier a component for the renderer: 'available' (show it now) or
    'pending_upstream' (enrichment whose source is not ready — show a typed
    'pending' note, not a blank)."""
    ctype = component["component_type"]
    if ctype in ENRICHMENT_COMPONENT_TYPES and component["status"] in {
        "stale", "source_missing", "withheld_low_confidence", "blocked", "queued"
    }:
        return "pending_upstream"
    return "available"


def derive_availability_summary(components: list[dict]) -> dict:
    """Record-level 'what we show now vs. what's coming' contract (graceful
    degradation). Lets a reader/consumer see, per article, exactly which
    sections are live, which are pending upstream work, and which are planned."""
    available, pending = [], []
    for c in components:
        tier = derive_component_availability(c)
        if tier == "available":
            available.append(c["component_type"])
        else:
            pending.append({
                "component_type": c["component_type"],
                "reason": c.get("absence_reason") or c["status"],
            })
    return {
        "available_now": sorted(available),
        "pending_upstream": pending,
        "planned_enrichment": list(PLANNED_STAGE2_SECTIONS),
    }


def build_toulmin_view(components: list[dict]) -> dict:
    """Assemble a Toulmin projection from existing components — no new data, no
    new component_type. Honest about what each slot is:
      claim/grounds/warrant/qualifier/rebuttal are filled from extracted data;
      warrant is a LABEL (not an explained warrant); backing is Stage-2 planned.
    `is_toulmin_shaped` mirrors the answer_shape routing decision but the box is
    shown for every record so the reader sees the structure and its gaps."""
    by = {c["component_type"]: c for c in components}
    pc = by.get("primary_claim", {}).get("content_json", {}) or {}
    ev = by.get("evidence_strength", {}).get("content_json", {}) or {}
    df = by.get("defeaters", {}).get("content_json", {}) or {}
    asc = by.get("answer_shape_status", {}).get("content_json", {}) or {}
    has_claim = bool(pc.get("claim_id"))
    return {
        "is_toulmin_shaped": asc.get("answer_shape") == "toulmin",
        "answer_shape": asc.get("answer_shape"),
        "slots": {
            "claim": {
                "availability": "available" if has_claim else "pending_upstream",
                "claim_id": pc.get("claim_id"),
                "text": pc.get("canonical_text") or pc.get("source_text"),
            },
            "grounds": {
                "availability": "available",
                "support_count": ev.get("support_count"),
                "attack_count": ev.get("attack_count"),
                "atlas_credence_mean": ev.get("atlas_credence_mean"),
                "study_record": ev.get("study_record"),
            },
            "warrant": {
                "availability": "available" if pc.get("warrant") else "pending_upstream",
                "label": pc.get("warrant"),
                "kind": "label_only",  # not an explained warrant — honest
            },
            "qualifier": {
                "availability": "available" if pc.get("qualifier") else "pending_upstream",
                "value": pc.get("qualifier"),
            },
            "rebuttal": {
                "availability": "available",
                "state": df.get("defeater_existence") or df.get("no_defeater_basis"),
                "rows": df.get("rows", []),
            },
            "backing": {
                "availability": "planned_enrichment",
                "note": "Support for the warrant is not extracted in Stage 1 "
                        "(Stage-2 LLM, gated by span attribution + human review).",
            },
        },
    }


def build_related_work(rec: dict) -> dict:
    """Project related-paper links (PNU-independent) for display. These are
    source-derived (article_details.related_papers) and weaker than support/
    contradict (no stance) — flagged as such. Not covered by payload_hash."""
    related = [r for r in (rec.get("related_papers") or []) if isinstance(r, dict)]
    items = [{
        "paper_id": r.get("paper_id"),
        "title": r.get("title"),
        "score": r.get("score"),
        "reason": r.get("reason"),
    } for r in related]
    return {
        "availability": "available" if items else "absent",
        "relation": "related_not_stance_bearing",
        "count": len(items),
        "items": items,
        "provenance_note": "source-derived projection (details.related_papers); "
                           "not a stance-bearing support/attack link",
    }


def derive_counts(components: list[dict]) -> dict:
    claim_rows_c = next((c for c in components if c["component_type"] == "claim_rows"), None)
    claim_count = (claim_rows_c or {}).get("content_json", {}).get("count", 0)
    ev = next((c for c in components if c["component_type"] == "evidence_strength"), None)
    support_count = (ev or {}).get("content_json", {}).get("support_count")
    attack_count = (ev or {}).get("content_json", {}).get("attack_count")
    defeaters_c = next((c for c in components if c["component_type"] == "defeaters"), None)
    defeater_rows = (defeaters_c or {}).get("content_json", {}).get("rows", [])
    return {
        "claim_count": claim_count,
        "support_count": support_count if support_count is not None else 0,
        "attack_count": attack_count if attack_count is not None else 0,
        "defeater_count": len(defeater_rows),
    }


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path
    # Skip empty (0-byte) files. A committed 0-byte decoy at
    # data/ka_payloads/pipeline_lifecycle_full.db otherwise wins auto-detection
    # over the real DB and silently routes writes/reads to an un-initialized
    # database (the cause of the crashing-runbook finding in the panel review).
    # Mirrors overseer/db.py resolve_db_path, which already does this.
    for candidate in DEFAULT_DB_CANDIDATES:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return DEFAULT_DB_CANDIDATES[-1]


# Lifecycle tables the builder/verifier require. Used to fail fast with a clear
# message instead of an unhandled "no such table" deep in a query.
REQUIRED_LIFECYCLE_TABLE = "article_epistemic_records"


def assert_schema_present(conn: sqlite3.Connection, db_path: Path) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (REQUIRED_LIFECYCLE_TABLE,),
    ).fetchone()
    if row is None:
        raise SystemExit(
            f"ERROR: lifecycle DB at {db_path} has no '{REQUIRED_LIFECYCLE_TABLE}' "
            f"table.\n  The DB is present but un-initialized. Run "
            f"`python3 scripts/article_epistemic_layer_init.py --db {db_path}` "
            f"first,\n  or pass --db 160sp/pipeline_lifecycle_full.db to target "
            f"the real lifecycle database."
        )


def load_article_details(input_path: Path) -> tuple[dict[str, dict], str]:
    raw = json.loads(input_path.read_text())
    details = raw.get("details") if isinstance(raw, dict) else None
    if not isinstance(details, dict):
        raise ValueError(
            f"{input_path} does not have a 'details' object keyed by paper_id"
        )
    snapshot_hash = "sha256:" + sha256_hex(input_path.read_bytes())
    return details, snapshot_hash


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT),
                        help=f"Article-details payload (default: {DEFAULT_INPUT})")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help=f"Sibling epistemic-layer payload to write "
                             f"(default: {DEFAULT_OUTPUT})")
    parser.add_argument("--db", default=None,
                        help="Lifecycle DB path (default: auto-detect)")
    parser.add_argument("--paper-ids", nargs="*",
                        help="Limit build to specific paper_ids (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build records in memory but do not write to DB or output JSON")
    parser.add_argument("--max-records", type=int, default=None,
                        help="Stop after N records (debug aid)")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.is_absolute():
        input_path = REPO_ROOT / input_path
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path
    db_path = resolve_db_path(args.db)

    details, snapshot_hash = load_article_details(input_path)
    paper_ids = sorted(details.keys()) if not args.paper_ids else sorted(args.paper_ids)
    if args.max_records is not None:
        paper_ids = paper_ids[: args.max_records]

    started_at = utc_now()
    # Open the DB up-front (unless dry-run) so build_run_id can query the
    # existing sequence. For dry runs we keep conn=None and fall back to a
    # microsecond-derived sequence.
    conn: sqlite3.Connection | None = None
    if not args.dry_run:
        conn = sqlite3.connect(db_path)
        # Autocommit mode so the explicit BEGIN IMMEDIATE below controls the
        # transaction boundary (acquires the write lock up front, serializing
        # concurrent builders across the deactivate-then-insert active swap).
        conn.isolation_level = None
        conn.execute("PRAGMA foreign_keys = ON;")
        assert_schema_present(conn, db_path)
    build_run_id = make_build_run_id(started_at, conn)

    # In-memory build first; only touch DB after every paper successfully builds.
    paper_records: list[dict] = []
    failure_count = 0
    repair_count = 0
    for pid in paper_ids:
        article_rec = details.get(pid)
        if article_rec is None:
            failure_count += 1
            continue
        try:
            paper_record = build_record_for_paper(pid, article_rec, build_run_id)
        except Exception as exc:  # noqa: BLE001
            failure_count += 1
            print(f"[FAIL] {pid}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        paper_records.append(paper_record)
        repair_count += len(paper_record["repair_items"])

    success_count = len(paper_records)

    print(f"Built {success_count} records, {failure_count} failures, "
          f"{repair_count} repair items.")

    if args.dry_run:
        # Still useful to surface a small summary in dry mode.
        sample_paper = paper_records[0] if paper_records else None
        if sample_paper:
            print("Sample record:", json.dumps(sample_paper["record"], indent=2)[:600])
        return 0

    # DB writes (conn was opened above). One serialized transaction: BEGIN
    # IMMEDIATE takes the write lock before the first active-swap, so a
    # concurrent builder blocks rather than racing the deactivate/insert.
    assert conn is not None  # mypy/reader: dry-run path returned earlier.
    try:
        conn.execute("BEGIN IMMEDIATE")
        write_build_run_row(conn, build_run_id, started_at)
        for pr in paper_records:
            persist_record(conn, pr, build_run_id)
        finalize_build_run_row(
            conn,
            build_run_id,
            finished_at=utc_now(),
            input_snapshot_hash=snapshot_hash,
            record_count=success_count,
            success_count=success_count,
            failure_count=failure_count,
            repair_count=repair_count,
            status="completed",
            report={
                "input_path": str(input_path),
                "paper_ids_count": len(paper_ids),
            },
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Public payload sibling.
    payload = build_public_payload(paper_records, build_run_id, started_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {output_path}")
    print(f"Lifecycle DB updated: {db_path}")
    print(f"build_run_id = {build_run_id}")
    cov = payload["summary"]["coverage"]
    print(f"Coverage: built={cov['built']} releasable={cov['releasable']} "
          f"renderable={cov['renderable']} stale={cov['stale']} "
          f"blocked={cov['blocked']}  "
          f"(built != releasable: {cov['built'] - cov['releasable']} not yet promotable)")
    return 0 if failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
