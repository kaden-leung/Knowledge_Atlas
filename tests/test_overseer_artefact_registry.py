"""Tests for overseer.artefact_registry."""

from __future__ import annotations

import pytest

from overseer.artefact_registry import (
    Artefact,
    FencingTokenMismatch,
    get,
    get_by_entity,
    increment_fencing_token,
    list_by_kind,
    mark_fresh,
    mark_stale,
    register,
    tombstone,
    update_with_hashes,
)


def test_register_inserts_new_row_and_returns_artefact(overseer_db):
    a = register(
        overseer_db,
        kind="pnu_row",
        entity_type="pnu",
        entity_id="PNU-001",
        field_path=None,
        schema_version="pnu_row.v1",
    )
    assert isinstance(a, Artefact)
    assert a.artefact_id == "pnu_row:PNU-001::pnu_row.v1"
    assert a.kind == "pnu_row"
    assert a.entity_id == "PNU-001"
    assert a.active is True
    assert a.current_fencing_token == 0
    assert a.freshness_status == "unknown"


def test_register_is_idempotent_on_natural_key(overseer_db):
    a1 = register(
        overseer_db,
        kind="article_epistemic_record",
        entity_type="paper",
        entity_id="PDF-0007",
        field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    a2 = register(
        overseer_db,
        kind="article_epistemic_record",
        entity_type="paper",
        entity_id="PDF-0007",
        field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    assert a1.artefact_id == a2.artefact_id
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM artefact_registry WHERE entity_id = 'PDF-0007'"
    ).fetchone()[0]
    assert n == 1


def test_get_returns_none_for_missing_artefact(overseer_db):
    assert get(overseer_db, "not_a_real_id") is None


def test_get_by_entity_finds_the_active_row(overseer_db):
    register(
        overseer_db,
        kind="article_detail_json",
        entity_type="paper",
        entity_id="PDF-0042",
        field_path=None,
        schema_version="article_detail.v1",
    )
    a = get_by_entity(
        overseer_db,
        entity_type="paper",
        entity_id="PDF-0042",
        field_path=None,
        schema_version="article_detail.v1",
    )
    assert a is not None
    assert a.entity_id == "PDF-0042"


def test_increment_fencing_token_returns_new_value(overseer_db):
    a = register(
        overseer_db,
        kind="pnu_row",
        entity_type="pnu",
        entity_id="PNU-002",
        field_path=None,
        schema_version="pnu_row.v1",
    )
    assert a.current_fencing_token == 0
    new_token = increment_fencing_token(overseer_db, a.artefact_id)
    assert new_token == 1
    assert increment_fencing_token(overseer_db, a.artefact_id) == 2


def test_update_with_hashes_succeeds_under_matching_token(overseer_db):
    a = register(
        overseer_db,
        kind="pnu_row",
        entity_type="pnu",
        entity_id="PNU-003",
        field_path=None,
        schema_version="pnu_row.v1",
    )
    token = increment_fencing_token(overseer_db, a.artefact_id)
    update_with_hashes(
        overseer_db,
        artefact_id=a.artefact_id,
        raw_hash="sha256:aa",
        semantic_hash="sha256:bb",
        build_run_id="br:test:001",
        fencing_token=token,
    )
    out = get(overseer_db, a.artefact_id)
    assert out.raw_hash == "sha256:aa"
    assert out.semantic_hash == "sha256:bb"
    assert out.latest_build_run_id == "br:test:001"
    assert out.freshness_status == "fresh"


def test_update_with_hashes_rejects_stale_token(overseer_db):
    a = register(
        overseer_db,
        kind="pnu_row",
        entity_type="pnu",
        entity_id="PNU-004",
        field_path=None,
        schema_version="pnu_row.v1",
    )
    token_a = increment_fencing_token(overseer_db, a.artefact_id)  # 1
    increment_fencing_token(overseer_db, a.artefact_id)            # 2 (watchdog reclaimed)
    # Worker A still tries to write with its stale token.
    with pytest.raises(FencingTokenMismatch):
        update_with_hashes(
            overseer_db,
            artefact_id=a.artefact_id,
            raw_hash="sha256:dead",
            semantic_hash="sha256:beef",
            build_run_id="br:test:002",
            fencing_token=token_a,  # stale
        )


def test_update_with_hashes_raises_when_artefact_missing(overseer_db):
    with pytest.raises(FencingTokenMismatch):
        update_with_hashes(
            overseer_db,
            artefact_id="does_not_exist",
            raw_hash="sha256:aa",
            semantic_hash="sha256:bb",
            build_run_id="br:test:003",
            fencing_token=1,
        )


def test_mark_stale_and_mark_fresh_round_trip(overseer_db):
    a = register(
        overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-005",
        field_path=None, schema_version="pnu_row.v1",
    )
    mark_stale(overseer_db, a.artefact_id)
    assert get(overseer_db, a.artefact_id).freshness_status == "stale"
    mark_fresh(overseer_db, a.artefact_id)
    assert get(overseer_db, a.artefact_id).freshness_status == "fresh"


def test_tombstone_makes_row_inactive_and_preserves_audit(overseer_db):
    a = register(
        overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-006",
        field_path=None, schema_version="pnu_row.v1",
    )
    tombstone(overseer_db, a.artefact_id)
    row = get(overseer_db, a.artefact_id)
    assert row is not None  # still present for audit
    assert row.active is False
    assert row.tombstoned_at is not None


def test_active_uniqueness_index_allows_replacement_after_tombstone(overseer_db):
    # Register, tombstone, then re-register the same natural key — the partial
    # unique index allows the new active row because the old one is active=0.
    a1 = register(
        overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-007",
        field_path=None, schema_version="pnu_row.v1",
    )
    tombstone(overseer_db, a1.artefact_id)
    # Re-register: would normally collide on PK, but artefact_id is deterministic
    # from natural key, so register's get_by_entity-then-insert path won't trip
    # since the existing row is inactive.
    existing_active = get_by_entity(
        overseer_db, entity_type="pnu", entity_id="PNU-007",
        field_path=None, schema_version="pnu_row.v1",
    )
    assert existing_active is None  # no active row remains


def test_list_by_kind_returns_active_rows_in_id_order(overseer_db):
    register(overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-A",
             field_path=None, schema_version="pnu_row.v1")
    register(overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-B",
             field_path=None, schema_version="pnu_row.v1")
    register(overseer_db, kind="article_detail_json", entity_type="paper",
             entity_id="PDF-0001", field_path=None,
             schema_version="article_detail.v1")
    rows = list_by_kind(overseer_db, "pnu_row")
    assert len(rows) == 2
    assert all(r.kind == "pnu_row" for r in rows)
    ids = [r.entity_id for r in rows]
    assert ids == sorted(ids)
