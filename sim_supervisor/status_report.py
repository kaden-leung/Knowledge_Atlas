"""Render a compact supervisor status surface for the simulator apparatus."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sim_supervisor import supervisor_db as sdb


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "data" / "sim" / "supervisor_reports"


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _seconds_since(ts: str | None) -> float | None:
    dt = _parse_iso(ts)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def build_status(*, db_path: str | Path | None = None, stale_multiplier: int = 5) -> dict[str, Any]:
    components = sdb.component_rows(db_path=db_path)
    decisions = sdb.decision_prompt_rows(db_path=db_path)
    by_state: dict[str, int] = {}
    stale_components: list[dict[str, Any]] = []
    for row in components:
        state = str(row.get("state") or "unknown")
        by_state[state] = by_state.get(state, 0) + 1
        age = _seconds_since(row.get("last_heartbeat_observed_at"))
        interval = int(row.get("expected_heartbeat_interval_seconds") or 0)
        if age is not None and interval > 0 and age > interval * stale_multiplier:
            stale_components.append(
                {
                    "component_id": row["component_id"],
                    "state": state,
                    "heartbeat_age_seconds": age,
                    "expected_interval_seconds": interval,
                }
            )
    decision_by_state: dict[str, int] = {}
    for row in decisions:
        state = str(row.get("state") or "unknown")
        decision_by_state[state] = decision_by_state.get(state, 0) + 1
    return {
        "generated_at": sdb.utc_now_iso(),
        "component_count": len(components),
        "component_state_counts": by_state,
        "stale_components": stale_components,
        "decision_prompt_count": len(decisions),
        "decision_prompt_state_counts": decision_by_state,
        "components": components,
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
        f"- decision_prompt_state_counts: `{status.get('decision_prompt_state_counts', {})}`",
        "",
        "## Stale Components",
    ]
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
            f"state=`{row['state']}` last_heartbeat_observed_at=`{row.get('last_heartbeat_observed_at')}`"
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
    json_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(status), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}

