"""Tests for overseer.build_runs."""

from __future__ import annotations

import json

import pytest

from overseer.build_runs import ALLOWED_STATUSES, finish, get, start


def test_start_inserts_running_row(overseer_db):
    brid = start(overseer_db, builder_name="article_epistemic_builder",
                 builder_version="v1", input_snapshot_hash="sha256:abc")
    assert brid.startswith("br:")
    run = get(overseer_db, brid)
    assert run is not None
    assert run.status == "running"
    assert run.builder_name == "article_epistemic_builder"
    assert run.builder_version == "v1"
    assert run.input_snapshot_hash == "sha256:abc"
    assert run.finished_at is None


def test_finish_with_verified_status_closes_run(overseer_db):
    brid = start(overseer_db, builder_name="b", builder_version="v1")
    finish(overseer_db, build_run_id=brid, status="verified",
           record_count=10, success_count=10, failure_count=0,
           report={"note": "all good"})
    run = get(overseer_db, brid)
    assert run.status == "verified"
    assert run.record_count == 10
    assert run.success_count == 10
    assert run.failure_count == 0
    assert run.finished_at is not None
    assert json.loads(run.report_json) == {"note": "all good"}


def test_finish_rejects_invalid_status(overseer_db):
    brid = start(overseer_db, builder_name="b", builder_version="v1")
    with pytest.raises(ValueError):
        finish(overseer_db, build_run_id=brid, status="catastrophe")


def test_get_returns_none_for_missing_id(overseer_db):
    assert get(overseer_db, "br:not_real") is None


def test_allowed_statuses_matches_schema():
    assert set(ALLOWED_STATUSES) == {"running", "verified", "failed", "aborted", "rehash"}
