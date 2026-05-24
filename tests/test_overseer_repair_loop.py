"""Tests for overseer.repair_loop."""

from __future__ import annotations

from overseer.artefact_registry import mark_stale, register
from overseer.completion_queue import enqueue as cq_enqueue
from overseer.repair_loop import (
    RepairAction,
    can_promote,
    execute,
    route,
    route_and_execute,
)
from overseer.verifier_data import CheckResult, VerificationReport, verify_strict


def test_route_returns_empty_for_passed_check():
    c = CheckResult(name="any", passed=True, failures=[])
    assert route(c) == []


def test_route_maps_kind_registration_failure_to_blocking_completion():
    c = CheckResult(
        name="kind_registration", passed=False,
        failures=[{"artefact_id": "a", "kind": "rogue"}],
    )
    actions = route(c)
    assert len(actions) == 1
    assert actions[0].kind == "enqueue_completion"
    assert actions[0].severity == "blocking"
    assert actions[0].reason == "unregistered_artefact_kind"


def test_route_maps_hash_presence_failure_to_rebuild(overseer_db):
    c = CheckResult(
        name="hash_presence_on_fresh_artefacts", passed=False,
        failures=[{"artefact_id": "a"}],
    )
    actions = route(c)
    assert actions[0].kind == "enqueue_rebuild"
    assert actions[0].severity == "high"


def test_execute_enqueue_completion_creates_row(overseer_db):
    action = RepairAction(
        kind="enqueue_completion", artefact_id=None,
        reason="test_reason", severity="medium",
    )
    qid = execute(overseer_db, action)
    assert qid is not None
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM completion_queue WHERE queue_id = ?", (qid,)
    ).fetchone()[0]
    assert n == 1


def test_execute_enqueue_rebuild_requires_existing_artefact(overseer_db):
    a = register(overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-R",
                 field_path=None, schema_version="pnu_row.v1")
    action = RepairAction(
        kind="enqueue_rebuild", artefact_id=a.artefact_id,
        reason="test", severity="medium",
    )
    qid = execute(overseer_db, action)
    assert qid is not None
    assert qid.startswith("q:")


def test_route_and_execute_handles_full_report(overseer_db):
    # Create a verifier failure (kind_registration) by registering an unregistered kind.
    register(overseer_db, kind="rogue", entity_type="p", entity_id="P",
             field_path=None, schema_version="v1")
    report = verify_strict(overseer_db)
    assert not report.overall_passed
    qids = route_and_execute(overseer_db, report)
    assert len(qids) >= 1


# ----------------------------------------------------------------------------
# Release gate (can_promote)
# ----------------------------------------------------------------------------

def test_can_promote_allows_when_clean(overseer_db):
    report = verify_strict(overseer_db)
    allowed, reasons = can_promote(overseer_db, report)
    assert allowed
    assert reasons == []


def test_can_promote_blocks_when_verifier_fails(overseer_db):
    register(overseer_db, kind="rogue_kind", entity_type="p", entity_id="P",
             field_path=None, schema_version="v1")
    report = verify_strict(overseer_db)
    allowed, reasons = can_promote(overseer_db, report)
    assert not allowed
    assert any("verifier:" in r for r in reasons)


def test_can_promote_blocks_when_stale_artefacts_present(overseer_db):
    # Seed a registered kind so kind_registration passes, then mark a freshly
    # built artefact as stale.
    overseer_db.execute(
        "INSERT INTO artefact_kinds (kind_name, owner_pipeline, support_rule_module, "
        "schema_version, active, created_at) VALUES ('pnu_row', 'p', 'm', 'v1', 1, '2026-05-23T00:00:00Z')"
    )
    a = register(overseer_db, kind="pnu_row", entity_type="pnu", entity_id="PNU-S",
                 field_path=None, schema_version="pnu_row.v1")
    mark_stale(overseer_db, a.artefact_id)
    report = verify_strict(overseer_db)
    allowed, reasons = can_promote(overseer_db, report)
    assert not allowed
    assert any("stale_required_artefacts:" in r for r in reasons)


def test_can_promote_blocks_when_blocking_completion_open(overseer_db):
    cq_enqueue(overseer_db, reason="block_test", severity="blocking")
    report = verify_strict(overseer_db)
    allowed, reasons = can_promote(overseer_db, report)
    assert not allowed
    assert "completion_queue:blocking_open" in reasons
