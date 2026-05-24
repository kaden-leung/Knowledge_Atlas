#!/usr/bin/env python3
"""Apply the article-epistemic-layer schema to the lifecycle database.

Idempotent. Safe to re-run: every CREATE in the schema uses IF NOT EXISTS.

Usage:
    python3 scripts/article_epistemic_layer_init.py
    python3 scripts/article_epistemic_layer_init.py --db PATH
    python3 scripts/article_epistemic_layer_init.py --dry-run

Source authority:
    docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "article_epistemic_layer.sql"

# Candidate locations for the lifecycle DB, in priority order. Mirrors
# scripts/paper_quality_blackboard_init.py so both schemas land in the same
# database on each developer's machine.
DEFAULT_DB_CANDIDATES = (
    REPO_ROOT / "data" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "data" / "ka_payloads" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "160sp" / "pipeline_lifecycle_full.db",
)

EXPECTED_TABLES = {
    "article_epistemic_records",
    "article_epistemic_components",
    "article_epistemic_support_sets",
    "article_epistemic_build_runs",
    "article_epistemic_completion_queue",
    "article_epistemic_verification_events",
}


def resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path
    for candidate in DEFAULT_DB_CANDIDATES:
        if candidate.exists():
            return candidate
    # Fall back to the 160sp canonical location even if it doesn't exist yet;
    # the operator can pass --db to override.
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
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'article_epistemic%' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()

    present = {name for (name,) in rows}
    missing = EXPECTED_TABLES - present
    return {
        "db": str(db_path),
        "applied": True,
        "tables_present": sorted(present),
        "tables_missing": sorted(missing),
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

    if not SCHEMA_PATH.exists():
        print(f"ERROR: schema file not found: {SCHEMA_PATH}", file=sys.stderr)
        return 2

    schema_sql = SCHEMA_PATH.read_text()
    db_path = resolve_db_path(args.db)
    result = apply_schema(db_path, schema_sql, args.dry_run)

    print(f"Lifecycle DB: {result['db']}")
    if not result.get("applied"):
        print(f"  Dry run only — no changes written.")
        return 0
    print(f"  Tables present:")
    for name in result["tables_present"]:
        print(f"    - {name}")
    if result["tables_missing"]:
        print(f"  ERROR: missing tables: {result['tables_missing']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
