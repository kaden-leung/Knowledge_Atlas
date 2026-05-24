"""Tests for overseer.abstract_provenance."""

from __future__ import annotations

import pytest

from overseer.abstract_provenance import (
    ABSTRACT_SOURCE_KIND,
    UnknownAbstractSourceError,
    canonical_source,
    is_allowed_source,
    list_allowed_sources,
    require_allowed_source,
)


def _seed_canonical(conn, value):
    import hashlib
    h = hashlib.sha256(f"{ABSTRACT_SOURCE_KIND}\x1f{value}".encode()).hexdigest()[:16]
    vid = f"vocab:{ABSTRACT_SOURCE_KIND}:{h}"
    conn.execute(
        """
        INSERT OR IGNORE INTO vocabulary_registry (
            value_id, kind, value, canonical_value, first_observed_at,
            review_status, seeded_from
        ) VALUES (?, ?, ?, NULL, '2026-05-23T00:00:00Z', 'canonical', 'test')
        """,
        (vid, ABSTRACT_SOURCE_KIND, value),
    )


def _seed_synonym(conn, value, canonical_value):
    import hashlib
    h = hashlib.sha256(f"{ABSTRACT_SOURCE_KIND}\x1f{value}".encode()).hexdigest()[:16]
    vid = f"vocab:{ABSTRACT_SOURCE_KIND}:{h}"
    conn.execute(
        """
        INSERT INTO vocabulary_registry (
            value_id, kind, value, canonical_value, first_observed_at,
            review_status, canonicalization_source
        ) VALUES (?, ?, ?, ?, '2026-05-23T00:00:00Z', 'synonym', 'test')
        """,
        (vid, ABSTRACT_SOURCE_KIND, value, canonical_value),
    )


def test_is_allowed_source_recognizes_canonical(overseer_db):
    _seed_canonical(overseer_db, "crossref")
    assert is_allowed_source(overseer_db, "crossref") is True


def test_is_allowed_source_recognizes_synonym(overseer_db):
    _seed_canonical(overseer_db, "openalex")
    _seed_synonym(overseer_db, "OpenAlex API", "openalex")
    assert is_allowed_source(overseer_db, "OpenAlex API") is True


def test_is_allowed_source_rejects_unknown(overseer_db):
    assert is_allowed_source(overseer_db, "ghost_source") is False


def test_is_allowed_source_rejects_empty(overseer_db):
    assert is_allowed_source(overseer_db, "") is False


def test_canonical_source_returns_value_for_canonical(overseer_db):
    _seed_canonical(overseer_db, "manual")
    assert canonical_source(overseer_db, "manual") == "manual"


def test_canonical_source_resolves_synonym_to_target(overseer_db):
    _seed_canonical(overseer_db, "crossref")
    _seed_synonym(overseer_db, "CrossRef", "crossref")
    assert canonical_source(overseer_db, "CrossRef") == "crossref"


def test_canonical_source_returns_none_for_unknown(overseer_db):
    assert canonical_source(overseer_db, "no_such_source") is None


def test_require_allowed_source_raises_on_unknown(overseer_db):
    with pytest.raises(UnknownAbstractSourceError):
        require_allowed_source(overseer_db, "fake_source")


def test_require_allowed_source_returns_canonical_for_synonym(overseer_db):
    _seed_canonical(overseer_db, "openalex")
    _seed_synonym(overseer_db, "Open Alex", "openalex")
    assert require_allowed_source(overseer_db, "Open Alex") == "openalex"


def test_list_allowed_sources_orders_alphabetically(overseer_db):
    _seed_canonical(overseer_db, "publisher_metadata")
    _seed_canonical(overseer_db, "crossref")
    _seed_canonical(overseer_db, "manual")
    out = list_allowed_sources(overseer_db)
    assert out == sorted(out)
    assert set(out) >= {"crossref", "manual", "publisher_metadata"}
