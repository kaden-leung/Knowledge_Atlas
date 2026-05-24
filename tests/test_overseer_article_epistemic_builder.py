"""Tests for overseer.article_epistemic_builder (Stage 1 deterministic).

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §12

Naming note: a separate tests/test_article_epistemic_builder.py covers the
COMPANION contract's builder (scripts/build_article_epistemic_layer.py). This
file covers the OVERSEER-side builder in overseer/article_epistemic_builder.py.
"""

from __future__ import annotations

import json

import pytest

from overseer.artefact_registry import (
    FencingTokenMismatch,
    increment_fencing_token,
    register,
)
from overseer.article_epistemic_builder import (
    BUILDER_NAME,
    BUILDER_VERSION,
    PaperInputs,
    assign_answer_shape,
    build_one,
    select_primary_claim,
)
from overseer.build_runs import start as start_build_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_pnu(conn, pnu_id: str = "PNU-001"):
    a = register(conn, kind="pnu_row", entity_type="pnu", entity_id=pnu_id,
                 field_path=None, schema_version="pnu_row.v1")
    return a.artefact_id, "sha256:pnu_hash_" + pnu_id


def _start_build(conn):
    return start_build_run(
        conn, builder_name=BUILDER_NAME, builder_version=BUILDER_VERSION,
        input_snapshot_hash="sha256:snap",
    )


