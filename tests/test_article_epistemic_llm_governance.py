"""Stage 1 LLM governance tests.

Authority: docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md §9, §11.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from scripts import build_article_epistemic_layer as builder
from scripts import verify_article_epistemic_layer_contract as verifier
from tests._article_epistemic_fixtures import (
    complete_record,
    record_with_llm_generated_content,
)

ROOT = Path(__file__).resolve().parents[1]
BUILDER_SCRIPT = ROOT / "scripts" / "build_article_epistemic_layer.py"


def test_builder_source_has_no_provider_sdk_imports():
    """Spec §9: builder must not import provider SDKs directly."""
    src = BUILDER_SCRIPT.read_text()
    for pat in verifier.FORBIDDEN_PROVIDER_PATTERNS:
        assert not pat.search(src), (
            f"builder source contains forbidden import matching {pat.pattern!r}"
        )


def test_builder_emits_no_llm_generated_components():
    rec = complete_record("P1")
    out = builder.build_record_for_paper("P1", rec, "aepl-20260523-000001")
    for c in out["components"]:
        assert c["source_mode"] != "llm_generated"
        assert c["field_policy"] != "llm_enrichable" or c["status"] != "present", (
            f"{c['component_type']} present with llm_enrichable policy in Stage 1"
        )


def test_verifier_rejects_llm_generated_component(aepl_db_path):
    """Inject an llm_generated component directly into the DB and verify the
    strict verifier surfaces the violation."""
    started_at = builder.utc_now()
    conn = sqlite3.connect(aepl_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    build_run_id = builder.make_build_run_id(started_at, conn)
    rec = record_with_llm_generated_content("TEST-LLM-INJECTED")
    try:
        with conn:
            builder.write_build_run_row(conn, build_run_id, started_at)
            paper_record = builder.build_record_for_paper(
                "TEST-LLM-INJECTED", rec, build_run_id
            )
            builder.persist_record(conn, paper_record, build_run_id)
            builder.finalize_build_run_row(
                conn, build_run_id,
                finished_at=builder.utc_now(),
                input_snapshot_hash="sha256:test",
                record_count=1, success_count=1, failure_count=0,
                repair_count=0,
                status="completed",
                report={},
            )
            # Now tamper: set one component's source_mode to llm_generated.
            conn.execute(
                "UPDATE article_epistemic_components "
                "SET source_mode = 'llm_generated' "
                "WHERE paper_id = ? AND component_type = 'primary_claim'",
                ("TEST-LLM-INJECTED",),
            )
    finally:
        conn.close()

    conn = sqlite3.connect(aepl_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        global_failures, per_record, _ = verifier.verify_all(conn, payload=None)
    finally:
        conn.close()
    all_fail_checks = (
        [f.check for f in global_failures]
        + [f.check for fails in per_record.values() for f in fails]
    )
    assert "stage1.no_llm_source_mode" in all_fail_checks


def test_release_eligible_stays_zero_for_llm_or_stale_components():
    """Even when a Stage-2-style upgrade tries to mark release_eligible=1, the
    verifier release-gate check holds the line. We exercise that via a record
    fabrication."""
    rec = complete_record("P1")
    out = builder.build_record_for_paper("P1", rec, "aepl-20260523-000001")
    # Hand-fabricate a stale required component + release_eligible=1.
    record = dict(out["record"], release_eligible=1, freshness_status="stale")
    components = [dict(c) for c in out["components"]]
    bn_idx = next(i for i, c in enumerate(components)
                  if c["component_type"] == "belief_network_context")
    components[bn_idx]["freshness_status"] = "stale"
    failures = verifier.check_release_eligibility_gating(record, components)
    assert any(f.check == "release.gated_by_required_freshness" for f in failures)
