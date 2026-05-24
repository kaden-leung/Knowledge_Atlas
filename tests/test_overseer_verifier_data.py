"""Tests for overseer.verifier_data."""

from __future__ import annotations

from overseer.artefact_registry import (
    increment_fencing_token,
    mark_stale,
    register,
    update_with_hashes,
)
from overseer.article_epistemic_builder import PaperInputs, build_one
from overseer.build_runs import start as start_build_run
from overseer.dependency_edges import add_edge
from overseer.rebuild_queue import enqueue as rq_enqueue, claim_one
from overseer.support_sets import capture as capture_ss
from overseer.verifier_data import (
    CHECKS,
    VerificationReport,
    verify_strict,
    report_to_dict,
)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _seed_canonical(conn, kind, value):
    import hashlib
    h = hashlib.sha256(f"{kind}\x1f{value}".encode()).hexdigest()[:16]
    vid = f"vocab:{kind}:{h}"
    conn.execute(
        """
        INSERT INTO vocabulary_registry (
            value_id, kind, value, canonical_value, first_seen_in_paper,
            first_observed_at, first_observed_build_run_id, review_status,
            canonicalization_source, seeded_from
        ) VALUES (?, ?, ?, NULL, NULL, '2026-05-23T00:00:00Z', NULL,
                  'canonical', NULL, 'test')
        """,
        (vid, kind, value),
    )


def _seed_artefact_kind(conn, kind_name):
    conn.execute(
        """
        INSERT OR IGNORE INTO artefact_kinds (
            kind_name, owner_pipeline, support_rule_module, schema_version,
            active, created_at
        ) VALUES (?, 'test_pipeline', 'test.module', 'v1', 1, '2026-05-23T00:00:00Z')
        """,
        (kind_name,),
    )


# ----------------------------------------------------------------------------
# Clean DB passes every check
# ----------------------------------------------------------------------------

def test_verify_strict_on_empty_db_passes_all_checks(overseer_db):
    report = verify_strict(overseer_db)
    assert isinstance(report, VerificationReport)
    assert report.overall_passed
    for c in report.checks:
        assert c.passed, f"check {c.name} failed: {c.failures}"


def test_verify_strict_returns_a_check_per_registered_check(overseer_db):
    report = verify_strict(overseer_db)
    assert len(report.checks) == len(CHECKS)


def test_report_to_dict_is_json_serializable(overseer_db):
    import json
    report = verify_strict(overseer_db)
    d = report_to_dict(report)
    json.dumps(d)  # raises if not serializable


# ----------------------------------------------------------------------------
# Individual checks fail on the documented failure condition
# ----------------------------------------------------------------------------

def test_referential_integrity_passes_when_edges_have_valid_endpoints(overseer_db):
    p = register(overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-1",
                 field_path=None, schema_version="pnu_row.v1")
    c = register(overseer_db, kind="article_epistemic_record", entity_type="paper",
                 entity_id="PDF-1", field_path=None,
                 schema_version="article_epistemic_layer.v1")
    _seed_artefact_kind(overseer_db, "pnu_row")
    _seed_artefact_kind(overseer_db, "article_epistemic_record")
    add_edge(overseer_db, parent_artefact_id=p.artefact_id,
             child_artefact_id=c.artefact_id, edge_kind="supports")
    report = verify_strict(overseer_db)
    assert all(c.passed for c in report.checks), [
        (c.name, c.failures) for c in report.checks if not c.passed
    ]


def test_kind_registration_fails_when_artefact_kind_unregistered(overseer_db):
    register(overseer_db, kind="rogue_kind", entity_type="paper",
             entity_id="PDF-99", field_path=None, schema_version="v1")
    report = verify_strict(overseer_db)
    failed = [c for c in report.checks if c.name == "kind_registration"]
    assert failed and not failed[0].passed
    assert any(f.get("kind") == "rogue_kind" for f in failed[0].failures)


def test_hash_presence_check_flags_fresh_artefact_with_no_hashes(overseer_db):
    _seed_artefact_kind(overseer_db, "pnu_row")
    a = register(overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-X",
                 field_path=None, schema_version="pnu_row.v1")
    # Force fresh status without hashes.
    overseer_db.execute(
        "UPDATE artefact_registry SET freshness_status = 'fresh' WHERE artefact_id = ?",
        (a.artefact_id,),
    )
    report = verify_strict(overseer_db)
    failed = [c for c in report.checks if c.name == "hash_presence_on_fresh_artefacts"]
    assert failed and not failed[0].passed


def test_defeater_target_typing_passes_on_clean_db(overseer_db):
    # No defeaters inserted; check passes.
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "defeater_target_typing"][0]
    assert res.passed


def test_claim_canonicalization_passes_on_clean_db(overseer_db):
    # claim_id is PRIMARY KEY so duplicate-text-per-claim_id is structurally
    # impossible; the verifier's GROUP BY HAVING n>1 check is a vacuous
    # sanity guard that always passes under the current schema. Confirm it.
    overseer_db.execute(
        """
        INSERT INTO claims (claim_id, paper_id, canonical_claim_text,
            canonicalizer_version, claim_origin, created_at)
        VALUES ('claim:X:abc', 'X', 'Text One', 'v1', 'top_claims_row', '2026-05-23T00:00:00Z')
        """,
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "claim_canonicalization"][0]
    assert res.passed


