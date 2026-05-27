"""Render a compact supervisor status surface for the simulator apparatus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sim_supervisor import operational_truth as ot
from sim_supervisor import supervisor_db as sdb


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "data" / "sim" / "supervisor_reports"
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def build_status(
    *,
    db_path: str | Path | None = None,
    stale_multiplier: int = 5,
    state_profile: dict[str, set[str]] | None = None,
    late_after_intervals: int = 1,
    decision_raised_grace_seconds: int = 300,
    decision_acknowledged_grace_seconds: int = 900,
) -> dict[str, Any]:
    components = sdb.component_rows(db_path=db_path)
    decisions = sdb.decision_prompt_rows(db_path=db_path)
    by_state: dict[str, int] = {}
    effective_by_state: dict[str, int] = {}
    stale_components: list[dict[str, Any]] = []
    attention_actions: list[dict[str, Any]] = []
    component_views: list[dict[str, Any]] = []
    for row in components:
        state = str(row.get("state") or "unknown")
        by_state[state] = by_state.get(state, 0) + 1
        component_view = ot.evaluate_component_row(
            row,
            state_profile=state_profile,
            late_after_intervals=late_after_intervals,
            stale_after_intervals=stale_multiplier,
        )
        age = component_view["heartbeat_age_seconds"]
        freshness_state = str(component_view["heartbeat_freshness_state"])
        effective_state = str(component_view["effective_state"])
        effective_by_state[effective_state] = effective_by_state.get(effective_state, 0) + 1
        component_views.append(component_view)
        if freshness_state == "stale" and component_view.get("state_class") != "terminal":
            stale_components.append(
                {
                    "component_id": row["component_id"],
                    "state": state,
                    "effective_state": effective_state,
                    "heartbeat_age_seconds": age,
                    "expected_interval_seconds": int(row.get("expected_heartbeat_interval_seconds") or 0),
                }
            )
        attention_actions.extend(component_view.get("attention_actions", []))
    decision_by_state: dict[str, int] = {}
    decision_views: list[dict[str, Any]] = []
    for row in decisions:
        state = str(row.get("state") or "unknown")
        decision_by_state[state] = decision_by_state.get(state, 0) + 1
        evaluated = ot.evaluate_decision_prompt_row(
            row,
            raised_grace_seconds=decision_raised_grace_seconds,
            acknowledged_grace_seconds=decision_acknowledged_grace_seconds,
        )
        decision_views.append(evaluated)
        attention_actions.extend(evaluated.get("attention_actions", []))
    attention_actions.sort(
        key=lambda row: (
            SEVERITY_ORDER.get(str(row.get("severity") or "low"), 99),
            str(row.get("scope") or ""),
            str(row.get("component_id") or row.get("decision_id") or ""),
        )
    )
    return {
        "generated_at": sdb.utc_now_iso(),
        "component_count": len(components),
        "component_state_counts": by_state,
        "component_effective_state_counts": effective_by_state,
        "stale_components": stale_components,
        "decision_prompt_count": len(decisions),
        "decision_prompt_state_counts": decision_by_state,
        "attention_actions": attention_actions,
        "components": component_views,
        "decision_prompts": decision_views,
    }


def render_markdown(status: dict[str, Any]) -> str:
    lines = [
        "# Simulator Supervisor Status",
        "",
        f"- generated_at: `{status['generated_at']}`",
        f"- component_count: `{status['component_count']}`",
        f"- decision_prompt_count: `{status['decision_prompt_count']}`",
        f"- component_state_counts: `{status.get('component_state_counts', {})}`",
        f"- component_effective_state_counts: `{status.get('component_effective_state_counts', {})}`",
        f"- decision_prompt_state_counts: `{status.get('decision_prompt_state_counts', {})}`",
        "",
        "## Act Now",
    ]
    actions = status.get("attention_actions", [])
    if not actions:
        lines.append("- none")
    else:
        for row in actions:
            subject = row.get("component_id") or row.get("decision_id") or "unknown"
            lines.append(
                f"- `{subject}` severity=`{row['severity']}` action=`{row['action']}` reason=`{row['reason']}`"
            )
    lines.extend([
        "",
        "## Stale Components",
    ])
    stale = status.get("stale_components", [])
    if not stale:
        lines.append("- none")
    else:
        for row in stale:
            lines.append(
                f"- `{row['component_id']}` state=`{row['state']}` "
                f"heartbeat_age_seconds=`{row['heartbeat_age_seconds']}` "
                f"expected_interval_seconds=`{row['expected_interval_seconds']}`"
            )
    lines.extend(["", "## Components"])
    for row in status.get("components", []):
        lines.append(
            f"- `{row['component_id']}` kind=`{row['component_kind']}` "
            f"state=`{row['state']}` effective_state=`{row.get('effective_state')}` "
            f"run_id=`{row.get('current_run_id')}` "
            f"heartbeat_freshness_state=`{row.get('heartbeat_freshness_state')}` "
            f"progress_freshness_state=`{row.get('progress_freshness_state')}` "
            f"clock_skew_state=`{row.get('clock_skew_state')}` "
            f"last_heartbeat_observed_at=`{row.get('last_heartbeat_observed_at')}`"
        )
    lines.extend(["", "## Decision Prompts"])
    prompts = status.get("decision_prompts", [])
    if not prompts:
        lines.append("- none")
    else:
        for row in prompts:
            lines.append(
                f"- `{row['decision_id']}` scenario=`{row['scenario_name']}` "
                f"class=`{row['decision_class']}` state=`{row['state']}` "
                f"raised_age_seconds=`{row.get('raised_age_seconds')}` "
                f"acknowledged_age_seconds=`{row.get('acknowledged_age_seconds')}`"
            )
    return "\n".join(lines) + "\n"


def write_reports(
    *,
    db_path: str | Path | None = None,
    stale_multiplier: int = 5,
    state_profile: dict[str, set[str]] | None = None,
    late_after_intervals: int = 1,
    decision_raised_grace_seconds: int = 300,
    decision_acknowledged_grace_seconds: int = 900,
) -> dict[str, str]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    status = build_status(
        db_path=db_path,
        stale_multiplier=stale_multiplier,
        state_profile=state_profile,
        late_after_intervals=late_after_intervals,
        decision_raised_grace_seconds=decision_raised_grace_seconds,
        decision_acknowledged_grace_seconds=decision_acknowledged_grace_seconds,
    )
    json_path = REPORT_DIR / "latest.json"
    md_path = REPORT_DIR / "latest.md"
    act_now_json_path = REPORT_DIR / "ACT_NOW.json"
    act_now_md_path = REPORT_DIR / "ACT_NOW.md"
    json_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(status), encoding="utf-8")
    act_now = {
        "generated_at": status["generated_at"],
        "count": len(status.get("attention_actions", [])),
        "actions": status.get("attention_actions", []),
    }
    act_now_json_path.write_text(json.dumps(act_now, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    act_now_md_path.write_text(
        "# Simulator Supervisor Act Now\n\n"
        + ("\n".join(
            f"- `{(row.get('component_id') or row.get('decision_id') or 'unknown')}` "
            f"severity=`{row['severity']}` action=`{row['action']}` reason=`{row['reason']}`"
            for row in act_now["actions"]
        ) if act_now["actions"] else "- none")
        + "\n",
        encoding="utf-8",
    )
    return {
        "json": str(json_path),
        "md": str(md_path),
        "act_now_json": str(act_now_json_path),
        "act_now_md": str(act_now_md_path),
    }
