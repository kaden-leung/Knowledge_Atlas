"""Build-run registration for the dependency overseer.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §3.2 §8
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P4)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from overseer.ids import build_run_id as new_build_run_id, utc_now_iso

ALLOWED_STATUSES = ("running", "verified", "failed", "aborted", "rehash")


@dataclass(frozen=True)
class BuildRun:
    build_run_id: str
    builder_name: str
    builder_version: str
    started_at: str
    finished_at: str | None
    status: str
    input_snapshot_hash: str | None
    record_count: int | None
    success_count: int | None
    failure_count: int | None
    report_json: str | None


def start(
    conn: sqlite3.Connection,
    *,
    builder_name: str,
    builder_version: str,
    input_snapshot_hash: str | None = None,
) -> str:
    """Open a new build run. Returns build_run_id."""
    brid = new_build_run_id(builder_name)
    conn.execute(
        """
        INSERT INTO build_runs (
            build_run_id, builder_name, builder_version, started_at, finished_at,
            status, input_snapshot_hash, record_count, success_count,
            failure_count, report_json
        ) VALUES (?, ?, ?, ?, NULL, 'running', ?, NULL, NULL, NULL, NULL)
        """,
        (brid, builder_name, builder_version, utc_now_iso(), input_snapshot_hash),
    )
    return brid


def finish(
    conn: sqlite3.Connection,
    *,
    build_run_id: str,
    status: str,
    record_count: int = 0,
    success_count: int = 0,
    failure_count: int = 0,
    report: dict | None = None,
) -> None:
    """Close a build run."""
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"status '{status}' not in {ALLOWED_STATUSES}")
    report_json = json.dumps(report, separators=(",", ":"), ensure_ascii=False) if report else None
    conn.execute(
        """
        UPDATE build_runs SET
            finished_at = ?, status = ?, record_count = ?,
            success_count = ?, failure_count = ?, report_json = ?
        WHERE build_run_id = ?
        """,
        (utc_now_iso(), status, record_count, success_count, failure_count,
         report_json, build_run_id),
    )


def get(conn: sqlite3.Connection, build_run_id: str) -> BuildRun | None:
    row = conn.execute(
        "SELECT * FROM build_runs WHERE build_run_id = ?", (build_run_id,)
    ).fetchone()
    if row is None:
        return None
    return BuildRun(
        build_run_id=row["build_run_id"], builder_name=row["builder_name"],
        builder_version=row["builder_version"], started_at=row["started_at"],
        finished_at=row["finished_at"], status=row["status"],
        input_snapshot_hash=row["input_snapshot_hash"],
        record_count=row["record_count"], success_count=row["success_count"],
        failure_count=row["failure_count"], report_json=row["report_json"],
    )
