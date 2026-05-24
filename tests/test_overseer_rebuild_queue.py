"""Tests for overseer.rebuild_queue."""

from __future__ import annotations

import pytest

from overseer.artefact_registry import register
from overseer.rebuild_queue import (
    ALLOWED_SEVERITIES,
    MAX_ATTEMPTS_BEFORE_QUARANTINE,
    Claim,
    claim_one,
    complete,
    enqueue,
    fail,
    heartbeat,
    oldest_queued_age_seconds,
    queue_depth,
)


def _register(conn, entity_id="PNU-Q1"):
    a = register(conn, kind="pnu_row", entity_type="pnu", entity_id=entity_id,
                 field_path=None, schema_version="pnu_row.v1")
    return a.artefact_id


def test_enqueue_inserts_queued_row(overseer_db):
    aid = _register(overseer_db)
    qid = enqueue(overseer_db, artefact_id=aid, reason="test", severity="medium")
    assert qid.startswith("q:")
    state = overseer_db.execute(
        "SELECT state FROM rebuild_queue WHERE queue_id = ?", (qid,)
    ).fetchone()[0]
    assert state == "queued"


def test_enqueue_is_idempotent_when_active_item_exists(overseer_db):
    aid = _register(overseer_db)
    qid1 = enqueue(overseer_db, artefact_id=aid, reason="r1")
    qid2 = enqueue(overseer_db, artefact_id=aid, reason="r2")
    assert qid1 == qid2
    n = overseer_db.execute("SELECT COUNT(*) FROM rebuild_queue").fetchone()[0]
    assert n == 1


def test_enqueue_with_invalid_severity_raises(overseer_db):
    aid = _register(overseer_db)
    with pytest.raises(ValueError):
        enqueue(overseer_db, artefact_id=aid, reason="x", severity="catastrophic")


def test_claim_one_returns_none_when_queue_empty(overseer_db):
    assert claim_one(overseer_db, worker_id="w1") is None


def test_claim_one_increments_fencing_token(overseer_db):
    aid = _register(overseer_db)
    enqueue(overseer_db, artefact_id=aid, reason="r")
    claim = claim_one(overseer_db, worker_id="w1")
    assert isinstance(claim, Claim)
    assert claim.fencing_token == 1
    token = overseer_db.execute(
        "SELECT current_fencing_token FROM artefact_registry WHERE artefact_id = ?",
        (aid,),
    ).fetchone()[0]
    assert token == 1


def test_claim_one_writes_lease_owner_and_worker_heartbeat(overseer_db):
    aid = _register(overseer_db)
    enqueue(overseer_db, artefact_id=aid, reason="r")
    claim = claim_one(overseer_db, worker_id="w1", input_fingerprint="fp:abc")
    row = overseer_db.execute(
        "SELECT lease_owner, fencing_token, input_fingerprint_at_claim, claimed_at, state "
        "FROM rebuild_queue WHERE queue_id = ?", (claim.queue_id,)
    ).fetchone()
    assert row[0] == "w1"
    assert row[1] == claim.fencing_token
    assert row[2] == "fp:abc"
    assert row[3] is not None
    assert row[4] == "claimed"
    hb = overseer_db.execute(
        "SELECT current_claim, heartbeat_timeout_seconds FROM worker_heartbeats WHERE worker_id = ?",
        ("w1",),
    ).fetchone()
    assert hb[0] == claim.queue_id
    assert hb[1] == 300


def test_claim_one_orders_by_severity_then_first_seen(overseer_db):
    a1 = _register(overseer_db, "PNU-A")
    a2 = _register(overseer_db, "PNU-B")
    a3 = _register(overseer_db, "PNU-C")
    # Enqueue in priority order: medium first, then blocking, then high.
    enqueue(overseer_db, artefact_id=a1, reason="r1", severity="medium")
    enqueue(overseer_db, artefact_id=a2, reason="r2", severity="blocking")
    enqueue(overseer_db, artefact_id=a3, reason="r3", severity="high")
    # First claim should grab the blocking item.
    c1 = claim_one(overseer_db, worker_id="w1")
    assert c1.severity == "blocking"
    c2 = claim_one(overseer_db, worker_id="w2")
    assert c2.severity == "high"
    c3 = claim_one(overseer_db, worker_id="w3")
    assert c3.severity == "medium"


