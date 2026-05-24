"""Tests for the dependency-overseer normalization rule v1.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §12 (test plan)
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P27)
"""

from __future__ import annotations

import hashlib
import json

import pytest

from overseer.normalization import (
    UnknownComponentTypeError,
    canonical_raw_bytes,
    normalize_for_semantic_hash,
)


def _sem(content, component_type, hints=None):
    return normalize_for_semantic_hash(
        content, component_type, hints_override=hints
    )


def _hash(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --- Whitespace collapse ----------------------------------------------------

def test_whitespace_only_change_in_collapsible_field_yields_same_semantic_hash():
    hints = {"canonical_claim_text": {"whitespace_collapsible": True}}
    a = {"canonical_claim_text": "Color   reduces  stress."}
    b = {"canonical_claim_text": "  Color reduces stress.  "}
    c = {"canonical_claim_text": "Color\treduces\nstress."}
    assert _sem(a, "primary_claim", hints) == _sem(b, "primary_claim", hints)
    assert _sem(b, "primary_claim", hints) == _sem(c, "primary_claim", hints)


def test_whitespace_change_in_non_collapsible_field_yields_different_semantic_hash():
    hints = {"narrative": {}}  # no whitespace_collapsible flag
    a = {"narrative": "color reduces stress"}
    b = {"narrative": "color  reduces  stress"}
    assert _sem(a, "primary_claim", hints) != _sem(b, "primary_claim", hints)


# --- Key reordering ---------------------------------------------------------

def test_dict_key_reordering_yields_same_semantic_hash():
    a = {"alpha": 1, "beta": 2, "gamma": 3}
    b = {"gamma": 3, "alpha": 1, "beta": 2}
    assert _sem(a, "primary_claim", hints={}) == _sem(b, "primary_claim", hints={})


def test_nested_dict_key_reordering_yields_same_semantic_hash():
    a = {"outer": {"alpha": 1, "beta": 2}}
    b = {"outer": {"beta": 2, "alpha": 1}}
    assert _sem(a, "primary_claim", hints={}) == _sem(b, "primary_claim", hints={})


# --- Order-insensitive lists ------------------------------------------------

def test_order_insensitive_list_reordering_yields_same_semantic_hash():
    hints = {"rows": {"order_insensitive": True}}
    a = {"rows": [{"id": 1}, {"id": 2}, {"id": 3}]}
    b = {"rows": [{"id": 3}, {"id": 1}, {"id": 2}]}
    assert _sem(a, "defeaters", hints) == _sem(b, "defeaters", hints)


def test_order_sensitive_list_reordering_yields_different_semantic_hash():
    hints = {"steps": {}}  # not order_insensitive
    a = {"steps": ["first", "second", "third"]}
    b = {"steps": ["third", "first", "second"]}
    assert _sem(a, "primary_claim", hints) != _sem(b, "primary_claim", hints)


# --- Cosmetic-only fields ---------------------------------------------------

def test_cosmetic_only_field_is_dropped_from_semantic_hash():
    hints = {"generated_at": {"cosmetic_only": True}}
    a = {"claim_text": "X", "generated_at": "2026-05-23T01:00:00Z"}
    b = {"claim_text": "X", "generated_at": "2026-05-24T02:00:00Z"}
    assert _sem(a, "provenance_summary", hints) == _sem(b, "provenance_summary", hints)


def test_cosmetic_only_field_is_retained_in_raw_hash():
    a = {"claim_text": "X", "generated_at": "2026-05-23T01:00:00Z"}
    b = {"claim_text": "X", "generated_at": "2026-05-24T02:00:00Z"}
    assert canonical_raw_bytes(a) != canonical_raw_bytes(b)


# --- Case-insensitive fields ------------------------------------------------

def test_case_change_in_case_insensitive_field_yields_same_semantic_hash():
    hints = {"claim_scope": {"case_insensitive": True}}
    a = {"claim_scope": "Population-Wide"}
    b = {"claim_scope": "population-wide"}
    c = {"claim_scope": "POPULATION-WIDE"}
    assert _sem(a, "primary_claim", hints) == _sem(b, "primary_claim", hints)
    assert _sem(b, "primary_claim", hints) == _sem(c, "primary_claim", hints)


def test_case_change_in_case_sensitive_field_yields_different_semantic_hash():
    hints = {"canonical_claim_text": {"whitespace_collapsible": True, "case_insensitive": False}}
    a = {"canonical_claim_text": "Color reduces stress"}
    b = {"canonical_claim_text": "color reduces stress"}
    assert _sem(a, "primary_claim", hints) != _sem(b, "primary_claim", hints)


# --- Determinism ------------------------------------------------------------

def test_normalization_is_deterministic_across_calls():
    content = {"b": 2, "a": [3, 1, 2], "c": {"y": "y", "x": "x"}}
    hints = {"a": {"order_insensitive": True}}
    out1 = _sem(content, "defeaters", hints)
    out2 = _sem(content, "defeaters", hints)
    out3 = _sem(content, "defeaters", hints)
    assert out1 == out2 == out3


def test_raw_bytes_are_deterministic():
    content = {"b": 2, "a": 1}
    assert canonical_raw_bytes(content) == canonical_raw_bytes(content)


# --- Raw vs semantic distinction --------------------------------------------

def test_raw_changes_without_semantic_change_for_whitespace():
    hints = {"text": {"whitespace_collapsible": True}}
    a = {"text": "hello   world"}
    b = {"text": "hello world"}
    assert canonical_raw_bytes(a) != canonical_raw_bytes(b)
    assert _sem(a, "primary_claim", hints) == _sem(b, "primary_claim", hints)


def test_raw_changes_without_semantic_change_for_cosmetic_field():
    hints = {"build_run_id": {"cosmetic_only": True}}
    a = {"x": 1, "build_run_id": "run-001"}
    b = {"x": 1, "build_run_id": "run-002"}
    assert canonical_raw_bytes(a) != canonical_raw_bytes(b)
    assert _sem(a, "provenance_summary", hints) == _sem(b, "provenance_summary", hints)


# --- Component-type lookup --------------------------------------------------

def test_known_component_type_loads_hints_from_contract_file():
    # Just confirm primary_claim (which is in component_types.json) does not raise
    out = normalize_for_semantic_hash(
        {"canonical_claim_text": "  hello  world  "}, "primary_claim"
    )
    # whitespace_collapsible should have collapsed the spaces
    assert "hello world" in out.decode("utf-8")


def test_unknown_component_type_raises():
    with pytest.raises(UnknownComponentTypeError):
        normalize_for_semantic_hash({}, "definitely_not_registered")


def test_unsupported_rule_version_raises():
    with pytest.raises(ValueError):
        normalize_for_semantic_hash({}, "primary_claim", rule_version="v99")


# --- List-element path matching ---------------------------------------------

def test_list_element_path_hint_applies_per_item():
    hints = {
        "rows[].claim_text": {"whitespace_collapsible": True},
        "rows[].name": {"case_insensitive": True},
    }
    a = {"rows": [
        {"claim_text": "x   y", "name": "Alice"},
        {"claim_text": "z   w", "name": "Bob"},
    ]}
    b = {"rows": [
        {"claim_text": "x y", "name": "alice"},
        {"claim_text": "z w", "name": "BOB"},
    ]}
    assert _sem(a, "claim_rows", hints) == _sem(b, "claim_rows", hints)
