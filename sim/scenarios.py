"""Scenario library for dependency-overseer AF traffic simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid


@dataclass(frozen=True)
class SimEvent:
    event_id: str
    at_offset_seconds: int
    kind: str
    paper_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class SimScenario:
    name: str
    description: str
    events: tuple[SimEvent, ...]


def _event(kind: str, paper_id: str, at_offset_seconds: int, payload: dict[str, Any]) -> SimEvent:
    return SimEvent(
        event_id=f"sim:{uuid.uuid4().hex}",
        at_offset_seconds=at_offset_seconds,
        kind=kind,
        paper_id=paper_id,
        payload=dict(payload),
    )


def accept_wave(*, count: int = 100, duration_seconds: int = 30 * 60) -> SimScenario:
    spacing = max(1, duration_seconds // max(1, count))
    events = []
    for idx in range(count):
        paper_id = f"SIM-AF-{idx + 1:04d}"
        events.append(
            _event(
                "flip_intake",
                paper_id,
                idx * spacing,
                {"atlas_intake_decision": "accept_candidate"},
            )
        )
    return SimScenario(
        name="accept_wave",
        description=(
            "Over a compressed 30-minute simulated period, a wave of AF papers "
            "flip to atlas_intake_decision='accept_candidate'. This exercises "
            "the reconciler bridge and the article_finder_candidate build path."
        ),
        events=tuple(events),
    )


def steady_inflow(*, count: int = 50, workday_seconds: int = 8 * 60 * 60) -> SimScenario:
    spacing = max(1, workday_seconds // max(1, count))
    events = []
    for idx in range(count):
        paper_id = f"SIM-INFLOW-{idx + 1:04d}"
        events.append(
            _event(
                "new_candidate",
                paper_id,
                idx * spacing,
                {"status": "candidate", "title": f"Simulated inflow paper {idx + 1}"},
            )
        )
        if idx % 5 == 0:
            events.append(
                _event(
                    "flip_intake",
                    paper_id,
                    min(workday_seconds - 1, idx * spacing + 2 * 60 * 60),
                    {"atlas_intake_decision": "accept_candidate"},
                )
            )
    return SimScenario(
        name="steady_inflow",
        description=(
            "A workday-scale inflow of new candidates with a minority later "
            "reaching accept_candidate. This exercises rates and stuck-paper logic."
        ),
        events=tuple(sorted(events, key=lambda ev: (ev.at_offset_seconds, ev.paper_id))),
    )


def drift_storm(*, count: int = 12, duration_seconds: int = 5 * 60) -> SimScenario:
    spacing = max(1, duration_seconds // max(1, count))
    events = []
    for idx in range(count):
        paper_id = f"SIM-DRIFT-{idx + 1:04d}"
        events.append(
            _event(
                "drift_title",
                paper_id,
                idx * spacing,
                {"title": f"Publisher-corrected title {idx + 1}"},
            )
        )
    return SimScenario(
        name="drift_storm",
        description=(
            "Multiple previously synced papers receive title changes in quick "
            "succession, exercising signature-drift detection and operator triage."
        ),
        events=tuple(events),
    )


def accept_then_drift(*, count: int = 12, accept_duration_seconds: int = 5 * 60, drift_lag_seconds: int = 10 * 60) -> SimScenario:
    """Accept a set of papers, then drift their titles later.

    This is the first scenario deliberately intended to produce unresolved
    signature drift and operator decision prompts in the simulator UI.
    """
    spacing = max(1, accept_duration_seconds // max(1, count))
    events = []
    for idx in range(count):
        paper_id = f"SIM-DRIFT-{idx + 1:04d}"
        accepted_at = idx * spacing
        events.append(
            _event(
                "flip_intake",
                paper_id,
                accepted_at,
                {
                    "atlas_intake_decision": "accept_candidate",
                    "title": f"Stable accepted title {idx + 1}",
                },
            )
        )
        events.append(
            _event(
                "drift_title",
                paper_id,
                accepted_at + drift_lag_seconds,
                {"title": f"Publisher-corrected title {idx + 1}"},
            )
        )
    return SimScenario(
        name="accept_then_drift",
        description=(
            "A set of papers is first accepted into the AF→KA bridge and then, "
            "after a delay, their titles drift. This produces unresolved "
            "signature-drift events and operator decision prompts."
        ),
        events=tuple(sorted(events, key=lambda ev: (ev.at_offset_seconds, ev.paper_id))),
    )


def cascade_spike(*, dependent_count: int = 150) -> SimScenario:
    return SimScenario(
        name="cascade_spike",
        description=(
            "A single source artefact change implies a large dependent rebuild set, "
            "exercising cascade-bound and batch-rebuild decision logic."
        ),
        events=(
            _event(
                "source_hash_change",
                "SIM-CASCADE-SOURCE-0001",
                0,
                {"dependent_count": dependent_count},
            ),
        ),
    )


def pipeline_jam(*, count: int = 25, jam_after_days: int = 7) -> SimScenario:
    events = []
    for idx in range(count):
        paper_id = f"SIM-JAM-{idx + 1:04d}"
        events.append(
            _event(
                "flip_intake",
                paper_id,
                idx * 60,
                {"atlas_intake_decision": "needs_pdf_text"},
            )
        )
        events.append(
            _event(
                "stuck_paper_threshold",
                paper_id,
                jam_after_days * 24 * 60 * 60 + idx * 60,
                {"reason": "needs_pdf_text_past_threshold"},
            )
        )
    return SimScenario(
        name="pipeline_jam",
        description=(
            "Papers accumulate in needs_pdf_text and age past the stuck-paper "
            "threshold, exercising runbook triage rather than simple throughput."
        ),
        events=tuple(events),
    )


def scenario_library() -> dict[str, SimScenario]:
    scenarios = [
        steady_inflow(),
        accept_wave(),
        accept_then_drift(),
        drift_storm(),
        cascade_spike(),
        pipeline_jam(),
    ]
    return {scenario.name: scenario for scenario in scenarios}
