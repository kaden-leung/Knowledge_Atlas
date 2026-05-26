from __future__ import annotations

import sqlite3
from pathlib import Path

from sim import scenarios
from sim import simulator_runner
from sim_supervisor import supervisor_db as sdb


def test_run_accept_wave_creates_pending_sync_events(tmp_path: Path) -> None:
    summary = simulator_runner.run_scenario(
        scenario=scenarios.accept_wave(count=3, duration_seconds=30),
        sim_af_db_path=tmp_path / "sim_af.db",
        sim_ka_db_path=tmp_path / "sim_ka.db",
        supervisor_db_path=tmp_path / "sim_supervisor.db",
    )
    assert summary.event_count == 3
    assert summary.reconciler_ticks == 3
    assert summary.inserted_pending == 3

    conn = sqlite3.connect(summary.sim_ka_db_path)
    try:
        pending = conn.execute(
            "SELECT COUNT(*) FROM cross_db_sync_events WHERE status = 'pending'"
        ).fetchone()[0]
        candidates = conn.execute(
            "SELECT COUNT(*) FROM artefact_registry WHERE kind = 'article_finder_candidate' AND active = 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert pending == 3
    assert candidates == 3

    components = sdb.component_rows(db_path=summary.supervisor_db_path)
    assert {row["component_id"] for row in components} == {
        simulator_runner.SCENARIO_ENGINE_COMPONENT,
        simulator_runner.RECONCILER_COMPONENT,
    }


def test_run_drift_title_raises_signature_drift_decision_prompt(tmp_path: Path) -> None:
    simulator_runner.run_scenario(
        scenario=scenarios.accept_wave(count=1, duration_seconds=1),
        sim_af_db_path=tmp_path / "sim_af.db",
        sim_ka_db_path=tmp_path / "sim_ka.db",
        supervisor_db_path=tmp_path / "sim_supervisor.db",
    )
    scenario = scenarios.SimScenario(
        name="drift_replay",
        description="Single drift event after initial sync.",
        events=(
            scenarios.SimEvent(
                event_id="sim:drift-one",
                at_offset_seconds=1,
                kind="drift_title",
                paper_id="SIM-AF-0001",
                payload={"title": "Revised simulated title"},
            ),
        ),
    )
    summary = simulator_runner.run_scenario(
        scenario=scenario,
        sim_af_db_path=tmp_path / "sim_af.db",
        sim_ka_db_path=tmp_path / "sim_ka.db",
        supervisor_db_path=tmp_path / "sim_supervisor.db",
    )
    assert summary.flagged_unresolved == 1
    prompts = sdb.decision_prompt_rows(db_path=summary.supervisor_db_path)
    assert any(row["decision_class"] == "signature_drift_resolution" for row in prompts)


def test_run_scenario_with_reset_databases_clears_prior_decision_prompts(tmp_path: Path) -> None:
    supervisor_db_path = tmp_path / "sim_supervisor.db"
    sdb.raise_decision_prompt(
        decision_id="dec:old",
        scenario_name="old",
        decision_class="old_class",
        trigger_summary="old prompt",
        available_actions=["noop"],
        db_path=supervisor_db_path,
    )
    summary = simulator_runner.run_scenario(
        scenario=scenarios.accept_wave(count=1, duration_seconds=1),
        sim_af_db_path=tmp_path / "sim_af.db",
        sim_ka_db_path=tmp_path / "sim_ka.db",
        supervisor_db_path=supervisor_db_path,
        reset_databases=True,
    )
    prompts = sdb.decision_prompt_rows(db_path=summary.supervisor_db_path)
    assert prompts == []


def test_accept_then_drift_raises_multiple_signature_drift_prompts(tmp_path: Path) -> None:
    summary = simulator_runner.run_scenario(
        scenario=scenarios.accept_then_drift(count=3, accept_duration_seconds=3, drift_lag_seconds=5),
        sim_af_db_path=tmp_path / "sim_af.db",
        sim_ka_db_path=tmp_path / "sim_ka.db",
        supervisor_db_path=tmp_path / "sim_supervisor.db",
        reset_databases=True,
    )
    assert summary.flagged_unresolved == 3
    prompts = sdb.decision_prompt_rows(db_path=summary.supervisor_db_path)
    drift_prompts = [row for row in prompts if row["decision_class"] == "signature_drift_resolution"]
    assert len(drift_prompts) == 3
