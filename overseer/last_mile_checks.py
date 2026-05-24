"""Last-mile production checks recorder.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §3.6 §13
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P15)

Phase 1 ships the recorder (writes to last_mile_production_checks) and a
release-gate query (most_recent_status_per_artefact). The actual probe
implementations (HTTP GET, headless browser checks) are wired into
verifier_render which selects an HTTP library per impl spec §14 OIQ #2.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from overseer.ids import check_id, utc_now_iso

ALLOWED_KINDS = (
    "http_200", "asset_200", "no_console_error",
    "payload_hash_equal", "mobile_layout", "provenance_visible",
)
ALLOWED_STATUSES = ("pass", "fail", "skipped")


@dataclass(frozen=True)
class CheckRecord:
    check_id: str
    artefact_id: str
    check_kind: str
    status: str
    evidence: dict | None
    created_at: str


def record(
    conn: sqlite3.Connection,
    *,
    artefact_id: str,
    check_kind: str,
    status: str,
    evidence: dict | None = None,
) -> str:
    """Record one last-mile check result. Returns the check_id."""
    if check_kind not in ALLOWED_KINDS:
        raise ValueError(f"check_kind '{check_kind}' not in {ALLOWED_KINDS}")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"status '{status}' not in {ALLOWED_STATUSES}")
    cid = check_id()
    conn.execute(
        """
        INSERT INTO last_mile_production_checks (
            check_id, artefact_id, check_kind, status, evidence_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            cid, artefact_id, check_kind, status,
            json.dumps(evidence, separators=(",", ":")) if evidence else None,
            utc_now_iso(),
        ),
    )
    return cid


def most_recent_per_artefact_and_kind(
    conn: sqlite3.Connection,
    *,
    within_seconds: int | None = None,
) -> dict[tuple[str, str], CheckRecord]:
    """Return the most recent check per (artefact_id, check_kind), optionally
    restricted to checks within the last N seconds.
    """
    if within_seconds is not None:
        rows = conn.execute(
            """
            SELECT check_id, artefact_id, check_kind, status, evidence_json, created_at
            FROM last_mile_production_checks
            WHERE (julianday('now') - julianday(created_at)) * 86400.0 <= ?
            ORDER BY created_at DESC
            """,
            (within_seconds,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT check_id, artefact_id, check_kind, status, evidence_json, created_at
            FROM last_mile_production_checks
            ORDER BY created_at DESC
            """,
        ).fetchall()
    out: dict[tuple[str, str], CheckRecord] = {}
    for r in rows:
        key = (r["artefact_id"], r["check_kind"])
        if key in out:
            continue
        out[key] = CheckRecord(
            check_id=r["check_id"], artefact_id=r["artefact_id"],
            check_kind=r["check_kind"], status=r["status"],
            evidence=json.loads(r["evidence_json"]) if r["evidence_json"] else None,
            created_at=r["created_at"],
        )
    return out


def has_recent_failures(
    conn: sqlite3.Connection,
    *,
    within_seconds: int = 3600,
) -> bool:
    """Return True if any last_mile check failed within the window.

    Used by the release-gate (`can_promote`) to block promotion when
    production probes are red. Default window: 1 hour.
    """
    row = conn.execute(
        """
        SELECT 1 FROM last_mile_production_checks
        WHERE status = 'fail'
          AND (julianday('now') - julianday(created_at)) * 86400.0 <= ?
        LIMIT 1
        """,
        (within_seconds,),
    ).fetchone()
    return row is not None
