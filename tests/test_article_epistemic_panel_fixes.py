"""Regression tests for the 2026-05-24 panel-review fixes (plan A/B/C).

Covers, with one test per finding:
  * A  — payload_hash is content-only and recomputes from the artefact's own
         bytes; mutable lifecycle/status state is excluded from the hash.
  * A  — input_fingerprint includes builder_version (no silent regression).
  * 4  — the verifier writes review_status='machine_verified' on a clean pass
         and leaves a failing record 'unreviewed'.
  * 5  — the defeater row contract (target_kind + defeat_kind) is enforced.
  * 4  — evidence_strength declares argument-support, not severity, semantics.
  * 6  — the production-typical (stale-PNU) record — the 758/760 shape — is
         asserted end to end, not just the fresh happy path.
  * C  — resolve_db_path skips 0-byte decoys; the verifier fails fast on an
         un-initialized DB instead of crashing mid-query.

Authority: docs/AEPL_PANEL_RUTHLESS_REVIEW_OUTPUT_2026-05-24.md §4.2.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_article_epistemic_layer as builder
from scripts import verify_article_epistemic_layer_contract as verifier
from tests._article_epistemic_fixtures import (
    complete_record,
    production_typical_record,
)

BR = "aepl-20260524-000001"


def _build(paper_id, rec):
    return builder.build_record_for_paper(paper_id, rec, BR)


def _persist(db_path, paper_id, rec):
    started = builder.utc_now()
    conn = sqlite3.connect(db_path)
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = ON")
    brid = builder.make_build_run_id(started, conn)
    try:
        conn.execute("BEGIN IMMEDIATE")
        builder.write_build_run_row(conn, brid, started)
        pr = builder.build_record_for_paper(paper_id, rec, brid)
        builder.persist_record(conn, pr, brid)
        builder.finalize_build_run_row(
            conn, brid, finished_at=builder.utc_now(),
            input_snapshot_hash="sha256:test", record_count=1, success_count=1,
            failure_count=0, repair_count=len(pr["repair_items"]),
            status="completed", report={})
        conn.commit()
    finally:
        conn.close()
    return brid


# --------------------------------------------------------------------------- A
def test_payload_hash_is_content_only_and_recomputes_from_artefact():
    out = _build("PDF-9999", complete_record("PDF-9999"))
    rec = out["record"]
    comps = {c["component_type"]: c["content_json"] for c in out["components"]}
    content = {
        "schema_version": rec["schema_version"],
        "record_id": rec["record_id"],
        "paper_id": rec["paper_id"],
        "primary_claim_id": rec["primary_claim_id"],
        "components": comps,
    }
    assert "sha256:" + builder.sha256_canonical(content) == rec["payload_hash"]


def test_payload_hash_excludes_mutable_lifecycle_state():
    """Adding any status field to the hashed dict must change the hash — proof
    that lifecycle state is not part of the content identity (fixes false-vs-0)."""
    out = _build("PDF-9999", complete_record("PDF-9999"))
    rec = out["record"]
    comps = {c["component_type"]: c["content_json"] for c in out["components"]}
    base = {
        "schema_version": rec["schema_version"], "record_id": rec["record_id"],
        "paper_id": rec["paper_id"], "primary_claim_id": rec["primary_claim_id"],
        "components": comps,
    }
    polluted = dict(base, release_eligible=rec["release_eligible"],
                    review_status=rec["review_status"])
    assert builder.sha256_canonical(base) != builder.sha256_canonical(polluted)
    # And the real stored hash matches the clean (content-only) form.
    assert "sha256:" + builder.sha256_canonical(base) == rec["payload_hash"]


def test_input_fingerprint_changes_with_builder_version(monkeypatch):
    rec = complete_record("PDF-9999")
    a = _build("PDF-9999", rec)["record"]["input_fingerprint"]
    monkeypatch.setattr(builder, "BUILDER_VERSION", "article_epistemic_builder.v2")
    b = _build("PDF-9999", rec)["record"]["input_fingerprint"]
    assert a != b, "bumping builder_version must change input_fingerprint"


# --------------------------------------------------------------------------- 4
def test_verifier_marks_clean_record_machine_verified(aepl_db_path):
    _persist(aepl_db_path, "TEST-CLEAN", complete_record("TEST-CLEAN"))
    rc = verifier.main(["--db", str(aepl_db_path),
                        "--payload", "/tmp/_aepl_nonexistent.json", "--quiet"])
    assert rc == 0
    conn = sqlite3.connect(aepl_db_path)
    try:
        rs = conn.execute(
            "SELECT review_status FROM article_epistemic_records "
            "WHERE paper_id='TEST-CLEAN' AND active=1").fetchone()[0]
    finally:
        conn.close()
    assert rs == "machine_verified"


def test_verifier_leaves_failing_record_unreviewed(aepl_db_path):
    _persist(aepl_db_path, "TEST-DIRTY", complete_record("TEST-DIRTY"))
    # Tamper: make one component llm_generated → a per-record failure.
    conn = sqlite3.connect(aepl_db_path)
    conn.execute("UPDATE article_epistemic_components SET source_mode='llm_generated' "
                 "WHERE paper_id='TEST-DIRTY' AND component_type='primary_claim'")
    conn.commit()
    conn.close()
    verifier.main(["--db", str(aepl_db_path),
                   "--payload", "/tmp/_aepl_nonexistent.json", "--quiet"])
    conn = sqlite3.connect(aepl_db_path)
    try:
        rs = conn.execute(
            "SELECT review_status FROM article_epistemic_records "
            "WHERE paper_id='TEST-DIRTY' AND active=1").fetchone()[0]
    finally:
        conn.close()
    assert rs == "unreviewed"


# --------------------------------------------------------------------------- 5
def test_defeater_row_without_target_kind_is_rejected():
    out = _build("PDF-9999", complete_record("PDF-9999"))
    comps = [dict(c) for c in out["components"]]
    dfi = next(i for i, c in enumerate(comps) if c["component_type"] == "defeaters")
    # Inject an untyped defeater row (the pre-fix failure mode).
    bad = dict(comps[dfi]["content_json"], rows=[{"content": "some attack"}])
    comps[dfi] = dict(comps[dfi], content_json=bad)
    fails = verifier.check_defeater_row_contract(out["record"], comps)
    checks = {f.check for f in fails}
    assert "defeaters.row_target_kind" in checks
    assert "defeaters.row_defeat_kind" in checks


def test_defeater_row_with_valid_target_and_defeat_kind_passes():
    out = _build("PDF-9999", complete_record("PDF-9999"))
    comps = [dict(c) for c in out["components"]]
    dfi = next(i for i, c in enumerate(comps) if c["component_type"] == "defeaters")
    good = dict(comps[dfi]["content_json"],
                rows=[{"target_kind": "warrant", "defeat_kind": "undercutting",
                       "content": "the warrant does not transmit support here"}])
    comps[dfi] = dict(comps[dfi], content_json=good)
    assert verifier.check_defeater_row_contract(out["record"], comps) == []


def test_defeaters_distinguish_not_extracted_from_not_exists():
    """Stage 1 must never assert no_defeater_exists (Pollock)."""
    out = _build("PDF-9999", complete_record("PDF-9999"))
    df = next(c for c in out["components"] if c["component_type"] == "defeaters")
    assert df["content_json"]["defeater_existence"] == "no_defeater_extracted"
    assert "row_contract" in df["content_json"]


# --------------------------------------------------------------------------- 4
def test_evidence_strength_declares_argument_support_not_severity():
    out = _build("PDF-9999", complete_record("PDF-9999"))
    ev = next(c for c in out["components"] if c["component_type"] == "evidence_strength")
    assert ev["content_json"]["measure_semantics"] == "argument_support_not_severity"
    assert ev["display_label"] == "Argument Support"


# --------------------------------------------------------------------------- 6
def test_production_typical_record_renders_with_pending_pnu(aepl_db_path):
    """The 758/760 shape (complete extraction + requires_repair PNU) now RENDERS:
    core is fresh, the belief-network section is pending, and the PNU repair is a
    non-blocking warning. This is the graceful-degradation principle in action."""
    out = _build("TEST-PROD", production_typical_record("TEST-PROD"))
    rec = out["record"]
    assert rec["freshness_status"] == "fresh"       # core is fresh
    assert rec["render_status"] == "renderable"     # the page renders now
    assert rec["extraction_status"] == "complete"
    assert rec["review_status"] == "unreviewed"     # not verified at build time
    bn = next(c for c in out["components"]
              if c["component_type"] == "belief_network_context")
    assert bn["status"] == "stale"                  # the section itself is pending
    # PNU is enrichment → no blocking repair item:
    assert not any(r["severity"] == "blocking" for r in out["repair_items"])
    bn_repairs = [r for r in out["repair_items"]
                  if r["component_type"] == "belief_network_context"]
    assert bn_repairs and bn_repairs[0]["severity"] == "warning"
    # End to end: persists and verifies clean and earns machine_verified.
    _persist(aepl_db_path, "TEST-PROD", production_typical_record("TEST-PROD"))
    rc = verifier.main(["--db", str(aepl_db_path),
                        "--payload", "/tmp/_aepl_nonexistent.json", "--quiet"])
    assert rc == 0


# --------------------------------------------------------------------------- C
def test_resolve_db_path_skips_zero_byte_decoy(tmp_path, monkeypatch):
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    real = tmp_path / "real.db"
    sqlite3.connect(real).close()
    real.write_bytes(b"x" * 10)  # non-zero
    monkeypatch.setattr(builder, "DEFAULT_DB_CANDIDATES", (empty, real))
    assert builder.resolve_db_path(None) == real


def test_verifier_fails_fast_on_uninitialized_db(tmp_path, capsys):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()  # 0-byte-ish, no tables
    rc = verifier.main(["--db", str(empty), "--strict"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "un-initialized" in err
