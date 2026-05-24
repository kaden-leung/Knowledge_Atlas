"""Tests for overseer.last_mile_checks."""

from __future__ import annotations

import pytest

from overseer.artefact_registry import register
from overseer.last_mile_checks import (
    ALLOWED_KINDS,
    ALLOWED_STATUSES,
    has_recent_failures,
    most_recent_per_artefact_and_kind,
    record,
)


def _aid(conn):
    return register(conn, kind="article_detail_json", entity_type="paper",
                    entity_id="PDF-0007", field_path=None,
                    schema_version="article_detail.v1").artefact_id


def test_record_inserts_row_and_returns_check_id(overseer_db):
    aid = _aid(overseer_db)
    cid = record(overseer_db, artefact_id=aid, check_kind="http_200",
                 status="pass", evidence={"url": "/ka_article_view.html"})
    assert cid.startswith("chk:")
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM last_mile_production_checks WHERE check_id = ?", (cid,)
    ).fetchone()[0]
    assert n == 1


def test_record_rejects_invalid_check_kind(overseer_db):
    aid = _aid(overseer_db)
    with pytest.raises(ValueError):
        record(overseer_db, artefact_id=aid, check_kind="bad_kind", status="pass")


def test_record_rejects_invalid_status(overseer_db):
    aid = _aid(overseer_db)
    with pytest.raises(ValueError):
        record(overseer_db, artefact_id=aid, check_kind="http_200", status="ok")


def test_most_recent_per_artefact_and_kind_picks_latest(overseer_db):
    aid = _aid(overseer_db)
    c1 = record(overseer_db, artefact_id=aid, check_kind="http_200", status="fail")
    overseer_db.execute(
        "UPDATE last_mile_production_checks SET created_at = '2020-01-01T00:00:00Z' WHERE check_id = ?",
        (c1,),
    )
    c2 = record(overseer_db, artefact_id=aid, check_kind="http_200", status="pass")
    recent = most_recent_per_artefact_and_kind(overseer_db)
    assert recent[(aid, "http_200")].check_id == c2
    assert recent[(aid, "http_200")].status == "pass"


def test_has_recent_failures_picks_failures_within_window(overseer_db):
    aid = _aid(overseer_db)
    record(overseer_db, artefact_id=aid, check_kind="http_200", status="fail")
    assert has_recent_failures(overseer_db, within_seconds=3600) is True


def test_has_recent_failures_skips_old_failures(overseer_db):
    aid = _aid(overseer_db)
    cid = record(overseer_db, artefact_id=aid, check_kind="http_200", status="fail")
    overseer_db.execute(
        "UPDATE last_mile_production_checks SET created_at = '2020-01-01T00:00:00Z' WHERE check_id = ?",
        (cid,),
    )
    assert has_recent_failures(overseer_db, within_seconds=3600) is False


def test_allowed_kinds_and_statuses_match_schema():
    assert set(ALLOWED_KINDS) == {
        "http_200", "asset_200", "no_console_error",
        "payload_hash_equal", "mobile_layout", "provenance_visible",
    }
    assert set(ALLOWED_STATUSES) == {"pass", "fail", "skipped"}
