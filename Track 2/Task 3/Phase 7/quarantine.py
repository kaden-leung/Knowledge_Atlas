"""Phase 7 — quarantine / restore utilities.

Provides two operations:

  quarantine(reference_id, reason, *, db_path, outbox_dir, run_id)
      Sets triage_decision='QUARANTINED', removes the row from v_acquisition_queue,
      moves the handoff artifact to outbox/quarantined/, and logs a transition.

  restore_from_quarantine(reference_id, reviewer_note, *, db_path, outbox_dir, run_id)
      Reverses the above: returns triage_decision to 'ACCEPT', moves the artifact
      back, and logs a restore transition.

Both operations require a reviewer_note and write a lifecycle_transitions row.
Neither mutates the committed evidence DB — they are production-path operations
and must be called on a working copy or pilot DB.
"""
from __future__ import annotations

import json
import hashlib
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DEFAULT_DB = _HERE.parent / "task3_pipeline_lifecycle.db"
DEFAULT_OUTBOX = _HERE / "handoff_outbox"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id_now() -> str:
    return f"RUN-QT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


class QuarantineError(ValueError):
    """Raised for invalid quarantine/restore operations."""


def _artifact_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quarantine(
    reference_id: str,
    reason: str,
    *,
    db_path: Path = DEFAULT_DB,
    outbox_dir: Path = DEFAULT_OUTBOX,
    run_id: str | None = None,
) -> None:
    """Move a reference to QUARANTINED state.

    - Sets triage_decision='QUARANTINED' in article_references.
    - Logs a lifecycle_transitions row with reason.
    - Moves the handoff artifact (if present) to outbox_dir/quarantined/.

    Raises QuarantineError if the row doesn't exist or is not in ACCEPT.
    """
    if not reason or not reason.strip():
        raise QuarantineError("reason must be a non-empty string")
    run_id = run_id or _run_id_now()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        row = conn.execute(
            "SELECT triage_decision FROM article_references WHERE reference_id = ?",
            (reference_id,),
        ).fetchone()
        if row is None:
            raise QuarantineError(f"reference_id '{reference_id}' not found")
        if row[0] != "ACCEPT":
            raise QuarantineError(
                f"'{reference_id}' must be ACCEPT before quarantine (current: {row[0]})"
            )

        now = _utc_now()
        artifact = outbox_dir / f"{reference_id}.json"
        audit_reason = json.dumps({
            "reason": reason.strip(),
            "previous_decision": row[0],
            "artifact_sha256": _artifact_sha256(artifact),
        }, separators=(",", ":"))
        conn.execute(
            "UPDATE article_references SET triage_decision='QUARANTINED', updated_at=? "
            "WHERE reference_id=?",
            (now, reference_id),
        )
        conn.execute(
            """
            INSERT INTO lifecycle_transitions
              (reference_id, run_id, from_stage, to_stage, reason, created_by)
            VALUES (?, ?, 'triage_complete', 'quarantined', ?, 'quarantine')
            """,
            (reference_id, run_id, audit_reason),
        )
        conn.commit()
    finally:
        conn.close()

    # Move artifact file if it exists
    artifact = outbox_dir / f"{reference_id}.json"
    quarantine_dir = outbox_dir / "quarantined"
    if artifact.exists():
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(artifact), str(quarantine_dir / artifact.name))


def restore_from_quarantine(
    reference_id: str,
    reviewer_note: str,
    *,
    db_path: Path = DEFAULT_DB,
    outbox_dir: Path = DEFAULT_OUTBOX,
    run_id: str | None = None,
) -> None:
    """Restore a QUARANTINED reference back to ACCEPT.

    - Sets triage_decision='ACCEPT'.
    - Logs a lifecycle_transitions row with reviewer_note.
    - Moves the artifact back from outbox_dir/quarantined/ to outbox_dir/.

    Raises QuarantineError if the row doesn't exist or is not QUARANTINED.
    """
    if not reviewer_note or not reviewer_note.strip():
        raise QuarantineError("reviewer_note must be a non-empty string")
    run_id = run_id or _run_id_now()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        row = conn.execute(
            "SELECT triage_decision FROM article_references WHERE reference_id = ?",
            (reference_id,),
        ).fetchone()
        if row is None:
            raise QuarantineError(f"reference_id '{reference_id}' not found")
        if row[0] != "QUARANTINED":
            raise QuarantineError(
                f"'{reference_id}' is not QUARANTINED (current: {row[0]})"
            )

        now = _utc_now()
        conn.execute(
            "UPDATE article_references SET triage_decision='ACCEPT', updated_at=? "
            "WHERE reference_id=?",
            (now, reference_id),
        )
        conn.execute(
            """
            INSERT INTO lifecycle_transitions
              (reference_id, run_id, from_stage, to_stage, reason, created_by)
            VALUES (?, ?, 'quarantined', 'triage_complete', ?, 'quarantine_restore')
            """,
            (reference_id, run_id, reviewer_note),
        )
        conn.commit()
    finally:
        conn.close()

    # Move artifact back if it's in the quarantined sub-directory
    quarantine_dir = outbox_dir / "quarantined"
    quarantined_artifact = quarantine_dir / f"{reference_id}.json"
    if quarantined_artifact.exists():
        shutil.move(str(quarantined_artifact), str(outbox_dir / quarantined_artifact.name))
