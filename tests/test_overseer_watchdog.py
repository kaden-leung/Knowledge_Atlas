"""Tests for overseer.watchdog (heartbeat-based reclaim, P7+P24)."""

from __future__ import annotations

from overseer.artefact_registry import register, FencingTokenMismatch
from overseer.rebuild_queue import claim_one, enqueue
from overseer.watchdog import tick


def _register_and_claim(conn, entity_id="PNU-W", worker_id="w1", timeout=300):
    a = register(conn, kind="pnu_row", entity_type="pnu", entity_id=entity_id,
                 field_path=None, schema_version="pnu_row.v1")
    enqueue(conn, artefact_id=a.artefact_id, reason="r")
    claim = claim_one(conn, worker_id=worker_id, heartbeat_timeout_seconds=timeout)
    return a.artefact_id, claim


def _force_heartbeat_age(conn, worker_id, seconds_ago=600):
    """Backdate the worker's last_heartbeat_at to N seconds ago."""
    conn.execute(
        "UPDATE worker_heartbeats SET last_heartbeat_at = datetime('now', ?) WHERE worker_id = ?",
        (f"-{seconds_ago} seconds", worker_id),
    )


def test_watchdog_does_not_reclaim_fresh_heartbeats(overseer_db):
    _, _ = _register_and_claim(overseer_db, "PNU-FRESH")
    reclaimed = tick(overseer_db)
    assert reclaimed == []


def test_watchdog_reclaims_stale_worker_and_increments_fencing_token(overseer_db):
    aid, claim = _register_and_claim(overseer_db, "PNU-STALE", timeout=60)
    _force_heartbeat_age(overseer_db, "w1", seconds_ago=600)
    reclaimed = tick(overseer_db)
    assert len(reclaimed) == 1
    rc = reclaimed[0]
    assert rc.queue_id == claim.queue_id
    assert rc.artefact_id == aid
    assert rc.worker_id == "w1"
    assert rc.new_fencing_token == claim.fencing_token + 1
    # Queue row is back to 'queued'
    state = overseer_db.execute(
        "SELECT state, lease_owner, last_error FROM rebuild_queue WHERE queue_id = ?",
        (claim.queue_id,),
    ).fetchone()
    assert state[0] == "queued"
    assert state[1] is None
    assert "watchdog_reclaimed" in state[2]
    # Worker heartbeat row is gone
    hb = overseer_db.execute(
        "SELECT COUNT(*) FROM worker_heartbeats WHERE worker_id = ?", ("w1",)
    ).fetchone()[0]
    assert hb == 0


def test_watchdog_reclaim_invalidates_dead_workers_writes(overseer_db):
    from overseer.artefact_registry import update_with_hashes
    import pytest
    aid, claim = _register_and_claim(overseer_db, "PNU-RACE", timeout=60)
    _force_heartbeat_age(overseer_db, "w1", seconds_ago=600)
    tick(overseer_db)
    # The dead worker tries to commit with its old fencing token. Must reject.
    with pytest.raises(FencingTokenMismatch):
        update_with_hashes(
            overseer_db,
            artefact_id=aid,
            raw_hash="sha256:dead",
            semantic_hash="sha256:beef",
            build_run_id="br:test:001",
            fencing_token=claim.fencing_token,
        )


def test_watchdog_quarantines_after_threshold(overseer_db):
    aid = register(
        overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-QUAR",
        field_path=None, schema_version="pnu_row.v1",
    ).artefact_id
    enqueue(overseer_db, artefact_id=aid, reason="r")
    for i in range(5):
        claim = claim_one(overseer_db, worker_id=f"w{i}", heartbeat_timeout_seconds=60)
        assert claim is not None
        _force_heartbeat_age(overseer_db, f"w{i}", seconds_ago=600)
        tick(overseer_db)
    # After 5 reclaims, attempt_count reaches threshold; state is 'quarantine'.
    row = overseer_db.execute(
        "SELECT state, attempt_count FROM rebuild_queue WHERE artefact_id = ?", (aid,)
    ).fetchone()
    assert row[0] == "quarantine"
    assert row[1] >= 5
    # A completion_queue row with severity='high' was created.
    cq = overseer_db.execute(
        "SELECT severity, reason FROM completion_queue WHERE artefact_id = ?", (aid,)
    ).fetchone()
    assert cq is not None
    assert cq[0] == "high"
    assert "quarantine" in cq[1]


def test_watchdog_handles_worker_with_no_active_claim(overseer_db):
    # A worker heartbeat with current_claim=NULL (idle worker who went silent).
    _register_and_claim(overseer_db, "PNU-X", timeout=60)
    # Force the worker into idle-and-stale state.
    overseer_db.execute(
        "UPDATE worker_heartbeats SET current_claim = NULL WHERE worker_id = 'w1'"
    )
    _force_heartbeat_age(overseer_db, "w1", seconds_ago=600)
    reclaimed = tick(overseer_db)
    # No claim was active, so nothing to reclaim — but the worker row gets deleted.
    assert reclaimed == []
    hb = overseer_db.execute(
        "SELECT COUNT(*) FROM worker_heartbeats WHERE worker_id = 'w1'"
    ).fetchone()[0]
    assert hb == 0
