"""Reusable operational-truth vocabulary for the simulator supervisor.

The aim is to judge components by observed operational evidence rather than
by hopeful prose or self-description alone.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


ACTIVE_COMPONENT_STATES = {"starting", "running"}
WAITING_COMPONENT_STATES = {"idle", "waiting_for_operator", "decision_pending"}
TERMINAL_COMPONENT_STATES = {"completed", "standing_down", "disabled"}
DEGRADED_COMPONENT_STATES = {"failed", "stuck", "degraded"}


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def seconds_since(ts: str | None) -> float | None:
    dt = parse_iso(ts)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def freshness_state(*, age: float | None, interval: int) -> str:
    if age is None or interval <= 0:
        return "unknown"
    if age <= interval:
        return "fresh"
    if age <= interval * 5:
        return "late"
    return "stale"


def clock_skew_state(
    *,
    authored_heartbeat_at: str | None,
    observed_heartbeat_at: str | None,
    skew_threshold_seconds: int = 300,
) -> tuple[str, float | None]:
    authored = parse_iso(authored_heartbeat_at)
    observed = parse_iso(observed_heartbeat_at)
    if authored is None or observed is None:
        return ("unknown", None)
    skew_seconds = abs((observed - authored).total_seconds())
    if skew_seconds <= skew_threshold_seconds:
        return ("normal", skew_seconds)
    return ("suspected", skew_seconds)


def effective_state(*, raw_state: str, freshness: str) -> str:
    if raw_state in DEGRADED_COMPONENT_STATES:
        return "degraded"
    if raw_state in ACTIVE_COMPONENT_STATES and freshness == "stale":
        return "resume_required"
    if raw_state in WAITING_COMPONENT_STATES and freshness == "stale":
        return "resume_required"
    return raw_state


def state_class(effective: str) -> str:
    if effective in ACTIVE_COMPONENT_STATES:
        return "active"
    if effective in WAITING_COMPONENT_STATES:
        return "waiting"
    if effective in TERMINAL_COMPONENT_STATES:
        return "terminal"
    if effective in {"resume_required", "degraded"}:
        return "attention"
    return "unknown"


def component_attention_action(
    *,
    component_id: str,
    raw_state: str,
    effective: str,
    freshness: str,
    clock_skew: str,
) -> dict[str, Any] | None:
    if clock_skew == "suspected":
        return {
            "scope": "component",
            "component_id": component_id,
            "severity": "high",
            "policy_family": "heartbeat_integrity_policy",
            "attention_class": "inspect_inconsistency",
            "action": "inspect_clock_skew_and_checkpoint_truth",
            "reason": "authored heartbeat time diverges materially from observed heartbeat time",
        }
    if effective == "degraded":
        return {
            "scope": "component",
            "component_id": component_id,
            "severity": "critical",
            "policy_family": "component_health_policy",
            "attention_class": "blocked_hard",
            "action": "repair_or_restart_component",
            "reason": f"component entered degraded state `{raw_state}`",
        }
    if effective == "resume_required":
        return {
            "scope": "component",
            "component_id": component_id,
            "severity": "high",
            "policy_family": "worker_availability_policy",
            "attention_class": "resume_now",
            "action": "restart_or_resume_component",
            "reason": f"component heartbeat is `{freshness}` while raw state is `{raw_state}`",
        }
    return None


def evaluate_component_row(
    row: dict[str, Any],
    *,
    stale_multiplier: int = 5,
    skew_threshold_seconds: int = 300,
) -> dict[str, Any]:
    del stale_multiplier  # retained for future policy tuning
    raw_state = str(row.get("state") or "unknown")
    age = seconds_since(row.get("last_heartbeat_observed_at"))
    interval = int(row.get("expected_heartbeat_interval_seconds") or 0)
    freshness = freshness_state(age=age, interval=interval)
    effective = effective_state(raw_state=raw_state, freshness=freshness)
    skew_state, skew_seconds = clock_skew_state(
        authored_heartbeat_at=row.get("last_heartbeat_at"),
        observed_heartbeat_at=row.get("last_heartbeat_observed_at"),
        skew_threshold_seconds=skew_threshold_seconds,
    )
    evaluated = dict(row)
    evaluated["heartbeat_age_seconds"] = age
    evaluated["freshness_state"] = freshness
    evaluated["effective_state"] = effective
    evaluated["state_class"] = state_class(effective)
    evaluated["clock_skew_state"] = skew_state
    evaluated["clock_skew_seconds"] = skew_seconds
    action = component_attention_action(
        component_id=str(row.get("component_id") or "unknown"),
        raw_state=raw_state,
        effective=effective,
        freshness=freshness,
        clock_skew=skew_state,
    )
    evaluated["attention_action"] = action
    return evaluated
