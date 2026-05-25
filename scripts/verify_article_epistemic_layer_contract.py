#!/usr/bin/env python3
"""Strict verifier for the article-detail epistemic layer (Stage 1).

Runs the fifteen checks listed in spec §11. Each failure is recorded as an
`article_epistemic_verification_events` row and, when repair is appropriate,
also written to `article_epistemic_completion_queue` (spec §12).

Authority:
    docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md   §11, §12

Usage:
    python3 scripts/verify_article_epistemic_layer_contract.py --strict
    python3 scripts/verify_article_epistemic_layer_contract.py --strict --db PATH --payload PATH
    python3 scripts/verify_article_epistemic_layer_contract.py --strict --no-write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAYLOAD = REPO_ROOT / "data" / "ka_payloads" / "article_epistemic_layer.json"
DEFAULT_DB_CANDIDATES = (
    REPO_ROOT / "data" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "data" / "ka_payloads" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "160sp" / "pipeline_lifecycle_full.db",
)
BUILDER_SCRIPT = REPO_ROOT / "scripts" / "build_article_epistemic_layer.py"

SCHEMA_VERSION = "article_epistemic_layer.v1"
VERIFIER_NAME = "article_epistemic_layer_strict_verifier"
VERIFIER_VERSION = "v1"

# Mirrors of the SQL CHECK vocabularies (spec §4). Keep in sync with
# contracts/schemas/article_epistemic_layer.sql.
VOCAB_EXTRACTION = {"absent", "minimal", "partial", "complete", "failed"}
VOCAB_ENRICHMENT = {"none", "deferred", "draft", "machine_checked",
                    "human_approved", "rejected"}
VOCAB_FRESHNESS = {"fresh", "stale", "unknown"}
VOCAB_REVIEW = {"not_required", "unreviewed", "machine_verified",
                "human_review_required", "human_approved", "human_rejected"}
VOCAB_RENDER_STATUS = {"renderable", "show_with_warning", "hidden", "block_article"}
VOCAB_COMPONENT_STATUS = {"present", "not_extracted", "not_applicable",
                          "source_missing", "extraction_failed", "stale",
                          "blocked", "queued", "withheld_low_confidence"}
VOCAB_SOURCE_MODE = {"extracted", "deterministic_derived", "llm_generated",
                     "human_entered", "missing"}
VOCAB_FIELD_POLICY = {"extracted_only", "deterministic_only", "llm_enrichable",
                      "human_only"}
VOCAB_RENDER_POLICY = {"render", "render_with_warning", "hide", "block"}

# Defeater row contract (spec §8; Pollock). Mirror of
# build_article_epistemic_layer.py DEFEATER_TARGET_KINDS / DEFEATER_DEFEAT_KINDS
# and overseer/article_epistemic_builder.py:_classify_defeaters — keep in sync.
VOCAB_DEFEATER_TARGET_KIND = {"claim", "warrant", "method", "measurement",
                              "interpretation", "generalizability",
                              "mechanism", "application"}
VOCAB_DEFEATER_DEFEAT_KIND = {"rebutting", "undercutting"}

REQUIRED_COMPONENT_TYPES = {
    "primary_claim", "claim_rows", "evidence_strength", "defeaters",
    "belief_network_context", "answer_shape_status", "provenance_summary",
}

REQUIRED_PUBLIC_FIELDS = {
    "schema_version", "record_id", "paper_id",
    "extraction_status", "enrichment_status", "freshness_status",
    "review_status", "render_status", "release_eligible",
    "build", "counts", "components", "blocking_failures",
}

# Spec §10 + §13 — "required dependency classes". For Stage 1, the components
# whose staleness must block release are:
RELEASE_BLOCKING_COMPONENTS = {
    "primary_claim", "claim_rows", "evidence_strength",
    "belief_network_context",
}

# Spec §9 — forbidden provider imports/SDK calls in Stage 1 pipeline code.
FORBIDDEN_PROVIDER_PATTERNS = (
    re.compile(r"\bimport\s+openai\b"),
    re.compile(r"\bfrom\s+openai\s+import\b"),
    re.compile(r"\bimport\s+anthropic\b"),
    re.compile(r"\bfrom\s+anthropic\s+import\b"),
    re.compile(r"\bimport\s+google\.generativeai\b"),
    re.compile(r"\bimport\s+cohere\b"),
)


# ---------------------------------------------------------------------------
# Canonical JSON + hashing (must match the builder)
# ---------------------------------------------------------------------------

def canonical_dumps(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_canonical(obj: Any) -> str:
    return sha256_hex(canonical_dumps(obj))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Failure / RepairAction value objects
# ---------------------------------------------------------------------------

class Failure:
    __slots__ = ("paper_id", "record_id", "check", "message", "severity",
                 "repair_action")

    def __init__(self, *, paper_id: str | None, record_id: str | None,
                 check: str, message: str, severity: str = "fail",
                 repair_action: dict | None = None):
        self.paper_id = paper_id
        self.record_id = record_id
        self.check = check
        self.message = message
        self.severity = severity
        self.repair_action = repair_action

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "record_id": self.record_id,
            "check": self.check,
            "message": self.message,
            "severity": self.severity,
        }


# ---------------------------------------------------------------------------
# DB loaders
# ---------------------------------------------------------------------------

def resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = REPO_ROOT / p
        return p
    # Skip 0-byte files: a committed empty decoy otherwise wins auto-detection
    # over the real DB and makes the documented command crash with a "no such
    # table" deep in a query (panel finding). Mirrors overseer/db.py.
    for candidate in DEFAULT_DB_CANDIDATES:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return DEFAULT_DB_CANDIDATES[-1]


def load_active_records(conn: sqlite3.Connection) -> dict[str, dict]:
    """Return active records keyed by paper_id (one per paper)."""
    rows = conn.execute(
        "SELECT record_id, build_run_id, paper_id, schema_version, active, "
        "       extraction_status, enrichment_status, freshness_status, "
        "       review_status, render_status, release_eligible, "
        "       primary_claim_id, input_fingerprint, payload_hash, "
        "       blocking_failures_json "
        "FROM article_epistemic_records WHERE active = 1"
    ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        rec = {
            "record_id": r[0], "build_run_id": r[1], "paper_id": r[2],
            "schema_version": r[3], "active": r[4],
            "extraction_status": r[5], "enrichment_status": r[6],
            "freshness_status": r[7], "review_status": r[8],
            "render_status": r[9], "release_eligible": r[10],
            "primary_claim_id": r[11], "input_fingerprint": r[12],
            "payload_hash": r[13],
            "blocking_failures": json.loads(r[14] or "[]"),
        }
        out[rec["paper_id"]] = rec
    return out


def load_components_for_record(conn: sqlite3.Connection, record_id: str,
                               build_run_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT component_id, component_type, component_status, source_mode, "
        "       field_policy, review_status, freshness_status, render_policy, "
        "       content_json, content_hash, support_set_id, provenance_json, "
        "       verification_json "
        "FROM article_epistemic_components "
        "WHERE record_id = ? AND build_run_id = ? "
        "ORDER BY component_type",
        (record_id, build_run_id),
    ).fetchall()
    return [{
        "component_id": r[0], "component_type": r[1], "status": r[2],
        "source_mode": r[3], "field_policy": r[4], "review_status": r[5],
        "freshness_status": r[6], "render_policy": r[7],
        "content_json": json.loads(r[8] or "{}"),
        "content_hash": r[9], "support_set_id": r[10],
        "provenance": json.loads(r[11] or "{}"),
        "verification": json.loads(r[12] or "{}"),
    } for r in rows]


def load_support_set(conn: sqlite3.Connection, support_set_id: str) -> dict | None:
    row = conn.execute(
        "SELECT support_set_id, support_set_hash, members_json "
        "FROM article_epistemic_support_sets WHERE support_set_id = ?",
        (support_set_id,),
    ).fetchone()
    if row is None:
        return None
    return {"support_set_id": row[0], "support_set_hash": row[1],
            "members": json.loads(row[2])}


def load_open_queue_for_paper(conn: sqlite3.Connection, paper_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT component_type, reason, severity, status "
        "FROM article_epistemic_completion_queue "
        "WHERE paper_id = ? AND status IN ('open', 'in_progress')",
        (paper_id,),
    ).fetchall()
    return [{"component_type": r[0], "reason": r[1], "severity": r[2],
             "status": r[3]} for r in rows]


# ---------------------------------------------------------------------------
# Individual checks (spec §11). Each returns a list[Failure].
# ---------------------------------------------------------------------------

def check_status_vocabularies(record: dict, components: list[dict]) -> list[Failure]:
    out: list[Failure] = []
    def fail(check: str, msg: str) -> Failure:
        return Failure(paper_id=record["paper_id"], record_id=record["record_id"],
                       check=check, message=msg)
    if record["extraction_status"] not in VOCAB_EXTRACTION:
        out.append(fail("vocab.extraction_status",
                        f"value {record['extraction_status']!r} not in vocab"))
    if record["enrichment_status"] not in VOCAB_ENRICHMENT:
        out.append(fail("vocab.enrichment_status",
                        f"value {record['enrichment_status']!r} not in vocab"))
    if record["freshness_status"] not in VOCAB_FRESHNESS:
        out.append(fail("vocab.freshness_status",
                        f"value {record['freshness_status']!r} not in vocab"))
    if record["review_status"] not in VOCAB_REVIEW:
        out.append(fail("vocab.review_status",
                        f"value {record['review_status']!r} not in vocab"))
    if record["render_status"] not in VOCAB_RENDER_STATUS:
        out.append(fail("vocab.render_status",
                        f"value {record['render_status']!r} not in vocab"))
    for c in components:
        if c["status"] not in VOCAB_COMPONENT_STATUS:
            out.append(fail("vocab.component_status",
                            f"{c['component_type']}: {c['status']!r}"))
        if c["source_mode"] not in VOCAB_SOURCE_MODE:
            out.append(fail("vocab.source_mode",
                            f"{c['component_type']}: {c['source_mode']!r}"))
        if c["field_policy"] not in VOCAB_FIELD_POLICY:
            out.append(fail("vocab.field_policy",
                            f"{c['component_type']}: {c['field_policy']!r}"))
        if c["freshness_status"] not in VOCAB_FRESHNESS:
            out.append(fail("vocab.component_freshness",
                            f"{c['component_type']}: {c['freshness_status']!r}"))
        if c["review_status"] not in VOCAB_REVIEW:
            out.append(fail("vocab.component_review",
                            f"{c['component_type']}: {c['review_status']!r}"))
        if c["render_policy"] not in VOCAB_RENDER_POLICY:
            out.append(fail("vocab.render_policy",
                            f"{c['component_type']}: {c['render_policy']!r}"))
    return out


def check_required_components(record: dict, components: list[dict]) -> list[Failure]:
    present_types = {c["component_type"] for c in components}
    missing = REQUIRED_COMPONENT_TYPES - present_types
    if not missing:
        return []
    return [Failure(
        paper_id=record["paper_id"], record_id=record["record_id"],
        check="components.required_set",
        message=f"missing component types: {sorted(missing)}",
        severity="fail",
        repair_action={
            "component_type": "build",
            "reason": "missing_required_components",
            "severity": "blocking",
            "next_action": (
                f"Re-run builder for {record['paper_id']}; "
                f"missing types: {sorted(missing)}."
            ),
        },
    )]


def check_typed_absence(record: dict, components: list[dict]) -> list[Failure]:
    """Spec §11: every component with empty content has an absence_reason."""
    out: list[Failure] = []
    for c in components:
        content = c["content_json"] or {}
        # Strip the absence_reason field itself before judging emptiness.
        substantive = {k: v for k, v in content.items() if k != "absence_reason"}
        is_empty = all(v in (None, "", [], {}, 0) for v in substantive.values()) \
            if substantive else True
        has_absence_reason = bool(content.get("absence_reason"))
        if is_empty and not has_absence_reason and c["status"] != "present":
            out.append(Failure(
                paper_id=record["paper_id"], record_id=record["record_id"],
                check="components.typed_absence",
                message=(f"{c['component_type']} has empty content but no "
                         "absence_reason; status={}".format(c["status"])),
            ))
    return out


def check_support_set_present(record: dict, components: list[dict]) -> list[Failure]:
    out: list[Failure] = []
    for c in components:
        if not c.get("support_set_id"):
            out.append(Failure(
                paper_id=record["paper_id"], record_id=record["record_id"],
                check="components.support_set_present",
                message=f"{c['component_type']} missing support_set_id",
            ))
    return out


def check_support_set_hashes(conn: sqlite3.Connection, record: dict,
                              components: list[dict]) -> list[Failure]:
    out: list[Failure] = []
    seen: dict[str, dict | None] = {}
    for c in components:
        ssid = c["support_set_id"]
        if not ssid:
            continue
        if ssid not in seen:
            seen[ssid] = load_support_set(conn, ssid)
        ss = seen[ssid]
        if ss is None:
            out.append(Failure(
                paper_id=record["paper_id"], record_id=record["record_id"],
                check="support_sets.referenced_row_exists",
                message=f"{c['component_type']} references missing {ssid}",
            ))
            continue
        sorted_members = sorted(
            ss["members"],
            key=lambda m: (m.get("source_artifact_id", ""),
                           m.get("source_field_path", "")),
        )
        recomputed = sha256_canonical(sorted_members)
        if recomputed != ss["support_set_hash"]:
            out.append(Failure(
                paper_id=record["paper_id"], record_id=record["record_id"],
                check="support_sets.hash_recomputes",
                message=(f"{ssid}: stored={ss['support_set_hash']!r} "
                         f"recomputed={recomputed!r}"),
            ))
    return out


def check_content_hashes(record: dict, components: list[dict]) -> list[Failure]:
    out: list[Failure] = []
    for c in components:
        recomputed = sha256_canonical(c["content_json"])
        if recomputed != c["content_hash"]:
            out.append(Failure(
                paper_id=record["paper_id"], record_id=record["record_id"],
                check="components.content_hash_recomputes",
                message=(f"{c['component_type']}: stored={c['content_hash']!r} "
                         f"recomputed={recomputed!r}"),
            ))
    return out


def check_payload_hash(record: dict, components: list[dict]) -> list[Failure]:
    # Content-only hash (must match build_article_epistemic_layer.py
    # content_for_hash exactly): identity + component content, NO mutable
    # lifecycle/status fields. This is what lets the published payload be
    # recomputed from its own bytes and lets promotion/review/freshness change
    # without rewriting content hashes. Supersedes the old status-inclusive
    # definition (spec §6/§7 amended).
    content = {
        "schema_version": record["schema_version"],
        "record_id": record["record_id"],
        "paper_id": record["paper_id"],
        "primary_claim_id": record["primary_claim_id"],
        "components": {c["component_type"]: c["content_json"] for c in components},
    }
    recomputed = "sha256:" + sha256_canonical(content)
    if recomputed != record["payload_hash"]:
        return [Failure(
            paper_id=record["paper_id"], record_id=record["record_id"],
            check="records.payload_hash_recomputes",
            message=(f"stored={record['payload_hash']!r} "
                     f"recomputed={recomputed!r}"),
        )]
    return []


def check_evidence_strength_claim_bound(record: dict, components: list[dict]
                                         ) -> list[Failure]:
    ev = next((c for c in components if c["component_type"] == "evidence_strength"), None)
    if ev is None:
        return []
    if ev["status"] == "not_applicable":
        # Allowed when no primary claim exists.
        return []
    claim_id = ev["content_json"].get("claim_id")
    if not claim_id:
        return [Failure(
            paper_id=record["paper_id"], record_id=record["record_id"],
            check="evidence_strength.claim_bound",
            message="evidence_strength is present but has no claim_id",
        )]
    return []


def check_count_reconciliation(record: dict, components: list[dict]
                                ) -> list[Failure]:
    """spec §11: support and attack counts reconcile with rows OR declare a basis."""
    ev = next((c for c in components if c["component_type"] == "evidence_strength"), None)
    defeaters = next((c for c in components if c["component_type"] == "defeaters"), None)
    if ev is None or defeaters is None:
        return []
    ev_attack = ev["content_json"].get("attack_count")
    def_rows = defeaters["content_json"].get("rows", []) or []
    def_basis = (
        defeaters["content_json"].get("no_defeater_basis")
        or defeaters["content_json"].get("absence_reason")
    )
    if ev_attack is None or ev_attack == 0:
        return []
    if len(def_rows) >= ev_attack:
        return []
    if def_basis:
        return []
    return [Failure(
        paper_id=record["paper_id"], record_id=record["record_id"],
        check="counts.reconcile",
        message=(f"evidence_strength.attack_count={ev_attack} but defeater rows "
                 f"={len(def_rows)} and no count basis declared"),
        repair_action={
            "component_type": "defeaters",
            "reason": "attack_count_without_mapped_rows",
            "severity": "warning",
            "next_action": (
                f"reconcile counts for {record['paper_id']}: either extract "
                f"{ev_attack} defeater rows or declare a count basis."
            ),
        },
    )]


def check_defeater_row_contract(record: dict, components: list[dict]) -> list[Failure]:
    """Spec §8 (Pollock): any extracted defeater row MUST carry a target_kind
    (which inference it attacks) and a defeat_kind (rebutting vs undercutting).
    Stage 1 extracts no rows, so this is forward-looking enforcement: the moment
    a row appears it must be a defeat relation, not an untyped blob."""
    defeaters = next((c for c in components if c["component_type"] == "defeaters"), None)
    if defeaters is None:
        return []
    rows = defeaters["content_json"].get("rows", []) or []
    out: list[Failure] = []
    for i, row in enumerate(rows):
        tk = (row or {}).get("target_kind")
        dk = (row or {}).get("defeat_kind")
        if tk not in VOCAB_DEFEATER_TARGET_KIND:
            out.append(Failure(
                paper_id=record["paper_id"], record_id=record["record_id"],
                check="defeaters.row_target_kind",
                message=f"defeater row {i} target_kind={tk!r} not in vocab",
            ))
        if dk not in VOCAB_DEFEATER_DEFEAT_KIND:
            out.append(Failure(
                paper_id=record["paper_id"], record_id=record["record_id"],
                check="defeaters.row_defeat_kind",
                message=f"defeater row {i} defeat_kind={dk!r} not in "
                        "{rebutting, undercutting}",
            ))
    return out


def check_no_llm_in_stage1(record: dict, components: list[dict]) -> list[Failure]:
    """Spec §9: Stage 1 must not produce llm_generated source_mode."""
    out: list[Failure] = []
    for c in components:
        if c["source_mode"] == "llm_generated":
            out.append(Failure(
                paper_id=record["paper_id"], record_id=record["record_id"],
                check="stage1.no_llm_source_mode",
                message=(f"{c['component_type']} has source_mode='llm_generated' "
                         "which is forbidden in Stage 1"),
                severity="fail",
                repair_action={
                    "component_type": c["component_type"],
                    "reason": "llm_source_mode_in_stage1",
                    "severity": "blocking",
                    "next_action": (
                        "Remove llm_generated content; Stage 1 is deterministic "
                        "only. Add the field to llm_enrichable policy in Stage 2."
                    ),
                },
            ))
    return out


def check_forbidden_provider_imports() -> list[Failure]:
    """Spec §9: builder must not import or call provider SDKs directly."""
    if not BUILDER_SCRIPT.exists():
        return []
    src = BUILDER_SCRIPT.read_text()
    out: list[Failure] = []
    for pat in FORBIDDEN_PROVIDER_PATTERNS:
        if pat.search(src):
            out.append(Failure(
                paper_id=None, record_id=None,
                check="builder.no_provider_sdks",
                message=(f"forbidden import matched pattern {pat.pattern!r} in "
                         f"{BUILDER_SCRIPT.name}"),
                repair_action={
                    "component_type": "build",
                    "reason": "forbidden_provider_sdk_import",
                    "severity": "blocking",
                    "next_action": (
                        f"Remove direct provider import from {BUILDER_SCRIPT.name}; "
                        "Stage 2 must use the approved subscription-CLI path."
                    ),
                },
            ))
    return out


def check_release_eligibility_gating(record: dict, components: list[dict]
                                       ) -> list[Failure]:
    """Spec §13: a stale required component must block release eligibility.

    Stage 1 always sets release_eligible=0, but if a Stage 2 builder ever
    upgrades it, this check holds the line.
    """
    if not record["release_eligible"]:
        return []
    stale_required = [
        c for c in components
        if c["component_type"] in RELEASE_BLOCKING_COMPONENTS
        and c["freshness_status"] == "stale"
    ]
    if not stale_required:
        return []
    return [Failure(
        paper_id=record["paper_id"], record_id=record["record_id"],
        check="release.gated_by_required_freshness",
        message=(f"release_eligible=1 but required components are stale: "
                 f"{[c['component_type'] for c in stale_required]}"),
        repair_action={
            "component_type": "release",
            "reason": "release_eligible_with_stale_required_components",
            "severity": "blocking",
            "next_action": "Set release_eligible=0 and refresh stale components.",
        },
    )]


def check_completion_queue_present_for_repairable(
    conn: sqlite3.Connection, record: dict
) -> list[Failure]:
    """For every entry in blocking_failures_json there must be an open queue row."""
    if not record["blocking_failures"]:
        return []
    open_queue = load_open_queue_for_paper(conn, record["paper_id"])
    open_lookup = {(q["component_type"], q["reason"]) for q in open_queue}
    out: list[Failure] = []
    for bf in record["blocking_failures"]:
        key = (bf.get("component_type"), bf.get("reason"))
        if key not in open_lookup:
            out.append(Failure(
                paper_id=record["paper_id"], record_id=record["record_id"],
                check="completion_queue.entry_exists_for_blocking_failure",
                message=(f"blocking failure {key} has no open queue entry"),
                repair_action={
                    "component_type": bf.get("component_type") or "build",
                    "reason": bf.get("reason") or "queue_entry_missing",
                    "severity": "blocking",
                    "next_action": "Re-run builder to refresh queue, or open repair manually.",
                },
            ))
    return out


def check_one_active_per_paper(conn: sqlite3.Connection) -> list[Failure]:
    rows = conn.execute(
        "SELECT paper_id, schema_version, COUNT(*) c "
        "FROM article_epistemic_records WHERE active=1 "
        "GROUP BY paper_id, schema_version HAVING c > 1"
    ).fetchall()
    return [Failure(
        paper_id=r[0], record_id=None,
        check="records.one_active_per_paper",
        message=f"paper_id={r[0]} schema_version={r[1]} has {r[2]} active rows",
    ) for r in rows]


def check_public_payload_fields(payload: dict) -> list[Failure]:
    """Spec §11: rendered payload contains required public fields."""
    if not payload:
        return []
    details = payload.get("details") or {}
    out: list[Failure] = []
    for paper_id, layer in details.items():
        missing = REQUIRED_PUBLIC_FIELDS - set(layer.keys())
        if missing:
            out.append(Failure(
                paper_id=paper_id, record_id=layer.get("record_id"),
                check="public_payload.required_fields",
                message=f"missing required fields: {sorted(missing)}",
                repair_action={
                    "component_type": "build",
                    "reason": "public_payload_missing_required_fields",
                    "severity": "blocking",
                    "next_action": "Re-run builder; payload writer must include all required fields.",
                },
            ))
    return out


# ---------------------------------------------------------------------------
# Verification orchestration
# ---------------------------------------------------------------------------

def verify_all(conn: sqlite3.Connection, payload: dict | None
                ) -> tuple[list[Failure], dict[str, list[Failure]], list[str]]:
    """Return (global_failures, per_record_failures, record_ids_verified)."""
    global_failures: list[Failure] = []
    per_record: dict[str, list[Failure]] = {}

    # Global checks first.
    global_failures.extend(check_forbidden_provider_imports())
    global_failures.extend(check_one_active_per_paper(conn))
    if payload is not None:
        global_failures.extend(check_public_payload_fields(payload))

    # Per-record checks.
    records = load_active_records(conn)
    record_ids: list[str] = []
    for paper_id, record in records.items():
        components = load_components_for_record(conn, record["record_id"],
                                                record["build_run_id"])
        fails: list[Failure] = []
        fails.extend(check_status_vocabularies(record, components))
        fails.extend(check_required_components(record, components))
        fails.extend(check_typed_absence(record, components))
        fails.extend(check_support_set_present(record, components))
        fails.extend(check_support_set_hashes(conn, record, components))
        fails.extend(check_content_hashes(record, components))
        fails.extend(check_payload_hash(record, components))
        fails.extend(check_evidence_strength_claim_bound(record, components))
        fails.extend(check_count_reconciliation(record, components))
        fails.extend(check_defeater_row_contract(record, components))
        fails.extend(check_no_llm_in_stage1(record, components))
        fails.extend(check_release_eligibility_gating(record, components))
        fails.extend(check_completion_queue_present_for_repairable(conn, record))
        per_record[record["record_id"]] = fails
        record_ids.append(record["record_id"])

    return global_failures, per_record, record_ids


# ---------------------------------------------------------------------------
# Persistence: verification events + completion queue
# ---------------------------------------------------------------------------

def write_verification_event(
    conn: sqlite3.Connection,
    *,
    record_id: str | None,
    build_run_id: str,
    status: str,
    failures: list[Failure],
) -> None:
    # Global verification events (record_id IS NULL) are written as-is; the
    # composite FK is satisfied under MATCH SIMPLE when record_id is NULL.
    failures_json = json.dumps([f.to_dict() for f in failures], sort_keys=True)
    repair_json = json.dumps(
        [{"paper_id": f.paper_id, **f.repair_action}
         for f in failures if f.repair_action],
        sort_keys=True,
    )
    conn.execute(
        "INSERT INTO article_epistemic_verification_events("
        "  record_id, build_run_id, verifier_name, verifier_version, "
        "  status, failures_json, repair_actions_json"
        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
        (record_id, build_run_id, VERIFIER_NAME, VERIFIER_VERSION,
         status, failures_json, repair_json),
    )


def write_repair_actions_to_queue(conn: sqlite3.Connection,
                                   failures: list[Failure]) -> int:
    written = 0
    for f in failures:
        if not f.repair_action or f.paper_id is None:
            # Global / structural failures without a paper context can't go
            # to the per-paper completion queue; they live in events only.
            continue
        ra = f.repair_action
        conn.execute(
            "INSERT INTO article_epistemic_completion_queue("
            "  paper_id, component_type, reason, severity, next_action, "
            "  status, attempt_count"
            ") VALUES (?, ?, ?, ?, ?, 'open', 1) "
            "ON CONFLICT(paper_id, component_type, reason) "
            "  WHERE status IN ('open', 'in_progress') "
            "  DO UPDATE SET "
            "    last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), "
            "    attempt_count = article_epistemic_completion_queue.attempt_count + 1",
            (f.paper_id, ra["component_type"], ra["reason"], ra["severity"],
             ra["next_action"]),
        )
        written += 1
    return written


def resolve_build_run_id(conn: sqlite3.Connection,
                         records: dict[str, dict]) -> str:
    """Use the most recent build_run_id seen on an active record, falling back
    to a verifier-only build_run row if no records exist yet."""
    build_run_ids = sorted({r["build_run_id"] for r in records.values()}, reverse=True)
    if build_run_ids:
        return build_run_ids[0]
    # No active records — record a verifier-only run.
    started_at = utc_now()
    date_part = started_at[:10].replace("-", "")
    prefix = f"aepl-{date_part}-"
    row = conn.execute(
        "SELECT build_run_id FROM article_epistemic_build_runs "
        "WHERE build_run_id LIKE ? ORDER BY build_run_id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    next_seq = 1 if row is None else int(row[0].rsplit("-", 1)[-1]) + 1
    build_run_id = f"{prefix}{next_seq:06d}"
    conn.execute(
        "INSERT INTO article_epistemic_build_runs("
        "  build_run_id, builder_version, started_at, status"
        ") VALUES (?, ?, ?, 'completed')",
        (build_run_id, "verifier_only", started_at),
    )
    return build_run_id


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="Lifecycle DB (default: auto)")
    parser.add_argument("--payload", default=str(DEFAULT_PAYLOAD),
                        help=f"Public payload JSON (default: {DEFAULT_PAYLOAD})")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero on any fail-severity result")
    parser.add_argument("--no-write", action="store_true",
                        help="Do not persist events or queue entries to the DB")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-record failure listing on stdout")
    args = parser.parse_args(argv)

    db_path = resolve_db_path(args.db)
    if not db_path.exists():
        print(f"ERROR: lifecycle DB not found: {db_path}", file=sys.stderr)
        return 2

    payload_path = Path(args.payload)
    if not payload_path.is_absolute():
        payload_path = REPO_ROOT / payload_path
    payload: dict | None = None
    if payload_path.exists():
        try:
            payload = json.loads(payload_path.read_text())
        except json.JSONDecodeError as exc:
            print(f"WARNING: payload not parseable ({payload_path}): {exc}",
                  file=sys.stderr)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    # Fail fast with a clear message if the DB is present but un-initialized,
    # instead of crashing with "no such table" inside a check (panel finding).
    if conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='article_epistemic_records'"
    ).fetchone() is None:
        conn.close()
        print(f"ERROR: lifecycle DB at {db_path} has no 'article_epistemic_records' "
              f"table — present but un-initialized.\n"
              f"  Run: python3 scripts/article_epistemic_layer_init.py --db {db_path}\n"
              f"  or:  pass --db 160sp/pipeline_lifecycle_full.db to target the real DB.",
              file=sys.stderr)
        return 2
    try:
        global_failures, per_record_failures, record_ids = verify_all(conn, payload)
        records = load_active_records(conn)
        build_run_id = resolve_build_run_id(conn, records)

        if not args.no_write:
            # record_id -> build_run_id, for the machine_verified UPDATE.
            build_run_by_record = {r["record_id"]: r["build_run_id"]
                                    for r in records.values()}
            with conn:
                # Global event row, even if empty (to mark a verifier run).
                write_verification_event(
                    conn, record_id=None, build_run_id=build_run_id,
                    status="fail" if global_failures else "pass",
                    failures=global_failures,
                )
                # Per-record event rows.
                for rec_id in record_ids:
                    fails = per_record_failures.get(rec_id, [])
                    write_verification_event(
                        conn, record_id=rec_id, build_run_id=build_run_id,
                        status="fail" if fails else "pass",
                        failures=fails,
                    )
                    # Spec §4/§11 (Mayo): a record that passes the full §11
                    # battery (its own checks AND no run-scoped global failures)
                    # is machine_verified. This is the only writer of that state;
                    # without it the value is unreachable. review_status is NOT
                    # in the content hash, so this does not invalidate
                    # payload_hash. A dirty record is left 'unreviewed'; a record
                    # previously machine_verified that now fails is demoted.
                    new_status = ("machine_verified"
                                  if not fails and not global_failures
                                  else "unreviewed")
                    conn.execute(
                        "UPDATE article_epistemic_records "
                        "SET review_status = ?, "
                        "    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                        "WHERE record_id = ? AND build_run_id = ? AND active = 1",
                        (new_status, rec_id, build_run_by_record.get(rec_id)),
                    )
                # Repair actions to queue.
                all_failures = global_failures + [
                    f for rid in record_ids for f in per_record_failures.get(rid, [])
                ]
                write_repair_actions_to_queue(conn, all_failures)
    finally:
        conn.close()

    total_failures = len(global_failures) + sum(
        len(v) for v in per_record_failures.values()
    )
    records_with_failures = sum(1 for v in per_record_failures.values() if v)
    records_clean = len(record_ids) - records_with_failures

    print(f"Verified {len(record_ids)} active records.")
    print(f"  Clean:   {records_clean}")
    print(f"  With failures: {records_with_failures}")
    print(f"  Global failures: {len(global_failures)}")
    print(f"  Total failures: {total_failures}")

    if not args.quiet and total_failures:
        # Surface a sample of failures so operators see what broke.
        sample = []
        for f in global_failures[:5]:
            sample.append(f)
        for rid in record_ids:
            for f in per_record_failures.get(rid, [])[:1]:
                sample.append(f)
                if len(sample) >= 10:
                    break
            if len(sample) >= 10:
                break
        print("Sample failures:")
        for f in sample:
            ctx = f.paper_id or "<global>"
            print(f"  [{ctx}] {f.check}: {f.message}")

    if args.strict and total_failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
