#!/usr/bin/env python3
"""Seed the dependency-overseer registries from JSON contract files.

Seeds two tables:
  * vocabulary_registry from contracts/schemas/dependency_overseer/psychopy_seed.json
    (review_status='canonical'; open-vocab kinds method/measure/instrument/
    construct/abstract-source — synthesis P26).
  * artefact_kinds from contracts/schemas/dependency_overseer/artefact_kinds.json
    (the three Phase 1 kinds).

Idempotent. Safe to re-run; uses INSERT OR IGNORE on UNIQUE constraints.

Usage:
    python3 scripts/dependency_overseer_seed.py
    python3 scripts/dependency_overseer_seed.py --db PATH
    python3 scripts/dependency_overseer_seed.py --dry-run

Source authorities:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §5
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P26)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas" / "dependency_overseer"
VOCAB_SEED_PATH = SCHEMA_DIR / "psychopy_seed.json"
KINDS_PATH = SCHEMA_DIR / "artefact_kinds.json"

DEFAULT_DB_CANDIDATES = (
    REPO_ROOT / "data" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "data" / "ka_payloads" / "pipeline_lifecycle_full.db",
    REPO_ROOT / "160sp" / "pipeline_lifecycle_full.db",
)


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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def value_id_for(kind: str, value: str) -> str:
    """Deterministic value_id derived from (kind, value)."""
    h = hashlib.sha256(f"{kind}\x1f{value}".encode("utf-8")).hexdigest()[:16]
    return f"vocab:{kind}:{h}"


def seed_vocabulary(conn: sqlite3.Connection, dry_run: bool) -> dict[str, int]:
    payload = json.loads(VOCAB_SEED_PATH.read_text(encoding="utf-8"))
    seeds = payload["seeds"]
    now = utc_now_iso()
    inserted = 0
    skipped = 0
    by_kind: dict[str, int] = {}
    for s in seeds:
        kind = s["kind"]
        value = s["value"]
        seeded_from = s.get("seeded_from")
        vid = value_id_for(kind, value)
        if dry_run:
            inserted += 1
            by_kind[kind] = by_kind.get(kind, 0) + 1
            continue
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO vocabulary_registry (
              value_id, kind, value, canonical_value, first_seen_in_paper,
              first_observed_at, first_observed_build_run_id, review_status,
              canonicalization_source, seeded_from
            ) VALUES (?, ?, ?, NULL, NULL, ?, NULL, 'canonical', NULL, ?)
            """,
            (vid, kind, value, now, seeded_from),
        )
        if cur.rowcount > 0:
            inserted += 1
            by_kind[kind] = by_kind.get(kind, 0) + 1
        else:
            skipped += 1
    return {"inserted": inserted, "skipped_existing": skipped, "by_kind": by_kind}


def seed_artefact_kinds(conn: sqlite3.Connection, dry_run: bool) -> dict[str, int]:
    payload = json.loads(KINDS_PATH.read_text(encoding="utf-8"))
    kinds = payload["kinds"]
    now = utc_now_iso()
    inserted = 0
    skipped = 0
    for k in kinds:
        if dry_run:
            inserted += 1
            continue
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO artefact_kinds (
              kind_name, owner_pipeline, support_rule_module,
              schema_version, active, created_at
            ) VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                k["kind_name"],
                k["owner_pipeline"],
                k["support_rule_module"],
                k["schema_version"],
                now,
            ),
        )
        if cur.rowcount > 0:
            inserted += 1
        else:
            skipped += 1
    return {"inserted": inserted, "skipped_existing": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Override lifecycle DB path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve paths and read JSON but do not write to the DB",
    )
    args = parser.parse_args(argv)

    db_path = resolve_db_path(args.db)
    if not VOCAB_SEED_PATH.exists():
        print(f"ERROR: vocab seed file missing: {VOCAB_SEED_PATH}", file=sys.stderr)
        return 2
    if not KINDS_PATH.exists():
        print(f"ERROR: artefact_kinds file missing: {KINDS_PATH}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        vocab = seed_vocabulary(conn, args.dry_run)
        kinds = seed_artefact_kinds(conn, args.dry_run)
        if not args.dry_run:
            conn.commit()
            vocab_total = conn.execute(
                "SELECT COUNT(*) FROM vocabulary_registry"
            ).fetchone()[0]
            kinds_total = conn.execute(
                "SELECT COUNT(*) FROM artefact_kinds"
            ).fetchone()[0]
        else:
            vocab_total = None
            kinds_total = None
    finally:
        conn.close()

    report = {
        "db": str(db_path),
        "dry_run": args.dry_run,
        "vocabulary_registry": {
            **vocab,
            "table_total_after": vocab_total,
        },
        "artefact_kinds": {
            **kinds,
            "table_total_after": kinds_total,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
