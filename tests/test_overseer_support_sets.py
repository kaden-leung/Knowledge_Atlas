"""Tests for overseer.support_sets."""

from __future__ import annotations

import json

from overseer.artefact_registry import register
from overseer.support_sets import (
    capture,
    compute_support_set_hash,
    get_hash,
    get_members,
)


def _register_three(conn):
    a = register(conn, kind="pnu_row", entity_type="pnu", entity_id="PNU-A",
                 field_path=None, schema_version="pnu_row.v1")
    b = register(conn, kind="pnu_row", entity_type="pnu", entity_id="PNU-B",
                 field_path=None, schema_version="pnu_row.v1")
    c = register(conn, kind="pnu_row", entity_type="pnu", entity_id="PNU-C",
                 field_path=None, schema_version="pnu_row.v1")
    return a.artefact_id, b.artefact_id, c.artefact_id


def test_compute_support_set_hash_is_deterministic():
    members = [("a", "h1"), ("b", "h2"), ("c", "h3")]
    assert compute_support_set_hash(members) == compute_support_set_hash(members)


def test_compute_support_set_hash_is_order_independent():
    a = [("a", "h1"), ("b", "h2"), ("c", "h3")]
    b = [("c", "h3"), ("a", "h1"), ("b", "h2")]
    assert compute_support_set_hash(a) == compute_support_set_hash(b)


def test_compute_support_set_hash_changes_when_a_member_hash_changes():
    a = [("a", "h1"), ("b", "h2")]
    b = [("a", "h1"), ("b", "h2_DIFFERENT")]
    assert compute_support_set_hash(a) != compute_support_set_hash(b)


def test_capture_inserts_support_set_and_members(overseer_db):
    a, b, c = _register_three(overseer_db)
    ssid = capture(overseer_db, [(a, "ha"), (b, "hb"), (c, "hc")])
    members = get_members(overseer_db, ssid)
    assert sorted(m[0] for m in members) == sorted([a, b, c])


def test_capture_is_idempotent_on_member_identity(overseer_db):
    a, b, c = _register_three(overseer_db)
    ssid1 = capture(overseer_db, [(a, "ha"), (b, "hb"), (c, "hc")])
    ssid2 = capture(overseer_db, [(c, "hc"), (a, "ha"), (b, "hb")])  # diff order
    assert ssid1 == ssid2
    n = overseer_db.execute("SELECT COUNT(*) FROM support_sets").fetchone()[0]
    assert n == 1


def test_capture_distinguishes_different_member_hashes(overseer_db):
    a, b, c = _register_three(overseer_db)
    ssid1 = capture(overseer_db, [(a, "ha"), (b, "hb")])
    ssid2 = capture(overseer_db, [(a, "ha_DIFFERENT"), (b, "hb")])
    assert ssid1 != ssid2


def test_get_hash_returns_support_set_hash(overseer_db):
    a, b, c = _register_three(overseer_db)
    ssid = capture(overseer_db, [(a, "ha"), (b, "hb")])
    h = get_hash(overseer_db, ssid)
    assert h is not None and h.startswith("sha256:")
    assert h == compute_support_set_hash([(a, "ha"), (b, "hb")])


def test_members_json_is_sorted_and_parseable(overseer_db):
    a, b, c = _register_three(overseer_db)
    ssid = capture(overseer_db, [(c, "hc"), (a, "ha"), (b, "hb")])
    row = overseer_db.execute(
        "SELECT members_json FROM support_sets WHERE support_set_id = ?",
        (ssid,),
    ).fetchone()
    payload = json.loads(row[0])
    artefact_ids = [m["artefact_id"] for m in payload]
    assert artefact_ids == sorted(artefact_ids)
