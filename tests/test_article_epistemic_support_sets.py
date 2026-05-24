"""Support-set hashing tests.

Authority: docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md §3, §5, §6.
"""

from __future__ import annotations

from scripts import build_article_epistemic_layer as builder
from tests._article_epistemic_fixtures import complete_record


def test_support_set_id_is_deterministic_for_same_members():
    members = [
        {
            "source_artifact_id": "article_details_json:P1:top_claims",
            "source_kind": "article_details_field",
            "source_path_or_table": "data/ka_payloads/article_details.json",
            "source_record_id": "P1",
            "source_field_path": "details.P1.top_claims",
            "source_hash": "abc123",
        }
    ]
    a = builder.make_support_set_id(members)
    b = builder.make_support_set_id(list(members))
    assert a == b
    assert a.startswith("support_set:")


def test_support_set_id_independent_of_member_order():
    m1 = {
        "source_artifact_id": "article_details_json:P1:top_claims",
        "source_kind": "article_details_field",
        "source_path_or_table": "x",
        "source_record_id": "P1",
        "source_field_path": "details.P1.top_claims",
        "source_hash": "a",
    }
    m2 = {
        "source_artifact_id": "article_details_json:P1:argumentation",
        "source_kind": "article_details_field",
        "source_path_or_table": "x",
        "source_record_id": "P1",
        "source_field_path": "details.P1.argumentation",
        "source_hash": "b",
    }
    a = builder.make_support_set_id([m1, m2])
    b = builder.make_support_set_id([m2, m1])
    assert a == b


def test_support_set_id_changes_when_member_hash_changes():
    base = {
        "source_artifact_id": "article_details_json:P1:top_claims",
        "source_kind": "article_details_field",
        "source_path_or_table": "x",
        "source_record_id": "P1",
        "source_field_path": "details.P1.top_claims",
        "source_hash": "a",
    }
    modified = dict(base, source_hash="b")
    assert builder.make_support_set_id([base]) != builder.make_support_set_id([modified])


def test_builder_emits_one_support_set_per_component_type():
    rec = complete_record("P1")
    out = builder.build_record_for_paper("P1", rec, "aepl-20260523-000001")
    # Seven components → seven support_set_ids (some may coincidentally share
    # if their members happen to match, but in this fixture they don't).
    assert len(out["support_sets"]) == 7


def test_support_set_hash_recomputes_from_members():
    """Independent recomputation of support_set_hash must match what the builder stored."""
    rec = complete_record("P1")
    out = builder.build_record_for_paper("P1", rec, "aepl-20260523-000001")
    for ss in out["support_sets"].values():
        sorted_members = sorted(
            ss["members"],
            key=lambda m: (m["source_artifact_id"], m["source_field_path"]),
        )
        recomputed = builder.sha256_canonical(sorted_members)
        assert recomputed == ss["support_set_hash"]


def test_support_set_id_format_is_support_set_colon_sixteen_hex():
    rec = complete_record("P1")
    out = builder.build_record_for_paper("P1", rec, "aepl-20260523-000001")
    for ssid in out["support_sets"]:
        prefix, digest = ssid.split(":", 1)
        assert prefix == "support_set"
        assert len(digest) == 16
        assert all(ch in "0123456789abcdef" for ch in digest)