def test_vocabulary_canonicalization_integrity_fails_on_synonym_without_canonical_target(
    overseer_db,
):
    # Synonym row pointing at a non-existent canonical value.
    overseer_db.execute(
        """
        INSERT INTO vocabulary_registry (
            value_id, kind, value, canonical_value, first_observed_at,
            review_status
        ) VALUES ('vocab:test:bad', 'measure_name', 'orphan_synonym',
                  'no_such_canonical', '2026-05-23T00:00:00Z', 'synonym')
        """,
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "vocabulary_canonicalization_integrity"][0]
    assert not res.passed


def test_fencing_token_monotonicity_fails_when_queue_token_exceeds_artefact(
    overseer_db,
):
    _seed_artefact_kind(overseer_db, "pnu_row")
    a = register(overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-MN",
                 field_path=None, schema_version="pnu_row.v1")
    # Manually craft a queue row with fencing_token higher than the artefact's
    # current_fencing_token. (Should never happen in practice; this asserts the
    # verifier catches such inconsistency.)
    overseer_db.execute(
        """
        INSERT INTO rebuild_queue (
            queue_id, artefact_id, reason, severity, first_seen_at, last_seen_at,
            attempt_count, state, fencing_token
        ) VALUES ('q:test', ?, 'r', 'low', '2026-05-23T00:00:00Z',
                  '2026-05-23T00:00:00Z', 0, 'queued', 99)
        """,
        (a.artefact_id,),
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "fencing_token_monotonicity"][0]
    assert not res.passed


def test_answer_shape_rule_trace_fails_when_unknown_has_empty_trace(overseer_db):
    overseer_db.execute(
        """
        INSERT INTO answer_shape_decisions (
            record_id, shape, rule_id, rule_version, rule_trace_json, created_at
        ) VALUES ('rec:X', 'unknown', 'R5', 'v1', NULL, '2026-05-23T00:00:00Z')
        """,
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "answer_shape_rule_trace"][0]
    assert not res.passed


def test_scaffold_tables_empty_passes_when_no_scaffold_rows(overseer_db):
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "scaffold_tables_empty"][0]
    assert res.passed


def test_scaffold_tables_empty_fails_when_scaffold_populated(overseer_db):
    # Insert into a scaffold table — Phase 1 verifier should flag this.
    overseer_db.execute(
        """
        INSERT INTO cross_db_sync_events (
            event_id, event_kind, status, created_at
        ) VALUES ('ev:test', 'accept_candidate', 'pending', '2026-05-23T00:00:00Z')
        """,
    )
    report = verify_strict(overseer_db)
    res = [c for c in report.checks if c.name == "scaffold_tables_empty"][0]
    assert not res.passed


# ----------------------------------------------------------------------------
# End-to-end: after a builder run, every check should still pass
# ----------------------------------------------------------------------------

def test_verify_strict_passes_after_a_complete_builder_run(overseer_db):
    _seed_artefact_kind(overseer_db, "pnu_row")
    _seed_artefact_kind(overseer_db, "article_epistemic_record")

    # Register PNU as support member.
    pnu = register(overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-E",
                   field_path=None, schema_version="pnu_row.v1")
    # Bring the PNU to fresh status with hashes so it passes
    # hash_presence_on_fresh_artefacts.
    pnu_token = increment_fencing_token(overseer_db, pnu.artefact_id)
    update_with_hashes(
        overseer_db, artefact_id=pnu.artefact_id,
        raw_hash="sha256:p_raw", semantic_hash="sha256:p_sem",
        build_run_id="br:seed:001", fencing_token=pnu_token,
    )

    paper_id = "PDF-2007"
    paper = register(
        overseer_db, kind="article_epistemic_record", entity_type="paper",
        entity_id=paper_id, field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    paper_token = increment_fencing_token(overseer_db, paper.artefact_id)
    brid = start_build_run(
        overseer_db, builder_name="article_epistemic_builder",
        builder_version="v1", input_snapshot_hash="sha256:snap",
    )
    inputs = PaperInputs(
        paper_id=paper_id,
        support_members=[(pnu.artefact_id, "sha256:p_sem")],
        structured_core_finding="Color reduces stress",
        argumentation={"defeaters": [
            {"target_kind": "method", "content": "small N"}
        ]},
        pnu_links=[{"pnu_id": "PNU-E", "pnu_version_hash": "sha256:p_sem"}],
    )
    build_one(overseer_db, paper_id=paper_id, inputs=inputs,
              build_run_id=brid, fencing_token=paper_token)

    report = verify_strict(overseer_db)
    failed = [c for c in report.checks if not c.passed]
    assert report.overall_passed, f"failed checks: {[(c.name, c.failures) for c in failed]}"
