"""Reusable operational-truth vocabulary for the simulator supervisor.

This module judges components by observed operational evidence rather than by
hopeful self-description.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any


DEFAULT_STATE_PROFILE: dict[str, set[str]] = {
    "active": {"starting", "running"},
    "waiting": {"idle", "waiting_for_operator", "decision_pending"},
    "terminal": {"completed", "standing_down", "disabled"},
    "degraded": {"failed", "stuck", "degraded"},
}


def parse_iso(ts: str | None) -> tuple[datetime | None, str]:
    if ts is None:
        return (None, "missing")
    text = str(ts).strip()
    if not text:
        return (None, "missing")
    try:
        return (datetime.fromisoformat(text.replace("Z", "+00:00")), "valid")
    except ValueError:
        return (None, "malformed")


def seconds_since(ts: str | None) -> tuple[float | None, str]:
    dt, status = parse_iso(ts)
    if dt is None:
        return (None, status)
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    if age < 0:
        return (age, "future")
    return (age, status)


def freshness_state(
    *,
    age: float | None,
    interval: int,
    late_after_intervals: int = 1,
    stale_after_intervals: int = 5,
) -> str:
    if interval <= 0:
        return "invalid_interval"
    if age is None:
        return "unknown"
    if age < 0:
        return "future"
    if age <= interval * late_after_intervals:
        return "fresh"
    if age <= interval * stale_after_intervals:
        return "late"
    return "stale"


def clock_skew_state(
    *,
    authored_heartbeat_at: str | None,
    observed_heartbeat_at: str | None,
    skew_threshold_seconds: int = 300,
) -> tuple[str, float | None]:
    authored, authored_status = parse_iso(authored_heartbeat_at)
    observed, observed_status = parse_iso(observed_heartbeat_at)
    _, authored_age_status = seconds_since(authored_heartbeat_at)
    _, observed_age_status = seconds_since(observed_heartbeat_at)
    if authored_status == "malformed" or observed_status == "malformed":
        return ("malformed", None)
    if authored_age_status == "future" or observed_age_status == "future":
        return ("future", None)
    if authored is None or observed is None:
        return ("unknown", None)
    skew_seconds = abs((observed - authored).total_seconds())
    if skew_seconds <= skew_threshold_seconds:
        return ("normal", skew_seconds)
    return ("suspected", skew_seconds)


def _state_family(raw_state: str, state_profile: dict[str, set[str]]) -> str:
    for family, members in state_profile.items():
        if raw_state in members:
            return family
    return "unknown"


def _details_dict(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("details_json")
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        decoded = json.loads(str(payload))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def effective_state(
    *,
    raw_state: str,
    heartbeat_freshness: str,
    progress_freshness: str,
    state_profile: dict[str, set[str]],
) -> str:
    family = _state_family(raw_state, state_profile)
    if family == "degraded":
        return "degraded"
    if family == "unknown":
        return "unknown_state"
    if family == "active":
        if heartbeat_freshness in {"unknown", "malformed", "invalid_interval", "stale", "future"}:
            return "resume_required"
        if progress_freshness in {"unknown", "malformed", "stale", "future"}:
            return "stalled_progress"
        return raw_state
    if family == "waiting":
        if heartbeat_freshness in {"unknown", "malformed", "invalid_interval", "stale", "future"}:
            return "blocked_waiting"
        return raw_state
    return raw_state


def state_class(effective: str, state_profile: dict[str, set[str]]) -> str:
    if effective in state_profile["active"]:
        return "active"
    if effective in state_profile["waiting"]:
        return "waiting"
    if effective in state_profile["terminal"]:
        return "terminal"
    if effective in {"resume_required", "degraded", "blocked_waiting", "stalled_progress", "unknown_state"}:
        return "attention"
    return "unknown"


def component_attention_actions(
    *,
    component_id: str,
    raw_state: str,
    family: str,
    effective: str,
    heartbeat_freshness: str,
    heartbeat_status: str,
    progress_freshness: str,
    progress_status: str,
    clock_skew: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if family == "unknown":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "state_contract_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_unknown_component_state",
                "reason": f"component reported unrecognized raw state `{raw_state}`",
            }
        )
    if heartbeat_status == "malformed":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "heartbeat_integrity_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_malformed_heartbeat_timestamp",
                "reason": "component authored or stored a malformed heartbeat timestamp",
            }
        )
    if heartbeat_freshness == "invalid_interval":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "heartbeat_integrity_policy",
                "attention_class": "inspect_inconsistency",
                "action": "repair_invalid_heartbeat_interval",
                "reason": "expected heartbeat interval is missing or nonpositive",
            }
        )
    if heartbeat_status == "future":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "heartbeat_integrity_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_future_heartbeat_timestamp",
                "reason": "component heartbeat evidence lies in the future",
            }
        )
    if heartbeat_freshness == "unknown" and family in {"active", "waiting"}:
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "heartbeat_integrity_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_missing_observed_heartbeat",
                "reason": f"component is `{raw_state}` but no observed heartbeat is available",
            }
        )
    if clock_skew == "malformed":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "heartbeat_integrity_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_clock_skew_evidence",
                "reason": "clock skew could not be evaluated because heartbeat timestamps are malformed",
            }
        )
    elif clock_skew == "suspected":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "heartbeat_integrity_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_clock_skew_and_checkpoint_truth",
                "reason": "authored heartbeat time diverges materially from observed heartbeat time",
            }
        )
    elif clock_skew == "future":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "heartbeat_integrity_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_future_clock_evidence",
                "reason": "clock skew cannot be trusted because heartbeat evidence lies in the future",
            }
        )
    if family == "degraded":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "critical",
                "policy_family": "component_health_policy",
                "attention_class": "blocked_hard",
                "action": "repair_or_restart_component",
                "reason": f"component entered degraded state `{raw_state}`",
            }
        )
    if family == "active" and heartbeat_freshness == "stale":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "worker_availability_policy",
                "attention_class": "resume_now",
                "action": "restart_or_resume_component",
                "reason": f"active component heartbeat is stale while raw state is `{raw_state}`",
            }
        )
    if family == "waiting" and heartbeat_freshness == "stale":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "medium",
                "policy_family": "dependency_wait_policy",
                "attention_class": "neglected_too_long",
                "action": "inspect_blocking_dependency",
                "reason": f"waiting component has been waiting too long in raw state `{raw_state}`",
            }
        )
    if progress_status == "future" and family == "active":
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "high",
                "policy_family": "progress_truth_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_future_progress_timestamp",
                "reason": "component progress evidence lies in the future",
            }
        )
    if family == "active" and progress_freshness in {"unknown", "malformed", "stale", "future"}:
        actions.append(
            {
                "scope": "component",
                "component_id": component_id,
                "severity": "medium" if progress_freshness not in {"stale", "future"} else "high",
                "policy_family": "progress_truth_policy",
                "attention_class": "neglected_too_long" if progress_freshness == "stale" else "inspect_inconsistency",
                "action": "inspect_stalled_progress",
                "reason": f"active component progress truth is `{progress_freshness}`",
            }
        )
    return actions


def evaluate_component_row(
    row: dict[str, Any],
    *,
    state_profile: dict[str, set[str]] | None = None,
    late_after_intervals: int = 1,
    stale_after_intervals: int = 5,
    skew_threshold_seconds: int = 300,
) -> dict[str, Any]:
    state_profile = state_profile or DEFAULT_STATE_PROFILE
    raw_state = str(row.get("state") or "unknown")
    family = _state_family(raw_state, state_profile)

    heartbeat_age, observed_status = seconds_since(row.get("last_heartbeat_observed_at"))
    authored_age, authored_status = seconds_since(row.get("last_heartbeat_at"))
    progress_age, progress_status = seconds_since(row.get("last_progress_at"))
    interval = int(row.get("expected_heartbeat_interval_seconds") or 0)
    details = _details_dict(row)
    progress_interval = int(details.get("expected_progress_interval_seconds") or max(interval * 3, interval))

    heartbeat_freshness = freshness_state(
        age=heartbeat_age,
        interval=interval,
        late_after_intervals=late_after_intervals,
        stale_after_intervals=stale_after_intervals,
    )
    progress_freshness = freshness_state(
        age=progress_age,
        interval=progress_interval,
        late_after_intervals=late_after_intervals,
        stale_after_intervals=stale_after_intervals,
    )
    skew_state, skew_seconds = clock_skew_state(
        authored_heartbeat_at=row.get("last_heartbeat_at"),
        observed_heartbeat_at=row.get("last_heartbeat_observed_at"),
        skew_threshold_seconds=skew_threshold_seconds,
    )
    effective = effective_state(
        raw_state=raw_state,
        heartbeat_freshness=heartbeat_freshness,
        progress_freshness=progress_freshness,
        state_profile=state_profile,
    )
    actions = component_attention_actions(
        component_id=str(row.get("component_id") or "unknown"),
        raw_state=raw_state,
        family=family,
        effective=effective,
        heartbeat_freshness=heartbeat_freshness,
        heartbeat_status="malformed" if authored_status == "malformed" or observed_status == "malformed" else observed_status,
        progress_freshness=progress_freshness,
        progress_status=progress_status,
        clock_skew=skew_state,
    )

    evaluated = dict(row)
    evaluated["state_family"] = family
    evaluated["progress_expected_interval_seconds"] = progress_interval
    evaluated["heartbeat_age_seconds"] = heartbeat_age
    evaluated["authored_heartbeat_age_seconds"] = authored_age
    evaluated["progress_age_seconds"] = progress_age
    evaluated["observed_heartbeat_timestamp_status"] = observed_status
    evaluated["authored_heartbeat_timestamp_status"] = authored_status
    evaluated["progress_timestamp_status"] = progress_status
    evaluated["heartbeat_freshness_state"] = heartbeat_freshness
    evaluated["progress_freshness_state"] = progress_freshness
    evaluated["effective_state"] = effective
    evaluated["state_class"] = state_class(effective, state_profile)
    evaluated["clock_skew_state"] = skew_state
    evaluated["clock_skew_seconds"] = skew_seconds
    evaluated["attention_actions"] = actions
    return evaluated


def evaluate_decision_prompt_row(
    row: dict[str, Any],
    *,
    acknowledged_grace_seconds: int = 900,
    raised_grace_seconds: int = 300,
) -> dict[str, Any]:
    state = str(row.get("state") or "unknown")
    raised_age, raised_status = seconds_since(row.get("raised_at"))
    acknowledged_age, acknowledged_status = seconds_since(row.get("acknowledged_at"))
    evaluated = dict(row)
    actions: list[dict[str, Any]] = []
    if state in {"raised", "acknowledged"} and raised_status in {"missing", "malformed", "future"}:
        actions.append(
            {
                "scope": "decision_prompt",
                "decision_id": row["decision_id"],
                "severity": "high",
                "policy_family": "decision_integrity_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_invalid_decision_timestamp",
                "reason": f"decision prompt raised_at is `{raised_status}`",
            }
        )
    if state == "acknowledged" and acknowledged_status in {"missing", "malformed", "future"}:
        actions.append(
            {
                "scope": "decision_prompt",
                "decision_id": row["decision_id"],
                "severity": "high",
                "policy_family": "decision_integrity_policy",
                "attention_class": "inspect_inconsistency",
                "action": "inspect_invalid_decision_timestamp",
                "reason": f"decision prompt acknowledged_at is `{acknowledged_status}`",
            }
        )
    if state == "raised":
        actions.append(
            {
                "scope": "decision_prompt",
                "decision_id": row["decision_id"],
                "severity": "high" if (raised_age is None or raised_age <= raised_grace_seconds) else "critical",
                "policy_family": "decision_lifecycle_policy",
                "attention_class": "resume_now" if (raised_age is None or raised_age <= raised_grace_seconds) else "neglected_too_long",
                "action": "answer_decision_prompt",
                "reason": f"decision prompt is raised for {raised_age if raised_age is not None else 'unknown'} seconds",
            }
        )
    elif state == "acknowledged":
        if acknowledged_age is None or acknowledged_status == "future":
            actions.append(
                {
                    "scope": "decision_prompt",
                    "decision_id": row["decision_id"],
                    "severity": "medium",
                    "policy_family": "decision_lifecycle_policy",
                    "attention_class": "resume_now",
                    "action": "answer_decision_prompt",
                    "reason": "decision prompt is acknowledged but acknowledgement age cannot be trusted",
                }
            )
        elif acknowledged_age > acknowledged_grace_seconds:
            actions.append(
                {
                    "scope": "decision_prompt",
                    "decision_id": row["decision_id"],
                    "severity": "medium",
                    "policy_family": "decision_lifecycle_policy",
                    "attention_class": "neglected_too_long",
                    "action": "answer_decision_prompt",
                    "reason": "decision prompt was acknowledged but has remained unanswered beyond the grace window",
                }
            )
    evaluated["raised_age_seconds"] = raised_age
    evaluated["raised_timestamp_status"] = raised_status
    evaluated["acknowledged_age_seconds"] = acknowledged_age
    evaluated["acknowledged_timestamp_status"] = acknowledged_status
    evaluated["attention_actions"] = actions
    return evaluated
