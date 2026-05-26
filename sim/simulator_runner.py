"""Run AF traffic scenarios against simulator-only AF and KA databases."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from overseer.article_finder_reconciler import tick as reconciler_tick
from overseer.ids import utc_now_iso
from sim import scenarios
from sim import sim_af_db
from sim import sim_ka_db
from sim_supervisor import supervisor_db as sdb


SCENARIO_ENGINE_COMPONENT = "scenario_engine"
RECONCILER_COMPONENT = "reconciler_tick_runner"


@dataclass(frozen=True)
class ScenarioRunSummary:
    scenario_name: str
    event_count: int
    reconciler_ticks: int
    inserted_pending: int
    upgraded_to_matched: int
    flagged_unresolved: int
    skipped_already_matched: int
    decision_prompts_raised: int
    sim_af_db_path: str
    sim_ka_db_path: str
    supervisor_db_path: str


def _paper_stub(paper_id: str, *, title: str | None = None) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "paper_id": paper_id,
        "doi": None,
        "title": title or f"Simulated paper {paper_id}",
        "canonical_paper_id": paper_id,
        "status": "candidate",
        "atlas_intake_decision": None,
        "ae_corpus_match_status": None,
        "updated_at": now,
        "created_at": now,
        "source": "dependency_overseer_simulator",
        "abstract": None,
        "pdf_path": None,
        "pdf_sha256": None,
        "ae_run_id": None,
        "atlas_primary_topic": None,
    }


def _fetch_paper(conn: sqlite3.Connection, paper_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
    return dict(row) if row is not None else None


def apply_event(
    event: scenarios.SimEvent,
    *,
    sim_af_db_path: str | Path | None = None,
    supervisor_db_path: str | Path | None = None,
    scenario_name: str | None = None,
    sim_elapsed_seconds: int | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    decision_prompts_raised = 0
    applied_kind = event.kind
    conn = sim_af_db.connect_sim_af(sim_af_db_path)
    try:
        if event.kind == "new_candidate":
            row = _paper_stub(event.paper_id, title=str(event.payload.get("title") or f"Simulated inflow paper {event.paper_id}"))
            row["status"] = str(event.payload.get("status") or "candidate")
            sim_af_db.upsert_papers([row], db_path=sim_af_db_path)
        elif event.kind == "flip_intake":
            row = _fetch_paper(conn, event.paper_id) or _paper_stub(event.paper_id)
            row["atlas_intake_decision"] = event.payload.get("atlas_intake_decision")
            row["status"] = str(event.payload.get("status") or row.get("status") or "processed_partial")
            row["updated_at"] = now
            sim_af_db.upsert_papers([row], db_path=sim_af_db_path)
        elif event.kind == "drift_title":
            row = _fetch_paper(conn, event.paper_id) or _paper_stub(event.paper_id)
            row["title"] = str(event.payload.get("title") or row.get("title") or f"Drifted title {event.paper_id}")
            row["updated_at"] = now
            sim_af_db.upsert_papers([row], db_path=sim_af_db_path)
        elif event.kind == "source_hash_change":
            sdb.raise_decision_prompt(
                decision_id=f"dec:{event.event_id}",
                scenario_name=scenario_name or "unknown",
                decision_class="cascade_bound_review",
                trigger_event_id=event.event_id,
                trigger_summary=f"Source hash change implies {event.payload.get('dependent_count')} dependent rebuilds.",
                available_actions=["approve_bounded_rebuild", "delay_rebuild", "inspect_dependency_span"],
                dashboard_widget="cascade_spike",
                runbook_section="Phase3/Cascade Bound",
                sim_elapsed_seconds=sim_elapsed_seconds,
                details={"paper_id": event.paper_id, **event.payload},
                db_path=supervisor_db_path,
            )
            decision_prompts_raised += 1
        elif event.kind == "stuck_paper_threshold":
            sdb.raise_decision_prompt(
                decision_id=f"dec:{event.event_id}",
                scenario_name=scenario_name or "unknown",
                decision_class="stuck_paper_triage",
                trigger_event_id=event.event_id,
                trigger_summary=f"Paper {event.paper_id} crossed the stuck-paper threshold.",
                available_actions=["open_triage", "waive_temporarily", "escalate_pdf_repair"],
                dashboard_widget="stuck_papers",
                runbook_section="Phase3/Stuck Paper Triage",
                sim_elapsed_seconds=sim_elapsed_seconds,
                details={"paper_id": event.paper_id, **event.payload},
                db_path=supervisor_db_path,
            )
            decision_prompts_raised += 1
        else:
            raise ValueError(f"unsupported simulated event kind: {event.kind}")
    finally:
        conn.close()
    return {
        "event_id": event.event_id,
        "kind": applied_kind,
        "paper_id": event.paper_id,
        "decision_prompts_raised": decision_prompts_raised,
    }


def run_scenario(
    *,
    scenario: scenarios.SimScenario,
    sim_af_db_path: str | Path | None = None,
    sim_ka_db_path: str | Path | None = None,
    supervisor_db_path: str | Path | None = None,
    reset_databases: bool = False,
) -> ScenarioRunSummary:
    sim_af_path = sim_af_db.resolve_sim_af_db_path(sim_af_db_path)
    sim_ka_path = sim_ka_db.resolve_sim_ka_db_path(sim_ka_db_path)
    supervisor_path = sdb.resolve_db_path(supervisor_db_path)
    if reset_databases:
        for path in (sim_af_path, sim_ka_path, supervisor_path):
            if path.exists():
                path.unlink()
    sim_af_path = sim_af_db.init_sim_af_db(sim_af_path)
    sim_ka_path = sim_ka_db.init_sim_ka_db(sim_ka_path)
    supervisor_path = sdb.init_db(supervisor_path)

    sdb.register_component(
        component_id=SCENARIO_ENGINE_COMPONENT,
        component_kind="scenario_engine",
        state="running",
        expected_heartbeat_interval_seconds=30,
        current_run_id=scenario.name,
        details={"scenario_name": scenario.name},
        db_path=supervisor_path,
    )
    sdb.register_component(
        component_id=RECONCILER_COMPONENT,
        component_kind="reconciler_tick_runner",
        state="idle",
        expected_heartbeat_interval_seconds=30,
        current_run_id=scenario.name,
        details={"scenario_name": scenario.name},
        db_path=supervisor_path,
    )

    reconciler_ticks = 0
    inserted_pending = 0
    upgraded_to_matched = 0
    flagged_unresolved = 0
    skipped_already_matched = 0
    decision_prompts_raised = 0

    for event in sorted(scenario.events, key=lambda ev: (ev.at_offset_seconds, ev.paper_id, ev.event_id)):
        sdb.record_heartbeat(
            component_id=SCENARIO_ENGINE_COMPONENT,
            state="running",
            progress_at=utc_now_iso(),
            details={
                "scenario_name": scenario.name,
                "event_id": event.event_id,
                "event_kind": event.kind,
                "paper_id": event.paper_id,
                "sim_elapsed_seconds": event.at_offset_seconds,
            },
            db_path=supervisor_path,
        )
        applied = apply_event(
            event,
            sim_af_db_path=sim_af_path,
            supervisor_db_path=supervisor_path,
            scenario_name=scenario.name,
            sim_elapsed_seconds=event.at_offset_seconds,
        )
        decision_prompts_raised += int(applied["decision_prompts_raised"])

        if event.kind in {"new_candidate", "flip_intake", "drift_title"}:
            sdb.record_heartbeat(
                component_id=RECONCILER_COMPONENT,
                state="running",
                progress_at=utc_now_iso(),
                details={"trigger_event_id": event.event_id, "paper_id": event.paper_id},
                db_path=supervisor_path,
            )
            ka_conn = sim_ka_db.connect_sim_ka(sim_ka_path)
            af_conn = sim_af_db.connect_sim_af(sim_af_path)
            try:
                report = reconciler_tick(
                    ka_conn,
                    af_conn=af_conn,
                    accepted_filter=None,
                    accepted_intake_decision="accept_candidate",
                )
            finally:
                af_conn.close()
                ka_conn.close()
            reconciler_ticks += 1
            inserted_pending += report.inserted_pending
            upgraded_to_matched += report.upgraded_to_matched
            flagged_unresolved += report.flagged_unresolved
            skipped_already_matched += report.skipped_already_matched
            sdb.record_heartbeat(
                component_id=RECONCILER_COMPONENT,
                state="idle",
                progress_at=utc_now_iso(),
                details={"trigger_event_id": event.event_id, "report": asdict(report)},
                db_path=supervisor_path,
            )
            if report.flagged_unresolved:
                sdb.raise_decision_prompt(
                    decision_id=f"dec:{event.event_id}:signature_drift",
                    scenario_name=scenario.name,
                    decision_class="signature_drift_resolution",
                    trigger_event_id=event.event_id,
                    trigger_summary=(
                        f"Reconciler flagged unresolved signature drift for paper {event.paper_id}."
                    ),
                    available_actions=["accept_new_signature", "roll_back_af", "escalate_manual_reconcile"],
                    dashboard_widget="drift_events",
                    runbook_section="Phase3/Signature Drift",
                    sim_elapsed_seconds=event.at_offset_seconds,
                    details={"paper_id": event.paper_id, "report": asdict(report)},
                    db_path=supervisor_path,
                )
                decision_prompts_raised += 1

    sdb.transition_component(
        component_id=RECONCILER_COMPONENT,
        to_state="completed",
        reason="scenario_complete",
        details={"scenario_name": scenario.name, "reconciler_ticks": reconciler_ticks},
        db_path=supervisor_path,
    )
    sdb.transition_component(
        component_id=SCENARIO_ENGINE_COMPONENT,
        to_state="completed",
        reason="scenario_complete",
        details={"scenario_name": scenario.name, "event_count": len(scenario.events)},
        db_path=supervisor_path,
    )

    return ScenarioRunSummary(
        scenario_name=scenario.name,
        event_count=len(scenario.events),
        reconciler_ticks=reconciler_ticks,
        inserted_pending=inserted_pending,
        upgraded_to_matched=upgraded_to_matched,
        flagged_unresolved=flagged_unresolved,
        skipped_already_matched=skipped_already_matched,
        decision_prompts_raised=decision_prompts_raised,
        sim_af_db_path=str(sim_af_path),
        sim_ka_db_path=str(sim_ka_path),
        supervisor_db_path=str(supervisor_path),
    )
