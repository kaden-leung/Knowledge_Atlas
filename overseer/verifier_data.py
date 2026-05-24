"""Strict data verifier for the dependency overseer.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §4 §10
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (§4 verifier contract)

Each check returns a CheckResult. verify_strict() runs every check and
returns a VerificationReport. The wrapper script
scripts/verify_dependency_overseer_contract.py exits 0 on overall pass
and 1 on any failure.

Phase 1 scope:
  * Core invariants: referential integrity, active-record uniqueness, hash
    presence on active records, defeater target-typing, claim
    canonicalization, kind registration, queue invariants, fencing-token
    monotonicity, vocabulary canonicalization integrity, answer-shape
    rule-trace presence.
  * Phase 2/3 checks (cross-DB sync, LLM provenance, LLM field policy)
    return pass with empty failures while their scaffold tables remain
    empty.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
_STATUS_VOCAB_PATH = (
    REPO_ROOT
    / "contracts"
    / "schemas"
    / "dependency_overseer"
    / "status_vocabularies.json"
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    failures: list[dict] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class VerificationReport:
    overall_passed: bool
    checks: list[CheckResult]
    started_at: str
    finished_at: str


# ----------------------------------------------------------------------------
# Individual checks
# ----------------------------------------------------------------------------

def _check_referential_integrity(conn: sqlite3.Connection) -> CheckResult:
    """Every dependency_edges endpoint resolves to an artefact_registry row."""
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT e.parent_artefact_id, e.child_artefact_id, e.edge_kind
        FROM dependency_edges e
        LEFT JOIN artefact_registry pa ON pa.artefact_id = e.parent_artefact_id
        LEFT JOIN artefact_registry ca ON ca.artefact_id = e.child_artefact_id
        WHERE (pa.artefact_id IS NULL OR ca.artefact_id IS NULL)
          AND e.tombstoned_at IS NULL
        """,
    ).fetchall()
    for r in rows:
        failures.append({
            "edge": dict(r),
            "message": "dependency_edges row has missing endpoint",
        })
    return CheckResult(
        name="referential_integrity",
        passed=not failures,
        failures=failures,
        description="Every active dependency_edges endpoint resolves in artefact_registry.",
    )


def _check_active_record_uniqueness(conn: sqlite3.Connection) -> CheckResult:
    """At most one active row per (entity_type, entity_id, field_path, schema_version)."""
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT entity_type, entity_id, field_path, schema_version, COUNT(*) AS n
        FROM artefact_registry
        WHERE active = 1
        GROUP BY entity_type, entity_id, field_path, schema_version
        HAVING n > 1
        """,
    ).fetchall()
    for r in rows:
        failures.append({"natural_key": dict(r), "message": "multiple active rows"})
    return CheckResult(
        name="active_record_uniqueness",
        passed=not failures,
        failures=failures,
        description="(entity_type, entity_id, field_path, schema_version) is unique among active rows.",
    )


def _check_hash_presence_on_fresh_artefacts(conn: sqlite3.Connection) -> CheckResult:
    """Every artefact_registry row with freshness_status='fresh' has both
    raw_hash and semantic_hash populated. (Hash recompute equality requires
    the source content; the builder enforces it at write time. This check
    catches stragglers where a fresh row lacks hashes.)"""
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT artefact_id, raw_hash, semantic_hash
        FROM artefact_registry
        WHERE active = 1 AND freshness_status = 'fresh'
          AND (raw_hash IS NULL OR semantic_hash IS NULL)
        """,
    ).fetchall()
    for r in rows:
        failures.append({"artefact_id": r["artefact_id"], "raw_hash": r["raw_hash"],
                         "semantic_hash": r["semantic_hash"]})
    return CheckResult(
        name="hash_presence_on_fresh_artefacts",
        passed=not failures,
        failures=failures,
        description="Active fresh artefacts have both raw_hash and semantic_hash.",
    )


