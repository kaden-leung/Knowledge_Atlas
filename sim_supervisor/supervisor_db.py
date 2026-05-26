"""Minimal control-plane DB for the AF traffic simulator."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "sim" / "sim_supervisor.db"

SUPERVISOR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS components (
    component_id TEXT PRIMARY KEY,
    component_kind TEXT NOT NULL,
    state TEXT NOT NULL,
    expected_heartbeat_interval_seconds INTEGER NOT NULL,
    current_run_id TEXT,
    last_heartbeat_at TEXT,
    last_heartbeat_observed_at TEXT,
    last_progress_at TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS component_heartbeats (
    heartbeat_id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL,
    state TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    progress_at TEXT,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS component_transitions (
    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS decision_prompts (
    decision_id TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    decision_class TEXT NOT NULL,
    state TEXT NOT NULL,
    trigger_event_id TEXT,
    trigger_summary TEXT NOT NULL,
    dashboard_widget TEXT,
    runbook_section TEXT,
    available_actions_json TEXT NOT NULL DEFAULT '[]',
    chosen_action TEXT,
    rationale TEXT,
    sim_elapsed_seconds INTEGER,
    real_elapsed_seconds REAL,
    raised_at TEXT NOT NULL,
    acknowledged_at TEXT,
    answered_at TEXT,
    expired_at TEXT,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sim_supervisor_components_state
    ON components(state);
CREATE INDEX IF NOT EXISTS idx_sim_supervisor_heartbeats_component
    ON component_heartbeats(component_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_sim_supervisor_transitions_component
    ON component_transitions(component_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_sim_supervisor_decisions_state
    ON decision_prompts(state, raised_at DESC);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is None:
        return DEFAULT_DB_PATH
    path = Path(db_path).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def init_db(db_path: str | Path | None = None) -> Path:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SUPERVISOR_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    return path


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = init_db(db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def register_component(
    *,
    component_id: str,
    component_kind: str,
    state: str,
    expected_heartbeat_interval_seconds: int,
    current_run_id: str | None = None,
    details: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    now = utc_now_iso()
    payload = json.dumps(details or {}, sort_keys=True)
    conn = connect(db_path)
    try:
        existing = conn.execute(
            "SELECT state FROM components WHERE component_id=?",
            (component_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO components (
                component_id, component_kind, state,
                expected_heartbeat_interval_seconds, current_run_id,
                last_heartbeat_at, last_heartbeat_observed_at, last_progress_at,
                details_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
            ON CONFLICT(component_id) DO UPDATE SET
                component_kind=excluded.component_kind,
                state=excluded.state,
                expected_heartbeat_interval_seconds=excluded.expected_heartbeat_interval_seconds,
                current_run_id=excluded.current_run_id,
                details_json=excluded.details_json,
                updated_at=excluded.updated_at
            """,
            (
                component_id,
                component_kind,
                state,
                int(expected_heartbeat_interval_seconds),
                current_run_id,
                payload,
                now,
            ),
        )
        if existing is None or str(existing["state"]) != state:
            conn.execute(
                """
                INSERT INTO component_transitions (
                    component_id, from_state, to_state, reason, changed_at, details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    component_id,
                    None if existing is None else str(existing["state"]),
                    state,
                    "component_registered",
                    now,
                    payload,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def record_heartbeat(
    *,
    component_id: str,
    state: str,
    heartbeat_at: str | None = None,
    progress_at: str | None = None,
    details: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    heartbeat_at = heartbeat_at or utc_now_iso()
    observed_at = utc_now_iso()
    payload = json.dumps(details or {}, sort_keys=True)
    conn = connect(db_path)
    try:
        existing = conn.execute(
            "SELECT state FROM components WHERE component_id=?",
            (component_id,),
        ).fetchone()
        if existing is None:
            raise ValueError(f"component not registered: {component_id}")
        conn.execute(
            """
            INSERT INTO component_heartbeats (
                component_id, state, heartbeat_at, observed_at, progress_at, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                component_id,
                state,
                heartbeat_at,
                observed_at,
                progress_at,
                payload,
            ),
        )
        conn.execute(
            """
            UPDATE components
               SET state=?,
                   last_heartbeat_at=?,
                   last_heartbeat_observed_at=?,
                   last_progress_at=COALESCE(?, last_progress_at),
                   details_json=?,
                   updated_at=?
             WHERE component_id=?
            """,
            (
                state,
                heartbeat_at,
                observed_at,
                progress_at,
                payload,
                observed_at,
                component_id,
            ),
        )
        if str(existing["state"]) != state:
            conn.execute(
                """
                INSERT INTO component_transitions (
                    component_id, from_state, to_state, reason, changed_at, details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    component_id,
                    str(existing["state"]),
                    state,
                    "heartbeat_state_change",
                    observed_at,
                    payload,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def transition_component(
    *,
    component_id: str,
    to_state: str,
    reason: str,
    details: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    now = utc_now_iso()
    payload = json.dumps(details or {}, sort_keys=True)
    conn = connect(db_path)
    try:
        existing = conn.execute(
            "SELECT state FROM components WHERE component_id=?",
            (component_id,),
        ).fetchone()
        if existing is None:
            raise ValueError(f"component not registered: {component_id}")
        conn.execute(
            """
            UPDATE components
               SET state=?, details_json=?, updated_at=?
             WHERE component_id=?
            """,
            (to_state, payload, now, component_id),
        )
        conn.execute(
            """
            INSERT INTO component_transitions (
                component_id, from_state, to_state, reason, changed_at, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                component_id,
                str(existing["state"]),
                to_state,
                reason,
                now,
                payload,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def raise_decision_prompt(
    *,
    decision_id: str,
    scenario_name: str,
    decision_class: str,
    trigger_summary: str,
    available_actions: list[str],
    dashboard_widget: str | None = None,
    runbook_section: str | None = None,
    trigger_event_id: str | None = None,
    sim_elapsed_seconds: int | None = None,
    real_elapsed_seconds: float | None = None,
    details: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    now = utc_now_iso()
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO decision_prompts (
                decision_id, scenario_name, decision_class, state,
                trigger_event_id, trigger_summary, dashboard_widget, runbook_section,
                available_actions_json, chosen_action, rationale,
                sim_elapsed_seconds, real_elapsed_seconds,
                raised_at, acknowledged_at, answered_at, expired_at, details_json
            )
            VALUES (?, ?, ?, 'raised', ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, NULL, NULL, ?)
            ON CONFLICT(decision_id) DO UPDATE SET
                state='raised',
                trigger_event_id=excluded.trigger_event_id,
                trigger_summary=excluded.trigger_summary,
                dashboard_widget=excluded.dashboard_widget,
                runbook_section=excluded.runbook_section,
                available_actions_json=excluded.available_actions_json,
                sim_elapsed_seconds=excluded.sim_elapsed_seconds,
                real_elapsed_seconds=excluded.real_elapsed_seconds,
                details_json=excluded.details_json
            """,
            (
                decision_id,
                scenario_name,
                decision_class,
                trigger_event_id,
                trigger_summary,
                dashboard_widget,
                runbook_section,
                json.dumps(available_actions, sort_keys=True),
                sim_elapsed_seconds,
                real_elapsed_seconds,
                now,
                json.dumps(details or {}, sort_keys=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def acknowledge_decision_prompt(
    decision_id: str,
    *,
    db_path: str | Path | None = None,
) -> None:
    now = utc_now_iso()
    conn = connect(db_path)
    try:
        conn.execute(
            """
            UPDATE decision_prompts
               SET state='acknowledged',
                   acknowledged_at=COALESCE(acknowledged_at, ?)
             WHERE decision_id=?
            """,
            (now, decision_id),
        )
        conn.commit()
    finally:
        conn.close()


def answer_decision_prompt(
    decision_id: str,
    *,
    chosen_action: str,
    rationale: str,
    db_path: str | Path | None = None,
) -> None:
    now = utc_now_iso()
    conn = connect(db_path)
    try:
        conn.execute(
            """
            UPDATE decision_prompts
               SET state='answered',
                   chosen_action=?,
                   rationale=?,
                   answered_at=?
             WHERE decision_id=?
            """,
            (chosen_action, rationale, now, decision_id),
        )
        conn.commit()
    finally:
        conn.close()


def component_rows(*, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM components ORDER BY component_id").fetchall()]
    finally:
        conn.close()


def decision_prompt_rows(*, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    conn = connect(db_path)
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM decision_prompts ORDER BY raised_at DESC, decision_id").fetchall()]
    finally:
        conn.close()

