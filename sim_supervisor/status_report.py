"""Render a compact supervisor status surface for the simulator apparatus."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sim_supervisor import supervisor_db as sdb


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "data" / "sim" / "supervisor_reports"
ACTIVE_COMPONENT_STATES = {"starting", "running"}
WAITING_COMPONENT_STATES = {"idle", "waiting_for_operator", "decision_pending"}
TERMINAL_COMPONENT_STATES = {"completed", "standing_down", "disabled"}
DEGRADED_COMPONENT_STATES = {"failed", "stuck", "degraded"}


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _seconds_since(ts: str | None) -> float | None:
    dt = _parse_iso(ts)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _freshness_state(*, age: float | None, interval: int) -> str:
    if age is None or interval <= 0:
        return "unknown"
    if age <= interval:
        return "fresh"
    if age <= interval * 5:
        return "late"
    return "stale"


def _component_effective_state(raw_state: str, freshness_state: str) -> str:
    if raw_state in ACTIVE_COMPONENT_STATES and freshness_state == "stale":
        return "resume_required"
    if raw_state in DEGRADED_COMPONENT_STATES:
        return "degraded"
    return raw_state


def _component_state_class(effective_state: str) -> str:
    if effective_state in ACTIVE_COMPONENT_STATES:
        return "active"
    if effective_state in WAITING_COMPONENT_STATES:
        return "waiting"
    if effective_state in TERMINAL_COMPONENT_STATES:
        return "terminal"
    if effective_state in {"resume_required", "degraded"}:
        return "attention"
    return "unknown"


def build_status(*, db_path: str | Path | None = None, stale_multiplier: int = 5) -> dict[str, Any]:
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
        age = _seconds_since(row.get("last_heartbeat_observed_at"))
        interval = int(row.get("expected_heartbeat_interval_seconds") or 0)
        freshness_state = _freshness_state(age=age, interval=interval)
        effective_state = _component_effective_state(state, freshness_state)
        effective_by_state[effective_state] = effective_by_state.get(effective_state, 0) + 1
        component_view = dict(row)
        component_view["heartbeat_age_seconds"] = age
        component_view["freshness_state"] = freshness_state
        component_view["effective_state"] = effective_state
        component_view["state_class"] = _component_state_class(effective_state)
        component_views.append(component_view)
        if age is not None and interval > 0 and age > interval * stale_multiplier:
            stale_components.append(
                {
                    "component_id": row["component_id"],
                    "state": state,
                    "effective_state": effective_state,
                    "heartbeat_age_seconds": age,
                    "expected_interval_seconds": interval,
                }
            )
        if effective_state == "resume_required":
            attention_actions.append(
                {
                    "scope": "component",
                    "component_id": row["component_id"],
                    "severity": "high",
                    "action": "restart_or_resume_component",
                    "reason": "active component heartbeat is stale",
                }
            )
    decision_by_state: dict[str, int] = {}
    for row in decisions:
        state = str(row.get("state") or "unknown")
        decision_by_state[state] = decision_by_state.get(state, 0) + 1
        if state in {"raised", "acknowledged"}:
            attention_actions.append(
                {
                    "scope": "decision_prompt",
                    "decision_id": row["decision_id"],
                    "severity": "high" if state == "raised" else "medium",
                    "action": "answer_decision_prompt",
                    "reason": f"decision prompt is {state}",
                }
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
        "decision_prompts": decisions,
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
            f"freshness_state=`{row.get('freshness_state')}` "
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
                f"class=`{row['decision_class']}` state=`{row['state']}`"
            )
    return "\n".join(lines) + "\n"


def write_reports(*, db_path: str | Path | None = None) -> dict[str, str]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    status = build_status(db_path=db_path)
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