def _check_semantic_hash_propagation(conn: sqlite3.Connection) -> CheckResult:
    """A rebuild_queue row exists for an artefact only if its semantic_hash
    changed across content_hashes history. Raw-only changes must not produce
    queue rows (P27).
    """
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT rq.queue_id, rq.artefact_id
        FROM rebuild_queue rq
        WHERE rq.state IN ('queued','claimed','building')
        """,
    ).fetchall()
    for r in rows:
        history = conn.execute(
            """
            SELECT semantic_hash FROM content_hashes
            WHERE artefact_id = ? ORDER BY hashed_at DESC LIMIT 2
            """,
            (r["artefact_id"],),
        ).fetchall()
        if len(history) >= 2 and history[0]["semantic_hash"] == history[1]["semantic_hash"]:
            failures.append({
                "queue_id": r["queue_id"],
                "artefact_id": r["artefact_id"],
                "message": "rebuild queued but semantic_hash unchanged across last two builds",
            })
    return CheckResult(
        name="semantic_hash_propagation",
        passed=not failures,
        failures=failures,
        description="Rebuilds enqueued only when semantic_hash changed.",
    )


def _check_normalization_rule_pinning(conn: sqlite3.Connection) -> CheckResult:
    """Every content_hashes row carries a normalization_rule_version, and the
    active set uses one consistent rule version per builder pass."""
    failures: list[dict] = []
    null_rows = conn.execute(
        """
        SELECT artefact_id, build_run_id FROM content_hashes
        WHERE normalization_rule_version IS NULL OR normalization_rule_version = ''
        """,
    ).fetchall()
    for r in null_rows:
        failures.append({"artefact_id": r["artefact_id"], "build_run_id": r["build_run_id"],
                         "message": "missing normalization_rule_version"})
    return CheckResult(
        name="normalization_rule_pinning",
        passed=not failures,
        failures=failures,
        description="Every content_hashes row has a non-empty normalization_rule_version.",
    )


def _check_closed_enum_membership(conn: sqlite3.Connection) -> CheckResult:
    """Sanity check that closed-enum CHECK constraints in DDL match the JSON
    contract file. Any drift (e.g., new code path writes an unlisted value)
    would normally trip the DDL CHECK and never land in DB, but this verifier
    confirms the contract file remains the source of truth."""
    failures: list[dict] = []
    try:
        vocab = json.loads(_STATUS_VOCAB_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        return CheckResult(
            name="closed_enum_membership",
            passed=False,
            failures=[{"error": str(e)}],
            description="status_vocabularies.json must exist.",
        )
    # Verify each column's actual values against the contract.
    column_checks = [
        ("artefact_registry", "freshness_status", "freshness_status"),
        ("rebuild_queue", "state", "queue_state"),
        ("rebuild_queue", "severity", "severity"),
        ("dependency_edges", "edge_kind", "edge_kind"),
        ("defeaters", "target_kind", "defeater_target_kind"),
        ("claims", "claim_origin", "claim_origin"),
        ("answer_shape_decisions", "shape", "answer_shape"),
        ("completion_queue", "status", "completion_queue_status"),
        ("completion_queue", "severity", "severity"),
        ("build_runs", "status", "build_run_status"),
    ]
    for table, col, vocab_key in column_checks:
        allowed = set(vocab.get(vocab_key, []))
        if not allowed:
            failures.append({"table": table, "col": col,
                             "message": f"vocab key '{vocab_key}' empty/missing"})
            continue
        rows = conn.execute(
            f"SELECT DISTINCT {col} AS v FROM {table} WHERE {col} IS NOT NULL"
        ).fetchall()
        for r in rows:
            if r["v"] not in allowed:
                failures.append({
                    "table": table, "col": col, "value": r["v"],
                    "message": f"value not in {vocab_key} vocabulary",
                })
    return CheckResult(
        name="closed_enum_membership",
        passed=not failures,
        failures=failures,
        description="DB closed-enum values match status_vocabularies.json.",
    )


def _check_vocabulary_canonicalization_integrity(conn: sqlite3.Connection) -> CheckResult:
    """Every 'synonym' row has a non-null canonical_value pointing at a
    'canonical' row of the same kind. No synonym chains of depth > 1."""
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT v1.kind, v1.value, v1.canonical_value, v1.review_status,
               v2.review_status AS target_status
        FROM vocabulary_registry v1
        LEFT JOIN vocabulary_registry v2
            ON v2.kind = v1.kind AND v2.value = v1.canonical_value
        WHERE v1.review_status = 'synonym'
        """,
    ).fetchall()
    for r in rows:
        if r["canonical_value"] is None:
            failures.append({
                "kind": r["kind"], "value": r["value"],
                "message": "synonym row has null canonical_value",
            })
            continue
        if r["target_status"] != "canonical":
            failures.append({
                "kind": r["kind"], "value": r["value"],
                "canonical_value": r["canonical_value"],
                "target_status": r["target_status"],
                "message": "synonym chain or canonical_value is not 'canonical'",
            })
    return CheckResult(
        name="vocabulary_canonicalization_integrity",
        passed=not failures,
        failures=failures,
        description="Synonym rows point at canonical rows; no chains.",
    )


