#!/usr/bin/env python3
"""Apply the dependency-overseer schema to the lifecycle database.

Idempotent. Safe to re-run: every CREATE in the schema uses IF NOT EXISTS.

Usage:
    python3 scripts/dependency_overseer_init.py
    python3 scripts/dependency_overseer_init.py --db PATH
    python3 scripts/dependency_overseer_init.py --dry-run

Source authorities:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md (controlling)
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = (
    REPO_ROOT / "contracts" / "schemas" / "dependency_overseer"
)
SCHEMA_PATH = SCHEMA_DIR / "dependency_overseer.sql"
OBSERVABILITY_SCHEMA_PATH = SCHEMA_DIR / "observability_layer.sql"

DEFAULT_DB_CANDIDATES = (
    REPO_ROOT / "data" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "data" / "ka_payloads" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "160sp" / "pipeline_lifecycle_full.db",
)

EXPECTED_ACTIVE_TABLES = {
    "artefact_registry",
    "dependency_edges",
    "content_hashes",
    "support_sets",
    "support_set_members",
    "build_runs",
    "rebuild_queue",
    "worker_heartbeats",
    "artefact_kinds",
    "pipeline_registry",
    "vocabulary_registry",
    "claims",
    "defeaters",
    "belief_network_links",
    "answer_shape_decisions",
    "completion_queue",
    "last_mile_production_checks",
}

EXPECTED_SCAFFOLD_TABLES = {
    "cross_db_sync_events",
    "llm_invocations",
    "prompt_templates",
    "source_packets",
    "content_equivalence_checks",
}

EXPECTED_OBSERVABILITY_TABLES = {
    "verifier_run_history",
    "reconciler_event_log",
}


def resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path
    for candidate in DEFAULT_DB_CANDIDATES:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return DEFAULT_DB_CANDIDATES[-1]


def apply_schema(db_path: Path, schema_sql: str, dry_run: bool) -> dict[str, object]:
    if dry_run:
        return {"db": str(db_path), "applied": False, "reason": "dry_run"}

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"
        ).fetchall()
    finally:
        conn.close()

    present = {name for (name,) in rows}
    active_missing = EXPECTED_ACTIVE_TABLES - present
    scaffold_missing = EXPECTED_SCAFFOLD_TABLES - present
    return {
        "db": str(db_path),
        "applied": True,
        "all_tables_present_count": len(present),
        "active_tables_missing": sorted(active_missing),
        "scaffold_tables_missing": sorted(scaffold_missing),
        "indices_present_count": len(idx),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Override lifecycle DB path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve paths and read the schema but do not write to the DB",
    )
    args = parser.parse_args(argv)

    db_path = resolve_db_path(args.db)
    if not SCHEMA_PATH.exists():
        print(f"ERROR: schema file missing: {SCHEMA_PATH}", file=sys.stderr)
        return 2

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    if OBSERVABILITY_SCHEMA_PATH.exists():
        schema_sql += "\n\n-- observability_layer.sql appended\n\n"
        schema_sql += OBSERVABILITY_SCHEMA_PATH.read_text(encoding="utf-8")
    result = apply_schema(db_path, schema_sql, args.dry_run)

    # Verify observability tables landed too.
    if not args.dry_run:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        finally:
            conn.close()
        present = {n for (n,) in rows}
        result["observability_tables_missing"] = sorted(
            EXPECTED_OBSERVABILITY_TABLES - present
        )

    print(json.dumps(result, indent=2, sort_keys=True))

    if args.dry_run:
        return 0
    if (result.get("active_tables_missing")
        or result.get("scaffold_tables_missing")
        or result.get("observability_tables_missing")):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
