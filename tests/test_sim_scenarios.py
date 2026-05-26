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
    assert {"steady_inflow", "accept_wave", "drift_storm", "cascade_spike", "pipeline_jam"} <= set(library)