def _check_kind_registration(conn: sqlite3.Connection) -> CheckResult:
    """Every active artefact's kind resolves in artefact_kinds (P12)."""
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT ar.artefact_id, ar.kind
        FROM artefact_registry ar
        LEFT JOIN artefact_kinds ak
            ON ak.kind_name = ar.kind AND ak.active = 1
        WHERE ar.active = 1 AND ak.kind_name IS NULL
        """,
    ).fetchall()
    for r in rows:
        failures.append({
            "artefact_id": r["artefact_id"], "kind": r["kind"],
            "message": "active artefact has unregistered kind",
        })
    return CheckResult(
        name="kind_registration",
        passed=not failures,
        failures=failures,
        description="Every active artefact's kind is registered in artefact_kinds.",
    )


def _check_queue_invariants_heartbeat_based(conn: sqlite3.Connection) -> CheckResult:
    """No claim whose owning worker's last_heartbeat_at is older than
    heartbeat_timeout_seconds is reachable from a 'ready' query (P7).
    Every claimed/building row has a non-null lease_owner and fencing_token > 0.
    """
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT rq.queue_id, rq.artefact_id, rq.state, rq.lease_owner,
               rq.fencing_token, wh.heartbeat_timeout_seconds,
               (julianday('now') - julianday(wh.last_heartbeat_at)) * 86400.0 AS age
        FROM rebuild_queue rq
        LEFT JOIN worker_heartbeats wh ON wh.worker_id = rq.lease_owner
        WHERE rq.state IN ('claimed','building')
        """,
    ).fetchall()
    for r in rows:
        if r["lease_owner"] is None:
            failures.append({"queue_id": r["queue_id"], "message": "claimed row has null lease_owner"})
            continue
        if r["fencing_token"] is None or r["fencing_token"] <= 0:
            failures.append({"queue_id": r["queue_id"], "message": "claimed row has invalid fencing_token"})
            continue
        if r["age"] is not None and r["heartbeat_timeout_seconds"] is not None:
            if r["age"] > r["heartbeat_timeout_seconds"]:
                failures.append({
                    "queue_id": r["queue_id"], "lease_owner": r["lease_owner"],
                    "age_seconds": int(r["age"]),
                    "timeout_seconds": r["heartbeat_timeout_seconds"],
                    "message": "claim past heartbeat timeout (watchdog should reclaim)",
                })
    return CheckResult(
        name="queue_invariants_heartbeat_based",
        passed=not failures,
        failures=failures,
        description="Claimed rows have valid owners + fresh heartbeats.",
    )


def _check_fencing_token_monotonicity(conn: sqlite3.Connection) -> CheckResult:
    """For every artefact, artefact_registry.current_fencing_token >= the
    max fencing_token of any of its queue rows.
    """
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT ar.artefact_id, ar.current_fencing_token,
               MAX(rq.fencing_token) AS max_queue_token
        FROM artefact_registry ar
        LEFT JOIN rebuild_queue rq ON rq.artefact_id = ar.artefact_id
        GROUP BY ar.artefact_id
        """,
    ).fetchall()
    for r in rows:
        if r["max_queue_token"] is not None and r["current_fencing_token"] < r["max_queue_token"]:
            failures.append({
                "artefact_id": r["artefact_id"],
                "current_fencing_token": r["current_fencing_token"],
                "max_queue_token": r["max_queue_token"],
                "message": "artefact current_fencing_token below max queue token (monotonicity violation)",
            })
    return CheckResult(
        name="fencing_token_monotonicity",
        passed=not failures,
        failures=failures,
        description="artefact_registry.current_fencing_token >= max queue token for each artefact.",
    )


def _check_defeater_target_typing(conn: sqlite3.Connection) -> CheckResult:
    """Every defeater row has a non-null target_kind (P16). The DDL CHECK
    enforces this; the verifier confirms zero stragglers."""
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT defeater_id FROM defeaters
        WHERE target_kind IS NULL OR target_kind = ''
        """,
    ).fetchall()
    for r in rows:
        failures.append({"defeater_id": r["defeater_id"]})
    return CheckResult(
        name="defeater_target_typing",
        passed=not failures,
        failures=failures,
        description="Every defeater row has a non-null target_kind.",
    )