def _claim_paper(conn, paper_id: str) -> int:
    art = register(
        conn, kind="article_epistemic_record", entity_type="paper",
        entity_id=paper_id, field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    return increment_fencing_token(conn, art.artefact_id)


# ---------------------------------------------------------------------------
# Rule cascades (pure functions)
# ---------------------------------------------------------------------------

def test_select_primary_claim_prefers_structured_core_finding():
    inputs = PaperInputs(
        paper_id="PDF-0007", support_members=[],
        structured_core_finding="Color reduces stress",
        top_claims=[{"canonical_claim_text": "Other claim"}],
    )
    text, origin = select_primary_claim(inputs)
    assert text == "Color reduces stress"
    assert origin == "structured_core_finding"


def test_select_primary_claim_falls_back_to_top_claims_with_priority_ordering():
    inputs = PaperInputs(
        paper_id="PDF-0007", support_members=[],
        top_claims=[
            {"canonical_claim_text": "Low support", "support_count": 1},
            {"canonical_claim_text": "High support", "support_count": 10},
        ],
    )
    text, origin = select_primary_claim(inputs)
    assert text == "High support"
    assert origin == "top_claims_row"


def test_select_primary_claim_uses_article_main_conclusion_next():
    inputs = PaperInputs(
        paper_id="PDF-0007", support_members=[],
        article_main_conclusion="Main conclusion",
    )
    text, origin = select_primary_claim(inputs)
    assert text == "Main conclusion"
    assert origin == "article_level_main_conclusion"


def test_select_primary_claim_uses_science_summary_last():
    inputs = PaperInputs(
        paper_id="PDF-0007", support_members=[],
        science_summary={"core_finding": "Summary finding"},
    )
    text, origin = select_primary_claim(inputs)
    assert text == "Summary finding"
    assert origin == "science_summary_core_finding"


def test_select_primary_claim_returns_not_extracted_when_no_input():
    inputs = PaperInputs(paper_id="PDF-0007", support_members=[])
    text, origin = select_primary_claim(inputs)
    assert text is None
    assert origin == "not_extracted"


def test_select_primary_claim_canonicalizes_whitespace():
    inputs = PaperInputs(
        paper_id="PDF-0007", support_members=[],
        structured_core_finding="  Color   reduces  stress  ",
    )
    text, _ = select_primary_claim(inputs)
    assert text == "Color reduces stress"


def test_assign_answer_shape_uses_explicit_hint_first():
    inputs = PaperInputs(
        paper_id="P", support_members=[],
        argumentation={"shape_hint": "toulmin"},
        evidence_profile={"comparison": "yes"},
    )
    shape, rule_id, _ = assign_answer_shape(inputs)
    assert shape == "toulmin"
    assert rule_id == "R1_explicit_hint"


def test_assign_answer_shape_detects_comparison():
    inputs = PaperInputs(
        paper_id="P", support_members=[],
        evidence_profile={"comparison": {"a": 1}},
    )
    shape, rule_id, _ = assign_answer_shape(inputs)
    assert shape == "comparison"
    assert rule_id == "R2_comparison"


def test_assign_answer_shape_falls_back_to_unknown_with_rule_trace():
    inputs = PaperInputs(paper_id="P", support_members=[])
    shape, rule_id, trace = assign_answer_shape(inputs)
    assert shape == "unknown"
    assert rule_id == "R5_fallback"
    fired = [r for r in trace["rules_checked"] if r["fired"]]
    assert len(fired) == 1 and fired[0]["rule"] == "R5_fallback"


def test_assign_answer_shape_detects_toulmin_via_warrant_data():
    inputs = PaperInputs(
        paper_id="P", support_members=[],
        top_claims=[{"canonical_claim_text": "c", "warrant": "w", "data": "d"}],
    )
    shape, rule_id, _ = assign_answer_shape(inputs)
    assert shape == "toulmin"
    assert rule_id == "R3_toulmin"


def test_assign_answer_shape_detects_field_map_via_iv_dv():
    inputs = PaperInputs(
        paper_id="P", support_members=[],
        top_claims=[{"canonical_claim_text": "c", "iv": "s", "dv": "r"}],
    )
    shape, rule_id, _ = assign_answer_shape(inputs)
    assert shape == "field_map"
    assert rule_id == "R4_field_map"


# ---------------------------------------------------------------------------
# build_one end-to-end
# ---------------------------------------------------------------------------

def test_build_one_writes_artefact_components_and_hashes(overseer_db):
    aid_pnu, h_pnu = _register_pnu(overseer_db, "PNU-A")
    paper_id = "PDF-0007"
    fencing_token = _claim_paper(overseer_db, paper_id)
    brid = _start_build(overseer_db)
    inputs = PaperInputs(
        paper_id=paper_id,
        support_members=[(aid_pnu, h_pnu)],
        structured_core_finding="Color reduces stress",
        top_claims=[{
            "canonical_claim_text": "Color reduces stress",
            "support_count": 5, "attack_count": 0, "credence": 0.7,
        }],
        pnu_links=[{"pnu_id": "PNU-A", "pnu_version_hash": h_pnu,
                    "edge_kind": "supports"}],
        argumentation={"defeaters": [
            {"target_kind": "method", "content": "small N"},
        ]},
    )
    result = build_one(
        overseer_db, paper_id=paper_id, inputs=inputs,
        build_run_id=brid, fencing_token=fencing_token,
    )
    assert result.primary_claim_origin == "structured_core_finding"
    assert result.defeater_count == 1
    assert result.belief_link_count == 1
    assert result.raw_hash.startswith("sha256:")
    assert result.semantic_hash.startswith("sha256:")

    row = overseer_db.execute(
        "SELECT raw_hash, semantic_hash, freshness_status, latest_build_run_id "
        "FROM artefact_registry WHERE artefact_id = ?",
        (result.artefact_id,),
    ).fetchone()
    assert row["raw_hash"] == result.raw_hash
    assert row["freshness_status"] == "fresh"
    assert row["latest_build_run_id"] == brid

    ch = overseer_db.execute(
        "SELECT raw_hash, semantic_hash, normalization_rule_version "
        "FROM content_hashes WHERE artefact_id = ? AND build_run_id = ?",
        (result.artefact_id, brid),
    ).fetchone()
    assert ch["raw_hash"] == result.raw_hash
    assert ch["normalization_rule_version"] == "v1"

    claims = overseer_db.execute(
        "SELECT claim_origin FROM claims WHERE paper_id = ?", (paper_id,)
    ).fetchall()
    assert any(c["claim_origin"] == "structured_core_finding" for c in claims)
    defs = overseer_db.execute(
        "SELECT target_kind FROM defeaters"
    ).fetchall()
    assert defs[0]["target_kind"] == "method"
    bn = overseer_db.execute(
        "SELECT pnu_version_hash, edge_kind FROM belief_network_links"
    ).fetchone()
    assert bn["pnu_version_hash"] == h_pnu
    ash = overseer_db.execute(
        "SELECT shape, rule_id, rule_trace_json FROM answer_shape_decisions"
    ).fetchone()
    assert ash["shape"] == "unknown"
    assert ash["rule_id"] == "R5_fallback"


def test_build_one_distinguishes_attack_count_with_vs_without_mapped_rows(overseer_db):
    paper1 = "PDF-A"
    paper2 = "PDF-B"
    t1 = _claim_paper(overseer_db, paper1)
    t2 = _claim_paper(overseer_db, paper2)
    br1 = _start_build(overseer_db)
    br2 = _start_build(overseer_db)

    inputs_with_attacks = PaperInputs(
        paper_id=paper1, support_members=[],
        structured_core_finding="A claim",
        argumentation={"attack_count": 3, "defeaters": []},
    )
    inputs_no_attacks = PaperInputs(
        paper_id=paper2, support_members=[],
        structured_core_finding="A claim",
        argumentation={"attack_count": 0, "defeaters": []},
    )
    r1 = build_one(overseer_db, paper_id=paper1, inputs=inputs_with_attacks,
                   build_run_id=br1, fencing_token=t1)
    r2 = build_one(overseer_db, paper_id=paper2, inputs=inputs_no_attacks,
                   build_run_id=br2, fencing_token=t2)
    # Different absence_reason -> different raw_hash.
    assert r1.raw_hash != r2.raw_hash


def test_build_one_drops_defeaters_missing_target_kind(overseer_db):
    paper_id = "PDF-0042"
    fencing_token = _claim_paper(overseer_db, paper_id)
    brid = _start_build(overseer_db)
    inputs = PaperInputs(
        paper_id=paper_id, support_members=[],
        structured_core_finding="A claim",
        argumentation={"defeaters": [
            {"content": "no target_kind"},
            {"target_kind": "claim", "content": "valid"},
        ]},
    )
    result = build_one(overseer_db, paper_id=paper_id, inputs=inputs,
                       build_run_id=brid, fencing_token=fencing_token)
    assert result.defeater_count == 1


def test_build_one_rejects_stale_fencing_token(overseer_db):
    paper_id = "PDF-0050"
    art = register(
        overseer_db, kind="article_epistemic_record", entity_type="paper",
        entity_id=paper_id, field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    stale = increment_fencing_token(overseer_db, art.artefact_id)
    increment_fencing_token(overseer_db, art.artefact_id)  # watchdog bump
    brid = _start_build(overseer_db)
    inputs = PaperInputs(
        paper_id=paper_id, support_members=[],
        structured_core_finding="X",
    )
    with pytest.raises(FencingTokenMismatch):
        build_one(overseer_db, paper_id=paper_id, inputs=inputs,
                  build_run_id=brid, fencing_token=stale)


def test_build_one_is_idempotent_under_identical_inputs(overseer_db):
    paper_id = "PDF-0008"
    fencing_token = _claim_paper(overseer_db, paper_id)
    brid = _start_build(overseer_db)
    inputs = PaperInputs(
        paper_id=paper_id, support_members=[],
        structured_core_finding="Stable claim",
    )
    r1 = build_one(overseer_db, paper_id=paper_id, inputs=inputs,
                   build_run_id=brid, fencing_token=fencing_token)
    r2 = build_one(overseer_db, paper_id=paper_id, inputs=inputs,
                   build_run_id=brid, fencing_token=fencing_token)
    assert r1.raw_hash == r2.raw_hash
    assert r1.semantic_hash == r2.semantic_hash


def test_build_one_records_answer_shape_rule_trace_when_unknown(overseer_db):
    paper_id = "PDF-0009"
    fencing_token = _claim_paper(overseer_db, paper_id)
    brid = _start_build(overseer_db)
    inputs = PaperInputs(
        paper_id=paper_id, support_members=[],
        structured_core_finding="Bare claim",
    )
    build_one(overseer_db, paper_id=paper_id, inputs=inputs,
              build_run_id=brid, fencing_token=fencing_token)
    trace_json = overseer_db.execute(
        "SELECT rule_trace_json FROM answer_shape_decisions"
    ).fetchone()[0]
    parsed = json.loads(trace_json)
    fired = [r for r in parsed["rules_checked"] if r["fired"]]
    assert any(r["rule"] == "R5_fallback" for r in fired)
