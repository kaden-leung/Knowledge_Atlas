from __future__ import annotations

from pathlib import Path
import sqlite3

from sim_supervisor import status_report
from sim_supervisor import supervisor_db as sdb


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
    assert status["attention_actions"][0]["action"] == "restart_or_resume_component"


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
