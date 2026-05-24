"""Tests for overseer.completion_queue."""

from __future__ import annotations

import pytest

from overseer.artefact_registry import register
from overseer.completion_queue import (
    ALLOWED_SEVERITIES,
    enqueue,
    has_blocking_open,
    list_open,
    mark_in_review,
    resolve,
    waive,
)


def _aid(conn, entity_id="PNU-1"):
    return register(conn, kind="pnu_row", entity_type="pnu", entity_id=entity_id,
                    field_path=None, schema_version="pnu_row.v1").artefact_id


def test_enqueue_inserts_open_item(overseer_db):
    aid = _aid(overseer_db)
    qid = enqueue(overseer_db, reason="missing_source", severity="blocking",
                  artefact_id=aid, next_action="reextract")
    assert qid.startswith("cq:")
    items = list_open(overseer_db)
    assert len(items) == 1
    assert items[0].reason == "missing_source"
    assert items[0].severity == "blocking"
    assert items[0].next_action == "reextract"
    assert items[0].status == "open"


def test_enqueue_rejects_invalid_severity(overseer_db):
    with pytest.raises(ValueError):
        enqueue(overseer_db, reason="x", severity="catastrophic")


def test_enqueue_is_idempotent_on_artefact_reason_pair(overseer_db):
    aid = _aid(overseer_db)
    qid1 = enqueue(overseer_db, reason="stale", artefact_id=aid)
    qid2 = enqueue(overseer_db, reason="stale", artefact_id=aid)
    assert qid1 == qid2
    n = overseer_db.execute("SELECT COUNT(*) FROM completion_queue").fetchone()[0]
    assert n == 1
    # attempt_count should have incremented.
    attempts = overseer_db.execute(
        "SELECT attempt_count FROM completion_queue WHERE queue_id = ?", (qid1,)
    ).fetchone()[0]
    assert attempts == 1


def test_mark_in_review_assigns(overseer_db):
    aid = _aid(overseer_db)
    qid = enqueue(overseer_db, reason="r", artefact_id=aid)
    mark_in_review(overseer_db, queue_id=qid, assigned_to="reviewer1")
    row = overseer_db.execute(
        "SELECT status, assigned_to FROM completion_queue WHERE queue_id = ?", (qid,)
    ).fetchone()
    assert row[0] == "in_review"
    assert row[1] == "reviewer1"


def test_resolve_closes_item(overseer_db):
    aid = _aid(overseer_db)
    qid = enqueue(overseer_db, reason="r", artefact_id=aid)
    resolve(overseer_db, queue_id=qid)
    row = overseer_db.execute(
        "SELECT status, resolved_at FROM completion_queue WHERE queue_id = ?", (qid,)
    ).fetchone()
    assert row[0] == "resolved"
    assert row[1] is not None


def test_waive_closes_item_with_reviewer(overseer_db):
    aid = _aid(overseer_db)
    qid = enqueue(overseer_db, reason="r", artefact_id=aid)
    waive(overseer_db, queue_id=qid, assigned_to="reviewer1")
    row = overseer_db.execute(
        "SELECT status, assigned_to FROM completion_queue WHERE queue_id = ?", (qid,)
    ).fetchone()
    assert row[0] == "waived"
    assert row[1] == "reviewer1"


def test_list_open_filters_by_min_severity(overseer_db):
    a1 = _aid(overseer_db, "PNU-L1")
    a2 = _aid(overseer_db, "PNU-L2")
    a3 = _aid(overseer_db, "PNU-L3")
    enqueue(overseer_db, reason="lo", artefact_id=a1, severity="low")
    enqueue(overseer_db, reason="hi", artefact_id=a2, severity="high")
    enqueue(overseer_db, reason="bk", artefact_id=a3, severity="blocking")
    all_items = list_open(overseer_db)
    assert len(all_items) == 3
    high_or_better = list_open(overseer_db, min_severity="high")
    assert len(high_or_better) == 2
    blocking_only = list_open(overseer_db, min_severity="blocking")
    assert len(blocking_only) == 1


def test_has_blocking_open_returns_true_only_for_blocking(overseer_db):
    aid = _aid(overseer_db)
    assert has_blocking_open(overseer_db) is False
    enqueue(overseer_db, reason="r", artefact_id=aid, severity="high")
    assert has_blocking_open(overseer_db) is False
    enqueue(overseer_db, reason="r2", artefact_id=aid, severity="blocking")
    assert has_blocking_open(overseer_db) is True


def test_resolved_items_do_not_block(overseer_db):
    aid = _aid(overseer_db)
    qid = enqueue(overseer_db, reason="r", artefact_id=aid, severity="blocking")
    assert has_blocking_open(overseer_db) is True
    resolve(overseer_db, queue_id=qid)
    assert has_blocking_open(overseer_db) is False


def test_allowed_severities_matches_schema():
    assert ALLOWED_SEVERITIES == ("low", "medium", "high", "blocking")
