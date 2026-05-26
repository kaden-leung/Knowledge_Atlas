from __future__ import annotations

from sim import scenarios


def test_accept_wave_builds_expected_number_of_events() -> None:
    scenario = scenarios.accept_wave(count=10, duration_seconds=100)
    assert scenario.name == "accept_wave"
    assert len(scenario.events) == 10
    assert scenario.events[0].kind == "flip_intake"
    assert scenario.events[-1].payload["atlas_intake_decision"] == "accept_candidate"


def test_scenario_library_contains_named_scenarios() -> None:
    library = scenarios.scenario_library()
    assert {"steady_inflow", "accept_wave", "accept_then_drift", "drift_storm", "cascade_spike", "pipeline_jam"} <= set(library)


def test_accept_then_drift_contains_both_accept_and_drift_events() -> None:
    scenario = scenarios.accept_then_drift(count=2, accept_duration_seconds=10, drift_lag_seconds=20)
    assert scenario.name == "accept_then_drift"
    assert len(scenario.events) == 4
    assert scenario.events[0].kind == "flip_intake"
    assert any(event.kind == "drift_title" for event in scenario.events)
