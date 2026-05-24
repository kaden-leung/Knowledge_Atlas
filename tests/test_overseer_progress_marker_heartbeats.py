"""Tests for P25 soft-stuck progress-marker detection (overseer.watchdog)."""

from __future__ import annotations

from overseer.artefact_registry import register
from overseer.rebuild_queue import claim_one, enqueue, heartbeat
from overseer.watchdog import (
    SOFT_STUCK_INTERVAL_MULTIPLIER,
    SoftStuckFlag,
    soft_stuck_tick,
    tick,
)


def _register_and_claim(conn, entity_id="PNU-SS", interval=30, timeout=300):
    a = register(conn, kind="pnu_row", entity_type="pnu", entity_id=entity_id,
                 field_path=None, schema_version="pnu_row.v1")
    enqueue(conn, artefact_id=a.artefact_id, reason="r")
    return claim_one(conn, worker_id="w1",
                     heartbeat_interval_seconds=interval,
                     heartbeat_timeout_seconds=timeout)


def _backdate_progress_marker(conn, worker_id, seconds_ago):
    conn.execute(
        "UPDATE worker_heartbeats SET progress_marker_unchanged_since = "
        "datetime('now', ?) WHERE worker_id = ?",
        (f"-{seconds_ago} seconds", worker_id),
    )


def test_soft_stuck_tick_returns_empty_when_no_workers(overseer_db):
    assert soft_stuck_tick(overseer_db) == []


def test_soft_stuck_tick_ignores_workers_without_progress_marker(overseer_db):
    _register_and_claim(overseer_db)
    # No progress_marker set yet → soft-stuck cannot fire.
    assert soft_stuck_tick(overseer_db) == []


def test_soft_stuck_tick_ignores_recent_unchanged_marker(overseer_db):
    _register_and_claim(overseer_db, interval=30, timeout=300)
    heartbeat(overseer_db, worker_id="w1", progress_marker="phase=x")
    # Marker was just set; not yet stuck.
    assert soft_stuck_tick(overseer_db) == []


def test_soft_stuck_tick_flags_marker_unchanged_past_threshold(overseer_db):
    claim = _register_and_claim(overseer_db, interval=30, timeout=300)
    heartbeat(overseer_db, worker_id="w1", progress_marker="phase=x")
    # Backdate marker_unchanged_since to past the soft-stuck threshold
    # (5 * 30s = 150s).
    _backdate_progress_marker(overseer_db, "w1", seconds_ago=200)
    flags = soft_stuck_tick(overseer_db)
    assert len(flags) == 1
    assert isinstance(flags[0], SoftStuckFlag)
    assert flags[0].worker_id == "w1"
    assert flags[0].progress_marker == "phase=x"
    # A medium-severity completion_queue row exists.
    cq = overseer_db.execute(
        "SELECT severity, reason, artefact_id FROM completion_queue WHERE queue_id = ?",
        (flags[0].completion_queue_id,),
    ).fetchone()
    assert cq["severity"] == "medium"
    assert "soft_stuck_progress_marker" in cq["reason"]
    assert cq["artefact_id"] == claim.artefact_id


def test_soft_stuck_does_not_kill_or_reclaim_worker(overseer_db):
    claim = _register_and_claim(overseer_db)
    heartbeat(overseer_db, worker_id="w1", progress_marker="phase=x")
    _backdate_progress_marker(overseer_db, "w1", seconds_ago=200)
    soft_stuck_tick(overseer_db)
    # Worker heartbeat row still exists; queue row still claimed; not killed.
    hb = overseer_db.execute(
        "SELECT COUNT(*) FROM worker_heartbeats WHERE worker_id = 'w1'"
    ).fetchone()[0]
    assert hb == 1
    state = overseer_db.execute(
        "SELECT state FROM rebuild_queue WHERE queue_id = ?", (claim.queue_id,)
    ).fetchone()[0]
    assert state == "claimed"


def test_soft_stuck_is_idempotent_under_unchanged_marker(overseer_db):
    _register_and_claim(overseer_db)
    heartbeat(overseer_db, worker_id="w1", progress_marker="phase=x")
    _backdate_progress_marker(overseer_db, "w1", seconds_ago=200)
    flags1 = soft_stuck_tick(overseer_db)
    flags2 = soft_stuck_tick(overseer_db)
    # Same completion_queue row reused (idempotent enqueue on artefact+reason).
    assert len(flags1) == 1 and len(flags2) == 1
    assert flags1[0].completion_queue_id == flags2[0].completion_queue_id


def test_soft_stuck_skips_dead_worker(overseer_db):
    # A worker whose heartbeat itself is stale belongs to the liveness reclaim
    # path (tick()), not soft_stuck_tick. soft_stuck_tick must ignore it.
    _register_and_claim(overseer_db, interval=30, timeout=60)
    heartbeat(overseer_db, worker_id="w1", progress_marker="phase=x")
    # Backdate BOTH heartbeat and marker — heartbeat is stale.
    overseer_db.execute(
        "UPDATE worker_heartbeats SET "
        "last_heartbeat_at = datetime('now', '-600 seconds'), "
        "progress_marker_unchanged_since = datetime('now', '-600 seconds') "
        "WHERE worker_id = 'w1'"
    )
    flags = soft_stuck_tick(overseer_db)
    assert flags == []  # liveness reclaim handles this case


def test_soft_stuck_multiplier_constant():
    assert SOFT_STUCK_INTERVAL_MULTIPLIER == 5
