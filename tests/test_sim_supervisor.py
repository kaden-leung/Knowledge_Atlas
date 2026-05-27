from __future__ import annotations

from pathlib import Path
import sqlite3

from sim_supervisor import status_report
from sim_supervisor import supervisor_db as sdb
from sim_supervisor import operational_truth as ot


def test_supervisor_registers_components_and_heartbeats(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_supervisor.db"
    sdb.register_component(
        component_id="scenario_engine",
        component_kind="engine",
        state="starting",
        expected_heartbeat_interval_seconds=30,
        db_path=db_path,
    )
    sdb.record_heartbeat(
        component_id="scenario_engine",
        state="running",
        progress_at="2026-05-25T00:00:05Z",
        db_path=db_path,
    )
    rows = sdb.component_rows(db_path=db_path)
    assert rows[0]["component_id"] == "scenario_engine"
    assert rows[0]["state"] == "running"
    assert rows[0]["last_heartbeat_observed_at"] is not None


def test_supervisor_tracks_decision_prompt_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_supervisor.db"
    sdb.raise_decision_prompt(
        decision_id="dec:test-1",
        scenario_name="drift_storm",
        decision_class="signature_drift_resolution",
        trigger_summary="Simulated drift detected",
        available_actions=["accept_new_signature", "roll_back_af", "escalate"],
        db_path=db_path,
    )
    sdb.acknowledge_decision_prompt("dec:test-1", db_path=db_path)
    sdb.answer_decision_prompt(
        "dec:test-1",
        chosen_action="accept_new_signature",
        rationale="Normal metadata correction.",
        db_path=db_path,
    )
    rows = sdb.decision_prompt_rows(db_path=db_path)
    assert rows[0]["state"] == "answered"
    assert rows[0]["chosen_action"] == "accept_new_signature"


def test_status_report_marks_stale_components(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_supervisor.db"
    sdb.register_component(
        component_id="reconciler_tick_runner",
        component_kind="runner",
        state="running",
        expected_heartbeat_interval_seconds=10,
        db_path=db_path,
    )
    sdb.record_heartbeat(
        component_id="reconciler_tick_runner",
        state="running",
        heartbeat_at="2026-05-25T00:00:00Z",
        progress_at="2026-05-25T00:00:00Z",
        db_path=db_path,
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE components
               SET last_heartbeat_observed_at='2026-05-25T00:00:00Z'
             WHERE component_id='reconciler_tick_runner'
            """
        )
        conn.commit()
    finally:
        conn.close()
    status = status_report.build_status(db_path=db_path, stale_multiplier=1)
    assert status["component_count"] == 1
    assert status["stale_components"]
    assert status["components"][0]["effective_state"] == "resume_required"
    assert any(row["action"] == "restart_or_resume_component" for row in status["attention_actions"])


def test_status_report_emits_attention_for_open_decision_prompt(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_supervisor.db"
    sdb.raise_decision_prompt(
        decision_id="dec:test-open",
        scenario_name="accept_then_drift",
        decision_class="signature_drift_resolution",
        trigger_summary="Unresolved signature drift detected",
        available_actions=["accept_new_signature", "roll_back_af"],
        db_path=db_path,
    )
    status = status_report.build_status(db_path=db_path)
    assert status["decision_prompt_count"] == 1
    assert status["attention_actions"]
    assert status["attention_actions"][0]["action"] == "answer_decision_prompt"


def test_operational_truth_flags_clock_skew() -> None:
    row = {
        "component_id": "scenario_engine",
        "component_kind": "engine",
        "state": "running",
        "expected_heartbeat_interval_seconds": 30,
        "last_heartbeat_at": "2026-05-25T00:00:00Z",
        "last_heartbeat_observed_at": "2026-05-25T01:00:00Z",
    }
    evaluated = ot.evaluate_component_row(row)
    assert evaluated["clock_skew_state"] == "suspected"
    assert evaluated["attention_actions"]
    assert any(row["policy_family"] == "heartbeat_integrity_policy" for row in evaluated["attention_actions"])


def test_status_report_carries_policy_family_on_component_attention(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_supervisor.db"
    sdb.register_component(
        component_id="reconciler_tick_runner",
        component_kind="runner",
        state="running",
        expected_heartbeat_interval_seconds=10,
        db_path=db_path,
    )
    sdb.record_heartbeat(
        component_id="reconciler_tick_runner",
        state="running",
        heartbeat_at="2026-05-25T00:00:00Z",
        progress_at="2026-05-25T00:00:00Z",
        db_path=db_path,
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE components
               SET last_heartbeat_at='2026-05-25T00:09:00Z',
                   last_heartbeat_observed_at='2026-05-25T00:10:00Z'
             WHERE component_id='reconciler_tick_runner'
            """
        )
        conn.commit()
    finally:
        conn.close()
    status = status_report.build_status(db_path=db_path, stale_multiplier=1)
    assert status["attention_actions"]
    assert any(row["policy_family"] == "worker_availability_policy" for row in status["attention_actions"])


def test_operational_truth_handles_missing_observed_heartbeat_as_attention() -> None:
    row = {
        "component_id": "scenario_engine",
        "component_kind": "engine",
        "state": "running",
        "expected_heartbeat_interval_seconds": 30,
        "last_heartbeat_at": "2026-05-25T00:00:00Z",
        "last_heartbeat_observed_at": None,
        "last_progress_at": "2026-05-25T00:00:00Z",
    }
    evaluated = ot.evaluate_component_row(row)
    assert evaluated["effective_state"] == "resume_required"
    assert any(row["action"] == "inspect_missing_observed_heartbeat" for row in evaluated["attention_actions"])


def test_operational_truth_does_not_crash_on_malformed_timestamps() -> None:
    row = {
        "component_id": "scenario_engine",
        "component_kind": "engine",
        "state": "running",
        "expected_heartbeat_interval_seconds": 30,
        "last_heartbeat_at": "not-a-time",
        "last_heartbeat_observed_at": "2026-05-25T00:00:00Z",
        "last_progress_at": "also-bad",
    }
    evaluated = ot.evaluate_component_row(row)
    assert evaluated["authored_heartbeat_timestamp_status"] == "malformed"
    assert any(row["policy_family"] == "heartbeat_integrity_policy" for row in evaluated["attention_actions"])


def test_operational_truth_preserves_multiple_fault_actions() -> None:
    row = {
        "component_id": "scenario_engine",
        "component_kind": "engine",
        "state": "failed",
        "expected_heartbeat_interval_seconds": 30,
        "last_heartbeat_at": "2026-05-25T00:00:00Z",
        "last_heartbeat_observed_at": "2026-05-25T01:00:00Z",
        "last_progress_at": "2026-05-25T00:00:00Z",
    }
    evaluated = ot.evaluate_component_row(row)
    families = {row["policy_family"] for row in evaluated["attention_actions"]}
    assert "component_health_policy" in families
    assert "heartbeat_integrity_policy" in families


def test_operational_truth_uses_dependency_wait_policy_for_stale_waiting_state() -> None:
    row = {
        "component_id": "operator_gate",
        "component_kind": "decision_gate",
        "state": "waiting_for_operator",
        "expected_heartbeat_interval_seconds": 10,
        "last_heartbeat_at": "2026-05-25T00:00:00Z",
        "last_heartbeat_observed_at": "2026-05-25T00:10:00Z",
        "last_progress_at": "2026-05-25T00:00:00Z",
    }
    evaluated = ot.evaluate_component_row(row, stale_after_intervals=1)
    assert evaluated["effective_state"] == "blocked_waiting"
    assert any(row["policy_family"] == "dependency_wait_policy" for row in evaluated["attention_actions"])


def test_decision_prompt_acknowledged_is_not_immediately_neglected() -> None:
    row = {
        "decision_id": "dec:test-open",
        "scenario_name": "accept_then_drift",
        "decision_class": "signature_drift_resolution",
        "state": "acknowledged",
        "raised_at": "2026-05-25T00:00:00Z",
        "acknowledged_at": ot.parse_iso("2026-05-25T00:00:00Z")[0].isoformat().replace("+00:00", "Z"),
    }
    evaluated = ot.evaluate_decision_prompt_row(row, acknowledged_grace_seconds=10**12)
    assert evaluated["attention_actions"] == []


def test_operational_truth_flags_future_timestamps() -> None:
    future_time = "2999-01-01T00:00:00Z"
    row = {
        "component_id": "scenario_engine",
        "component_kind": "engine",
        "state": "running",
        "expected_heartbeat_interval_seconds": 30,
        "last_heartbeat_at": future_time,
        "last_heartbeat_observed_at": future_time,
        "last_progress_at": future_time,
    }
    evaluated = ot.evaluate_component_row(row)
    assert evaluated["heartbeat_freshness_state"] == "future"
    assert any(action["action"] == "inspect_future_heartbeat_timestamp" for action in evaluated["attention_actions"])


def test_decision_prompt_bad_timestamp_still_emits_attention() -> None:
    row = {
        "decision_id": "dec:test-bad",
        "scenario_name": "accept_then_drift",
        "decision_class": "signature_drift_resolution",
        "state": "acknowledged",
        "raised_at": "bad-time",
        "acknowledged_at": None,
    }
    evaluated = ot.evaluate_decision_prompt_row(row)
    families = {action["policy_family"] for action in evaluated["attention_actions"]}
    assert "decision_integrity_policy" in families
    assert "decision_lifecycle_policy" in families


def test_decision_prompt_future_acknowledgement_keeps_lifecycle_action() -> None:
    row = {
        "decision_id": "dec:test-future",
        "scenario_name": "accept_then_drift",
        "decision_class": "signature_drift_resolution",
        "state": "acknowledged",
        "raised_at": "2026-05-25T00:00:00Z",
        "acknowledged_at": "2999-01-01T00:00:00Z",
    }
    evaluated = ot.evaluate_decision_prompt_row(row)
    families = {action["policy_family"] for action in evaluated["attention_actions"]}
    assert "decision_integrity_policy" in families
    assert "decision_lifecycle_policy" in families


def test_status_report_survives_bad_component_and_reports_run_id(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_supervisor.db"
    sdb.register_component(
        component_id="scenario_engine",
        component_kind="engine",
        state="running",
        expected_heartbeat_interval_seconds=30,
        current_run_id="run-1",
        db_path=db_path,
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE components
               SET last_heartbeat_at='bad-time',
                   last_heartbeat_observed_at='2026-05-25T00:00:00Z',
                   last_progress_at='bad-progress'
             WHERE component_id='scenario_engine'
            """
        )
        conn.commit()
    finally:
        conn.close()
    status = status_report.build_status(db_path=db_path)
    assert status["component_count"] == 1
    assert status["components"][0]["current_run_id"] == "run-1"
    assert status["components"][0]["authored_heartbeat_timestamp_status"] == "malformed"


def test_status_report_accepts_custom_state_profile(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_supervisor.db"
    sdb.register_component(
        component_id="custom_runner",
        component_kind="runner",
        state="active_now",
        expected_heartbeat_interval_seconds=30,
        db_path=db_path,
    )
    status = status_report.build_status(
        db_path=db_path,
        state_profile={
            "active": {"active_now"},
            "waiting": {"paused_now"},
            "terminal": {"done_now"},
            "degraded": {"broken_now"},
        },
    )
    assert status["components"][0]["state_family"] == "active"


def test_operational_truth_clock_skew_future_status_is_reachable() -> None:
    skew_state, skew_seconds = ot.clock_skew_state(
        authored_heartbeat_at="2999-01-01T00:00:00Z",
        observed_heartbeat_at="2999-01-01T00:00:00Z",
    )
    assert skew_state == "future"
    assert skew_seconds is None


def test_terminal_component_is_not_listed_as_stale(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_supervisor.db"
    sdb.register_component(
        component_id="finished_runner",
        component_kind="runner",
        state="completed",
        expected_heartbeat_interval_seconds=10,
        db_path=db_path,
    )
    sdb.record_heartbeat(
        component_id="finished_runner",
        state="completed",
        heartbeat_at="2026-05-25T00:00:00Z",
        progress_at="2026-05-25T00:00:00Z",
        db_path=db_path,
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE components
               SET last_heartbeat_observed_at='2026-05-25T00:10:00Z'
             WHERE component_id='finished_runner'
            """
        )
        conn.commit()
    finally:
        conn.close()
    status = status_report.build_status(db_path=db_path, stale_multiplier=1)
    assert status["stale_components"] == []


def test_progress_truth_uses_custom_progress_interval() -> None:
    now = sdb.utc_now_iso()
    row = {
        "component_id": "slow_runner",
        "component_kind": "runner",
        "state": "running",
        "expected_heartbeat_interval_seconds": 10,
        "last_heartbeat_at": now,
        "last_heartbeat_observed_at": now,
        "last_progress_at": now,
        "details_json": "{\"expected_progress_interval_seconds\": 3600}",
    }
    evaluated = ot.evaluate_component_row(row)
    assert evaluated["progress_expected_interval_seconds"] == 3600
    assert evaluated["progress_freshness_state"] in {"fresh", "late"}


def test_attention_actions_are_sorted_by_severity(tmp_path: Path) -> None:
    db_path = tmp_path / "sim_supervisor.db"
    sdb.register_component(
        component_id="broken_runner",
        component_kind="runner",
        state="failed",
        expected_heartbeat_interval_seconds=10,
        db_path=db_path,
    )
    sdb.record_heartbeat(
        component_id="broken_runner",
        state="failed",
        heartbeat_at="2026-05-25T00:00:00Z",
        progress_at="2026-05-25T00:00:00Z",
        db_path=db_path,
    )
    sdb.raise_decision_prompt(
        decision_id="dec:test-open",
        scenario_name="accept_then_drift",
        decision_class="signature_drift_resolution",
        trigger_summary="Unresolved signature drift detected",
        available_actions=["accept_new_signature", "roll_back_af"],
        db_path=db_path,
    )
    status = status_report.build_status(db_path=db_path)
    severities = [row["severity"] for row in status["attention_actions"]]
    assert severities == sorted(severities, key=lambda sev: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(sev, 99))
