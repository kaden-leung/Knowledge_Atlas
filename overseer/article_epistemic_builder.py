"""Stage 1 deterministic builder for article_epistemic_record artefacts.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §8
    docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md §8 (companion)
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P16, P17, P18, P19, P27)

The Stage 1 builder is purely deterministic: no LLM calls, no semantic
inference. It takes pre-fetched paper inputs and:

  1. Selects the primary claim via the rule cascade (companion §8) and
     records the rule that fired in claims.claim_origin (P18).
  2. Builds claim_rows from top_claims.
  3. Computes a coarse evidence_strength per claim from support/attack counts.
  4. Preserves defeaters with required target_kind (P16); flags
     attack_count_without_mapped_rows when applicable.
  5. Builds belief_network_links pinned to pnu_version_hash (P19).
  6. Assigns answer_shape via the deterministic rule cascade; records the
     rule trace (P18, OR's verifier check).
  7. Captures the support set as artefact-typed members.
  8. Computes raw_hash and semantic_hash on the assembled record content
     (P27).
  9. Atomically writes: claims, defeaters, belief_network_links,
     answer_shape_decisions, support_sets, content_hashes, artefact_registry
     (with fencing_token-validated update_with_hashes, raising
     FencingTokenMismatch on stale token per P24).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from overseer.artefact_registry import (
    Artefact,
    FencingTokenMismatch,
    register,
    update_with_hashes,
)
from overseer.content_hashes import (
    compute_input_fingerprint,
    compute_raw_hash,
    compute_semantic_hash,
)
from overseer.db import transaction
from overseer.ids import utc_now_iso
from overseer.support_sets import capture as capture_support_set

BUILDER_NAME = "article_epistemic_builder"
BUILDER_VERSION = "v1"
SCHEMA_VERSION = "article_epistemic_layer.v1"
ARTEFACT_KIND = "article_epistemic_record"
CANONICALIZER_VERSION = "v1"


# ----------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------

@dataclass
class PaperInputs:
    """Pre-fetched inputs for the builder.

    The caller is responsible for assembling this from upstream sources
    (article detail JSON, top_claims rows, abstract, PNU rows, etc.). For
    Phase 1 the dataclass is intentionally permissive: missing fields are
    handled by the builder via absence_reasons.

    `support_members` is the list of (artefact_id, hash_at_capture) pairs the
    support set is built from. The caller must register each upstream input as
    an overseer artefact and provide its current hash here.
    """

    paper_id: str
    support_members: list[tuple[str, str]]
    structured_core_finding: str | None = None
    top_claims: list[dict] = field(default_factory=list)
    article_main_conclusion: str | None = None
    science_summary: dict | None = None
    argumentation: dict | None = None
    evidence_profile: dict | None = None
    pnu_links: list[dict] = field(default_factory=list)
    abstract: dict | None = None


@dataclass
class BuildResult:
    paper_id: str
    artefact_id: str
    build_run_id: str
    raw_hash: str
    semantic_hash: str
    support_set_id: str
    primary_claim_id: str | None
    primary_claim_origin: str
    claim_count: int
    defeater_count: int
    belief_link_count: int
    answer_shape: str


# ----------------------------------------------------------------------------
# Rule cascades
# ----------------------------------------------------------------------------

def _claim_id_for(paper_id: str, canonical_text: str) -> str:
    """Deterministic claim_id per synthesis P17."""
    import hashlib
    h = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()[:16]
    return f"claim:{paper_id}:{h}"


def _canonicalize_claim_text(text: str) -> str:
    """Apply canonicalizer v1: trim + collapse internal whitespace."""
    import re
    return re.sub(r"\s+", " ", text.strip())


def select_primary_claim(inputs: PaperInputs) -> tuple[str | None, str]:
    """Run the rule cascade. Returns (canonical_text, claim_origin).

    Rule order per companion §8:
      1. structured_core_finding
      2. top_claims sorted by (-support_count, attack_count, -credence,
         source_order, canonical_claim_text)
      3. article_main_conclusion
      4. science_summary.core_finding
      5. None -> 'not_extracted'
    """
    if inputs.structured_core_finding:
        return _canonicalize_claim_text(inputs.structured_core_finding), "structured_core_finding"
    if inputs.top_claims:
        sorted_claims = sorted(
            inputs.top_claims,
            key=lambda c: (
                -int(c.get("support_count", 0)),
                int(c.get("attack_count", 0)),
                -float(c.get("credence", 0.0)),
                int(c.get("source_order", 0)),
                str(c.get("canonical_claim_text", "")),
            ),
        )
        first = sorted_claims[0]
        text = first.get("canonical_claim_text") or first.get("text")
        if text:
            return _canonicalize_claim_text(text), "top_claims_row"
    if inputs.article_main_conclusion:
        return _canonicalize_claim_text(inputs.article_main_conclusion), "article_level_main_conclusion"
    if inputs.science_summary and inputs.science_summary.get("core_finding"):
        return _canonicalize_claim_text(inputs.science_summary["core_finding"]), "science_summary_core_finding"
    return None, "not_extracted"


def assign_answer_shape(inputs: PaperInputs) -> tuple[str, str, dict]:
    """Returns (shape, rule_id, rule_trace).

    Rule order (deterministic):
      R1. inputs.argumentation.shape_hint if explicitly set -> use it
      R2. evidence_profile presence: 'comparison' if it has 'comparison' key,
          'mechanism' if it has 'mechanism' key, 'review_synthesis' if
          'review_type' == 'meta_analysis'.
      R3. top_claims with both 'warrant' and 'data' fields -> 'toulmin'
      R4. top_claims with IV/DV structure -> 'field_map'
      R5. fallback -> 'unknown' with rule trace showing all checks ran.
    """
    trace: dict = {"rules_checked": []}
    arg = inputs.argumentation or {}
    if arg.get("shape_hint") in {"toulmin", "field_map", "comparison",
                                  "mechanism", "review_synthesis", "mixed"}:
        trace["rules_checked"].append({"rule": "R1_explicit_hint", "fired": True})
        return arg["shape_hint"], "R1_explicit_hint", trace
    trace["rules_checked"].append({"rule": "R1_explicit_hint", "fired": False})

    ep = inputs.evidence_profile or {}
    if "comparison" in ep:
        trace["rules_checked"].append({"rule": "R2_comparison", "fired": True})
        return "comparison", "R2_comparison", trace
    trace["rules_checked"].append({"rule": "R2_comparison", "fired": False})

    if "mechanism" in ep:
        trace["rules_checked"].append({"rule": "R2_mechanism", "fired": True})
        return "mechanism", "R2_mechanism", trace
    trace["rules_checked"].append({"rule": "R2_mechanism", "fired": False})

    if ep.get("review_type") == "meta_analysis":
        trace["rules_checked"].append({"rule": "R2_review_synthesis", "fired": True})
        return "review_synthesis", "R2_review_synthesis", trace
    trace["rules_checked"].append({"rule": "R2_review_synthesis", "fired": False})

    if inputs.top_claims and any(
        ("warrant" in c and "data" in c) for c in inputs.top_claims
    ):
        trace["rules_checked"].append({"rule": "R3_toulmin", "fired": True})
        return "toulmin", "R3_toulmin", trace
    trace["rules_checked"].append({"rule": "R3_toulmin", "fired": False})

    if inputs.top_claims and any(
        ("iv" in c or "dv" in c) for c in inputs.top_claims
    ):
        trace["rules_checked"].append({"rule": "R4_field_map", "fired": True})
        return "field_map", "R4_field_map", trace
    trace["rules_checked"].append({"rule": "R4_field_map", "fired": False})

    trace["rules_checked"].append({"rule": "R5_fallback", "fired": True})
    return "unknown", "R5_fallback", trace


def _classify_defeaters(arg: dict | None) -> list[dict]:
    """Extract defeater rows from argumentation. Each defeater MUST have a
    target_kind in the controlled vocabulary (P16).

    argumentation may contain:
      * defeaters: list of {target_kind, content, ...}
      * attack_count: int (used to detect attack_count_without_mapped_rows)
    """
    if not arg:
        return []
    defeaters = arg.get("defeaters") or []
    out = []
    for d in defeaters:
        target_kind = d.get("target_kind")
        if target_kind not in {
            "claim", "warrant", "method", "measurement", "interpretation",
            "generalizability", "mechanism", "application",
        }:
            # Reject — Phase 1 refuses to write defeaters without target_kind.
            continue
        out.append(d)
    return out


# ----------------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------------

def build_one(
    conn: sqlite3.Connection,
    *,
    paper_id: str,
    inputs: PaperInputs,
    build_run_id: str,
    fencing_token: int,
) -> BuildResult:
    """Build the article_epistemic_record for one paper. Atomic, all-or-nothing.

    Caller responsibilities:
      * Ensure the artefact is registered in artefact_registry (call
        builder_register_artefact below first, or pre-register).
      * Ensure fencing_token matches artefact_registry.current_fencing_token
        for this paper's article_epistemic_record (claim path does this).
      * Provide a valid PaperInputs.support_members list of registered
        upstream artefact_ids.

    Raises:
      FencingTokenMismatch if the write is rejected by P24 enforcement.
    """
    # 1. Run rule cascades to produce the assembled record content.
    primary_text, primary_origin = select_primary_claim(inputs)
    shape, shape_rule_id, shape_trace = assign_answer_shape(inputs)
    defeaters = _classify_defeaters(inputs.argumentation)
    attack_count = int((inputs.argumentation or {}).get("attack_count", 0))

    primary_claim_id = (
        _claim_id_for(paper_id, primary_text) if primary_text else None
    )

    # 2. Build claim_rows (deterministic snapshot of top_claims with stable ids).
    claim_rows = []
    for c in (inputs.top_claims or []):
        text = c.get("canonical_claim_text") or c.get("text")
        if not text:
            continue
        cid = _claim_id_for(paper_id, _canonicalize_claim_text(text))
        claim_rows.append({
            "claim_id": cid,
            "canonical_claim_text": _canonicalize_claim_text(text),
            "support_count": c.get("support_count"),
            "attack_count": c.get("attack_count"),
            "credence": c.get("credence"),
        })

    # 3. Defeater absence-reason logic (P16, companion §8).
    if not defeaters and attack_count > 0:
        defeater_absence_reason = "attack_count_without_mapped_rows"
    elif not defeaters and primary_text:
        defeater_absence_reason = "no_defeater_extracted"
    else:
        defeater_absence_reason = None

    # 4. Belief-network links (P19): each link captures the PNU version hash.
    bn_links = []
    if inputs.pnu_links:
        for link in inputs.pnu_links:
            if not link.get("pnu_id") or not link.get("pnu_version_hash"):
                continue
            bn_links.append({
                "pnu_id": link["pnu_id"],
                "pnu_version_hash": link["pnu_version_hash"],
                "edge_kind": link.get("edge_kind", "supports"),
                "claim_id": link.get(
                    "claim_id",
                    primary_claim_id or _claim_id_for(paper_id, ""),
                ),
            })

    # 5. Compose the public record content (the bytes we hash).
    record_content = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "primary_claim": {
            "claim_id": primary_claim_id,
            "canonical_claim_text": primary_text,
            "claim_origin": primary_origin,
        } if primary_text else {
            "claim_id": None,
            "canonical_claim_text": None,
            "claim_origin": primary_origin,
            "absence_reason": "not_yet_extracted",
        },
        "claim_rows": claim_rows,
        "evidence_strength": {
            "claim_id": primary_claim_id,
            "support_count": (claim_rows[0]["support_count"] if claim_rows else None),
            "attack_count": (claim_rows[0]["attack_count"] if claim_rows else None),
            "credence": (claim_rows[0]["credence"] if claim_rows else None),
            "confidence_basis": "deterministic_from_source_counts",
        } if claim_rows else {
            "absence_reason": "not_yet_extracted",
        },
        "defeaters": {
            "rows": defeaters,
            "attack_count": attack_count,
            "absence_reason": defeater_absence_reason,
        },
        "belief_network_context": {
            "links": bn_links,
            "absence_reason": None if bn_links else "no_pnu_support_available",
        },
        "answer_shape_status": {
            "shape": shape,
            "rule_id": shape_rule_id,
        },
    }

    # 6. Compute hashes.
    raw = compute_raw_hash(record_content)
    semantic = compute_semantic_hash(
        record_content,
        component_type="primary_claim",
        hints_override={
            "canonical_claim_text": {"whitespace_collapsible": True},
            "rows": {"order_insensitive": True},
            "links": {"order_insensitive": True},
        },
    )
    input_fp = compute_input_fingerprint(inputs.support_members)

    # 7. Resolve the artefact_id (caller pre-registered, or we register now).
    art = register(
        conn,
        kind=ARTEFACT_KIND,
        entity_type="paper",
        entity_id=paper_id,
        field_path=None,
        schema_version=SCHEMA_VERSION,
    )

    # 8. Atomic write: support_set, content_hashes, child rows, then
    #    update_with_hashes (fencing-token-validated).
    with transaction(conn):
        ssid = capture_support_set(conn, inputs.support_members)
        conn.execute(
            """
            INSERT INTO content_hashes (
                artefact_id, build_run_id, raw_hash, semantic_hash,
                normalization_rule_version, input_fingerprint, hashed_at
            ) VALUES (?, ?, ?, ?, 'v1', ?, ?)
            ON CONFLICT(artefact_id, build_run_id) DO UPDATE SET
                raw_hash = excluded.raw_hash,
                semantic_hash = excluded.semantic_hash,
                normalization_rule_version = excluded.normalization_rule_version,
                input_fingerprint = excluded.input_fingerprint,
                hashed_at = excluded.hashed_at
            """,
            (art.artefact_id, build_run_id, raw, semantic, input_fp, utc_now_iso()),
        )
        record_id = f"article_epistemic_layer.v1:{paper_id}"
        # claims
        if primary_text:
            conn.execute(
                """
                INSERT INTO claims (
                    claim_id, paper_id, canonical_claim_text,
                    canonicalizer_version, original_text, claim_scope,
                    claim_type, claim_polarity, assertion_status,
                    epistemic_status, claim_origin, superseded_by, created_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, ?, NULL, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    canonical_claim_text = excluded.canonical_claim_text,
                    canonicalizer_version = excluded.canonicalizer_version,
                    claim_origin = excluded.claim_origin
                """,
                (primary_claim_id, paper_id, primary_text, CANONICALIZER_VERSION,
                 primary_origin, utc_now_iso()),
            )
        for row in claim_rows:
            conn.execute(
                """
                INSERT INTO claims (
                    claim_id, paper_id, canonical_claim_text,
                    canonicalizer_version, claim_origin, created_at
                ) VALUES (?, ?, ?, ?, 'top_claims_row', ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    canonical_claim_text = excluded.canonical_claim_text
                """,
                (row["claim_id"], paper_id, row["canonical_claim_text"],
                 CANONICALIZER_VERSION, utc_now_iso()),
            )
        # defeaters
        for d in defeaters:
            import hashlib
            dh = hashlib.sha256(
                (paper_id + json.dumps(d, sort_keys=True)).encode()
            ).hexdigest()[:16]
            did = f"def:{paper_id}:{dh}"
            conn.execute(
                """
                INSERT INTO defeaters (
                    defeater_id, claim_id, target_kind, content_json,
                    support_set_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(defeater_id) DO UPDATE SET
                    target_kind = excluded.target_kind,
                    content_json = excluded.content_json
                """,
                (did, primary_claim_id, d["target_kind"],
                 json.dumps(d, sort_keys=True), ssid, utc_now_iso()),
            )
        # belief_network_links
        for link in bn_links:
            conn.execute(
                """
                INSERT INTO belief_network_links (
                    record_id, claim_id, pnu_id, pnu_version_hash,
                    edge_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id, claim_id, pnu_id, edge_kind) DO UPDATE SET
                    pnu_version_hash = excluded.pnu_version_hash
                """,
                (record_id, link["claim_id"], link["pnu_id"],
                 link["pnu_version_hash"], link["edge_kind"], utc_now_iso()),
            )
        # answer_shape_decisions
        conn.execute(
            """
            INSERT INTO answer_shape_decisions (
                record_id, shape, rule_id, rule_version, rule_trace_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id, created_at) DO NOTHING
            """,
            (record_id, shape, shape_rule_id, BUILDER_VERSION,
             json.dumps(shape_trace, sort_keys=True), utc_now_iso()),
        )
        # Finally: fencing-token-validated update of artefact_registry.
        update_with_hashes(
            conn,
            artefact_id=art.artefact_id,
            raw_hash=raw,
            semantic_hash=semantic,
            build_run_id=build_run_id,
            fencing_token=fencing_token,
            freshness_status="fresh",
        )

    return BuildResult(
        paper_id=paper_id,
        artefact_id=art.artefact_id,
        build_run_id=build_run_id,
        raw_hash=raw,
        semantic_hash=semantic,
        support_set_id=ssid,
        primary_claim_id=primary_claim_id,
        primary_claim_origin=primary_origin,
        claim_count=len(claim_rows) + (1 if primary_text and primary_claim_id not in {r["claim_id"] for r in claim_rows} else 0),
        defeater_count=len(defeaters),
        belief_link_count=len(bn_links),
        answer_shape=shape,
    )
