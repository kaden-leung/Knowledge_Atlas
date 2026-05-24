"""Tests for the dependency-overseer hash functions.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §12
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P27)
"""

from __future__ import annotations

import re

import pytest

from overseer.content_hashes import (
    compute_input_fingerprint,
    compute_raw_hash,
    compute_semantic_hash,
)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


# --- Shape ------------------------------------------------------------------

def test_raw_hash_is_sha256_prefixed():
    h = compute_raw_hash({"a": 1})
    assert _SHA256_RE.match(h), f"unexpected hash format: {h!r}"


def test_semantic_hash_is_sha256_prefixed():
    h = compute_semantic_hash({"x": 1}, "primary_claim", hints_override={})
    assert _SHA256_RE.match(h), f"unexpected hash format: {h!r}"


def test_input_fingerprint_is_sha256_prefixed():
    h = compute_input_fingerprint([("a", "h1"), ("b", "h2")])
    assert _SHA256_RE.match(h), f"unexpected hash format: {h!r}"


# --- Determinism ------------------------------------------------------------

def test_raw_hash_is_deterministic():
    content = {"a": 1, "b": [2, 3]}
    assert compute_raw_hash(content) == compute_raw_hash(content)


def test_semantic_hash_is_deterministic():
    hints = {"name": {"case_insensitive": True}}
    content = {"name": "alice", "age": 30}
    h1 = compute_semantic_hash(content, "primary_claim", hints_override=hints)
    h2 = compute_semantic_hash(content, "primary_claim", hints_override=hints)
    h3 = compute_semantic_hash(content, "primary_claim", hints_override=hints)
    assert h1 == h2 == h3


def test_input_fingerprint_is_deterministic():
    sset = [("a", "h1"), ("b", "h2"), ("c", "h3")]
    assert compute_input_fingerprint(sset) == compute_input_fingerprint(sset)


# --- Order independence in input_fingerprint --------------------------------

def test_input_fingerprint_is_order_independent():
    a = [("a", "h1"), ("b", "h2"), ("c", "h3")]
    b = [("c", "h3"), ("a", "h1"), ("b", "h2")]
    assert compute_input_fingerprint(a) == compute_input_fingerprint(b)


def test_input_fingerprint_changes_when_member_hash_changes():
    a = [("a", "h1"), ("b", "h2")]
    b = [("a", "h1"), ("b", "h2_DIFFERENT")]
    assert compute_input_fingerprint(a) != compute_input_fingerprint(b)


# --- Discrimination ---------------------------------------------------------

def test_raw_hash_changes_for_different_content():
    assert compute_raw_hash({"a": 1}) != compute_raw_hash({"a": 2})


def test_raw_hash_does_not_collide_on_key_reorder_canonically():
    # Canonical JSON sorts keys, so {"a":1,"b":2} and {"b":2,"a":1} produce the
    # same raw_hash. This is intentional: dict-key order is not meaningful in
    # JSON content.
    assert compute_raw_hash({"a": 1, "b": 2}) == compute_raw_hash({"b": 2, "a": 1})


def test_semantic_hash_collapses_what_normalization_collapses():
    hints = {"text": {"whitespace_collapsible": True, "case_insensitive": True}}
    a = {"text": "Hello   World"}
    b = {"text": "hello world"}
    assert compute_raw_hash(a) != compute_raw_hash(b)
    assert compute_semantic_hash(a, "primary_claim", hints_override=hints) == compute_semantic_hash(
        b, "primary_claim", hints_override=hints
    )


def test_semantic_hash_distinguishes_what_normalization_does_not_collapse():
    hints = {"text": {"case_insensitive": False}}
    a = {"text": "Apple"}
    b = {"text": "Banana"}
    assert compute_semantic_hash(a, "primary_claim", hints_override=hints) != compute_semantic_hash(
        b, "primary_claim", hints_override=hints
    )


# --- Raw vs semantic --------------------------------------------------------

def test_raw_and_semantic_differ_when_cosmetic_field_present():
    hints = {"timestamp": {"cosmetic_only": True}}
    content = {"x": 1, "timestamp": "2026-05-23T00:00:00Z"}
    raw = compute_raw_hash(content)
    sem = compute_semantic_hash(content, "provenance_summary", hints_override=hints)
    # Stripping a field from the normalized form yields a different hash.
    assert raw != sem


def test_raw_and_semantic_agree_when_no_normalization_applies():
    # If the hints are empty, semantic normalization is the identity (modulo
    # canonical JSON serialization, which both raw and semantic apply).
    content = {"a": 1, "b": "hello"}
    raw = compute_raw_hash(content)
    sem = compute_semantic_hash(content, "primary_claim", hints_override={})
    assert raw == sem


# --- Input fingerprint composition ------------------------------------------

def test_input_fingerprint_accepts_empty_support_set():
    assert _SHA256_RE.match(compute_input_fingerprint([]))


def test_input_fingerprint_accepts_iterables_of_any_kind():
    a = compute_input_fingerprint([("a", "h1"), ("b", "h2")])
    b = compute_input_fingerprint(iter([("a", "h1"), ("b", "h2")]))
    c = compute_input_fingerprint({("a", "h1"), ("b", "h2")})  # set, order-undefined
    assert a == b == c