def test_heartbeat_updates_last_heartbeat_at(overseer_db):
    aid = _register(overseer_db)
    enqueue(overseer_db, artefact_id=aid, reason="r")
    claim_one(overseer_db, worker_id="w1")
    before = overseer_db.execute(
        "SELECT last_heartbeat_at FROM worker_heartbeats WHERE worker_id = ?", ("w1",)
    ).fetchone()[0]
    # Force a different timestamp by direct UPDATE (simulate older heartbeat).
    overseer_db.execute(
        "UPDATE worker_heartbeats SET last_heartbeat_at = '2020-01-01T00:00:00Z' WHERE worker_id = ?",
        ("w1",),
    )
    heartbeat(overseer_db, worker_id="w1")
    after = overseer_db.execute(
        "SELECT last_heartbeat_at FROM worker_heartbeats WHERE worker_id = ?", ("w1",)
    ).fetchone()[0]
    assert after != "2020-01-01T00:00:00Z"


def test_heartbeat_records_progress_marker_change(overseer_db):
    aid = _register(overseer_db)
    enqueue(overseer_db, artefact_id=aid, reason="r")
    claim_one(overseer_db, worker_id="w1")
    heartbeat(overseer_db, worker_id="w1", progress_marker="phase=hash:0")
    heartbeat(overseer_db, worker_id="w1", progress_marker="phase=hash:0")  # unchanged
    heartbeat(overseer_db, worker_id="w1", progress_marker="phase=write:1")  # changed
    row = overseer_db.execute(
        "SELECT progress_marker, progress_marker_unchanged_since FROM worker_heartbeats WHERE worker_id = ?",
        ("w1",),
    ).fetchone()
    assert row[0] == "phase=write:1"
    assert row[1] is not None


def test_complete_marks_state_done_and_clears_claim(overseer_db):
    aid = _register(overseer_db)
    enqueue(overseer_db, artefact_id=aid, reason="r")
    claim = claim_one(overseer_db, worker_id="w1")
    complete(overseer_db, claim, worker_id="w1")
    state = overseer_db.execute(
        "SELECT state FROM rebuild_queue WHERE queue_id = ?", (claim.queue_id,)
    ).fetchone()[0]
    assert state == "done"
    cc = overseer_db.execute(
        "SELECT current_claim FROM worker_heartbeats WHERE worker_id = ?", ("w1",)
    ).fetchone()[0]
    assert cc is None


def test_fail_increments_attempt_and_requeues(overseer_db):
    aid = _register(overseer_db)
    enqueue(overseer_db, artefact_id=aid, reason="r")
    claim = claim_one(overseer_db, worker_id="w1")
    new_state = fail(overseer_db, claim, worker_id="w1", error="boom")
    assert new_state == "queued"
    state, attempts = overseer_db.execute(
        "SELECT state, attempt_count FROM rebuild_queue WHERE queue_id = ?", (claim.queue_id,)
    ).fetchone()
    assert state == "queued"
    assert attempts == 1


def test_fail_quarantines_after_threshold(overseer_db):
    aid = _register(overseer_db)
    enqueue(overseer_db, artefact_id=aid, reason="r")
    for _ in range(MAX_ATTEMPTS_BEFORE_QUARANTINE):
        claim = claim_one(overseer_db, worker_id="w1")
        assert claim is not None
        new_state = fail(overseer_db, claim, worker_id="w1", error="boom")
    assert new_state == "quarantine"


def test_queue_depth_groups_by_state(overseer_db):
    a1 = _register(overseer_db, "PNU-D1")
    a2 = _register(overseer_db, "PNU-D2")
    enqueue(overseer_db, artefact_id=a1, reason="r1")
    enqueue(overseer_db, artefact_id=a2, reason="r2")
    claim_one(overseer_db, worker_id="w1")
    depth = queue_depth(overseer_db)
    assert depth.get("queued", 0) == 1
    assert depth.get("claimed", 0) == 1


def test_oldest_queued_age_seconds_is_nonneg_when_queue_has_items(overseer_db):
    aid = _register(overseer_db)
    enqueue(overseer_db, artefact_id=aid, reason="r")
    age = oldest_queued_age_seconds(overseer_db)
    assert age is not None and age >= 0


def test_oldest_queued_age_seconds_none_when_empty(overseer_db):
    assert oldest_queued_age_seconds(overseer_db) is None


def test_allowed_severities_matches_schema():
    assert ALLOWED_SEVERITIES == ("low", "medium", "high", "blocking")