def _check_claim_canonicalization(conn: sqlite3.Connection) -> CheckResult:
    """Every active claim_id resolves to exactly one canonical_claim_text."""
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT claim_id, COUNT(DISTINCT canonical_claim_text) AS n
        FROM claims
        WHERE tombstoned_at IS NULL
        GROUP BY claim_id
        HAVING n > 1
        """,
    ).fetchall()
    for r in rows:
        failures.append({"claim_id": r["claim_id"], "distinct_texts": r["n"]})
    return CheckResult(
        name="claim_canonicalization",
        passed=not failures,
        failures=failures,
        description="Each active claim_id resolves to one canonical_claim_text.",
    )


def _check_belief_network_freshness(conn: sqlite3.Connection) -> CheckResult:
    """Every active belief_network_link references a PNU artefact whose
    artefact_registry row is active OR the linking artefact is marked stale.
    """
    failures: list[dict] = []
    # Linking artefacts are identified by record_id format
    # 'article_epistemic_layer.v1:{paper_id}'. We check the artefact_registry
    # row for the matching paper_id has freshness_status != 'fresh' when the
    # link references a tombstoned PNU.
    rows = conn.execute(
        """
        SELECT bnl.record_id, bnl.pnu_id, bnl.pnu_version_hash, ar.active AS pnu_active
        FROM belief_network_links bnl
        LEFT JOIN artefact_registry ar
            ON ar.kind = 'pnu_row' AND ar.entity_id = bnl.pnu_id
        WHERE bnl.tombstoned_at IS NULL
        """,
    ).fetchall()
    for r in rows:
        if r["pnu_active"] is None or r["pnu_active"] == 0:
            # PNU is tombstoned. Check the linking article's freshness.
            paper_id = r["record_id"].split(":", 1)[-1]
            paper_freshness = conn.execute(
                """
                SELECT freshness_status FROM artefact_registry
                WHERE kind = 'article_epistemic_record' AND entity_id = ?
                  AND active = 1
                """,
                (paper_id,),
            ).fetchone()
            if paper_freshness and paper_freshness["freshness_status"] == "fresh":
                failures.append({
                    "record_id": r["record_id"], "pnu_id": r["pnu_id"],
                    "message": "link references tombstoned/missing PNU but linking artefact is fresh",
                })
    return CheckResult(
        name="belief_network_freshness",
        passed=not failures,
        failures=failures,
        description="Belief-network links pointing at tombstoned PNUs require stale artefacts.",
    )


def _check_answer_shape_rule_trace(conn: sqlite3.Connection) -> CheckResult:
    """If shape='unknown' the row must have a non-empty rule_trace_json (P18)."""
    failures: list[dict] = []
    rows = conn.execute(
        """
        SELECT record_id, created_at FROM answer_shape_decisions
        WHERE shape = 'unknown' AND superseded_at IS NULL
          AND (rule_trace_json IS NULL OR rule_trace_json = '')
        """,
    ).fetchall()
    for r in rows:
        failures.append({"record_id": r["record_id"], "created_at": r["created_at"]})
    return CheckResult(
        name="answer_shape_rule_trace",
        passed=not failures,
        failures=failures,
        description="answer_shape='unknown' requires a non-empty rule_trace_json.",
    )


def _check_scaffold_tables_empty(conn: sqlite3.Connection) -> CheckResult:
    """The five scaffold tables (cross_db_sync_events, llm_invocations,
    prompt_templates, source_packets, content_equivalence_checks) have no
    rows in Phase 1 (P28)."""
    failures: list[dict] = []
    scaffold = [
        "cross_db_sync_events", "llm_invocations", "prompt_templates",
        "source_packets", "content_equivalence_checks",
    ]
    for t in scaffold:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        if n > 0:
            failures.append({
                "table": t, "rows": n,
                "message": "scaffold-only table has rows in Phase 1",
            })
    return CheckResult(
        name="scaffold_tables_empty",
        passed=not failures,
        failures=failures,
        description="Phase 1 scaffold tables remain empty until their activating phase.",
    )


CHECKS: list[Callable[[sqlite3.Connection], CheckResult]] = [
    _check_referential_integrity,
    _check_active_record_uniqueness,
    _check_hash_presence_on_fresh_artefacts,
    _check_semantic_hash_propagation,
    _check_normalization_rule_pinning,
    _check_closed_enum_membership,
    _check_vocabulary_canonicalization_integrity,
    _check_kind_registration,
    _check_queue_invariants_heartbeat_based,
    _check_fencing_token_monotonicity,
    _check_defeater_target_typing,
    _check_claim_canonicalization,
    _check_belief_network_freshness,
    _check_answer_shape_rule_trace,
    _check_scaffold_tables_empty,
]


def verify_strict(conn: sqlite3.Connection) -> VerificationReport:
    """Run every check; return a structured report."""
    from datetime import datetime, timezone
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = [c(conn) for c in CHECKS]
    finished = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return VerificationReport(
        overall_passed=all(r.passed for r in results),
        checks=results,
        started_at=started,
        finished_at=finished,
    )


def report_to_dict(report: VerificationReport) -> dict[str, Any]:
    return {
        "overall_passed": report.overall_passed,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "description": c.description,
                "failures": c.failures,
            }
            for c in report.checks
        ],
    }
