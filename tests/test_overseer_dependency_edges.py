"""Tests for overseer.dependency_edges."""

from __future__ import annotations

import pytest

from overseer.artefact_registry import register
from overseer.dependency_edges import (
    ALLOWED_EDGE_KINDS,
    add_edge,
    children_of,
    parents_of,
    tombstone_edge,
)


def _register_pair(conn):
    p = register(conn, kind="pnu_row", entity_type="pnu", entity_id="PNU-P",
                 field_path=None, schema_version="pnu_row.v1")
    c = register(conn, kind="article_epistemic_record", entity_type="paper",
                 entity_id="PDF-0007", field_path=None,
                 schema_version="article_epistemic_layer.v1")
    return p.artefact_id, c.artefact_id


def test_add_edge_inserts_active_row(overseer_db):
    p, c = _register_pair(overseer_db)
    add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
             edge_kind="supports")
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM dependency_edges WHERE tombstoned_at IS NULL"
    ).fetchone()[0]
    assert n == 1


def test_add_edge_with_invalid_kind_raises(overseer_db):
    p, c = _register_pair(overseer_db)
    with pytest.raises(ValueError):
        add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
                 edge_kind="not_an_edge_kind")


def test_add_edge_requires_both_endpoints_to_exist(overseer_db):
    # FK constraint: endpoint must be in artefact_registry.
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        add_edge(overseer_db,
                 parent_artefact_id="ghost_parent",
                 child_artefact_id="ghost_child",
                 edge_kind="supports")


def test_add_edge_is_idempotent_on_pk(overseer_db):
    p, c = _register_pair(overseer_db)
    add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
             edge_kind="supports")
    add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
             edge_kind="supports")
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM dependency_edges"
    ).fetchone()[0]
    assert n == 1


def test_tombstone_edge_sets_tombstoned_at_and_drops_from_active_queries(overseer_db):
    p, c = _register_pair(overseer_db)
    add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
             edge_kind="supports")
    tombstone_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
                   edge_kind="supports")
    assert parents_of(overseer_db, c) == []
    # Row still present for audit:
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM dependency_edges WHERE tombstoned_at IS NOT NULL"
    ).fetchone()[0]
    assert n == 1


def test_add_edge_reactivates_tombstoned_row(overseer_db):
    p, c = _register_pair(overseer_db)
    add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
             edge_kind="supports")
    tombstone_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
                   edge_kind="supports")
    add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
             edge_kind="supports")
    assert parents_of(overseer_db, c) == [p]


def test_parents_of_and_children_of_filter_by_kind(overseer_db):
    p, c = _register_pair(overseer_db)
    add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
             edge_kind="supports")
    add_edge(overseer_db, parent_artefact_id=p, child_artefact_id=c,
             edge_kind="grounds")
    # Unfiltered returns one row per edge_kind (no SQL distinct).
    assert parents_of(overseer_db, c) == [p, p]
    # Filtered returns one row per matching kind.
    assert parents_of(overseer_db, c, edge_kind="supports") == [p]
    assert parents_of(overseer_db, c, edge_kind="grounds") == [p]
    assert children_of(overseer_db, p, edge_kind="supports") == [c]


def test_allowed_edge_kinds_matches_schema(overseer_db):
    # The CHECK in DDL must match ALLOWED_EDGE_KINDS in code.
    assert ALLOWED_EDGE_KINDS == {"supports", "derived_from", "depends_on", "grounds"}
