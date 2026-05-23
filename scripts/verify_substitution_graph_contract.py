#!/usr/bin/env python3
"""Verify the Knowledge Atlas substitution graph contract.

The runtime substitution skill must use the SQLite graph when it is present,
and that graph must contain both the original Week-1 worked-example seed and
the POE-EXT expansion seed. This verifier is intentionally deterministic: it
does not call an LLM and it does not repair the database.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "substitution_graph.db"
BASE_SEED_PATH = REPO_ROOT / "data" / "substitution_seed_graph.json"
POE_SEED_PATH = REPO_ROOT / "data" / "poe_ext_substitution_seed.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def table_ids(db: sqlite3.Connection, table: str, key: str) -> set[str]:
    return {row[0] for row in db.execute(f"SELECT {key} FROM {table}")}


def fail(failures: list[str], message: str) -> None:
    failures.append(message)


def verify(db_path: Path = DB_PATH) -> list[str]:
    failures: list[str] = []
    if not db_path.exists():
        return [f"missing SQLite graph: {db_path}"]

    base_seed = load_json(BASE_SEED_PATH)
    poe_seed = load_json(POE_SEED_PATH)

    db = sqlite3.connect(str(db_path))
    try:
        db.execute("PRAGMA foreign_keys = ON")
        tables = table_ids(
            db,
            "sqlite_master",
            "name",
        )
        for required in ("constructs", "measures", "construct_measure_links"):
            if required not in tables:
                fail(failures, f"missing table: {required}")
        if failures:
            return failures

        construct_ids = table_ids(db, "constructs", "construct_id")
        measure_ids = table_ids(db, "measures", "measure_id")
        link_pairs = {
            (row[0], row[1])
            for row in db.execute(
                "SELECT construct_id, measure_id FROM construct_measure_links"
            )
        }

        for label, seed in (("base", base_seed), ("poe_ext", poe_seed)):
            for row in seed.get("constructs", []):
                if row["construct_id"] not in construct_ids:
                    fail(failures, f"{label} construct missing: {row['construct_id']}")
            for row in seed.get("measures", []):
                if row["measure_id"] not in measure_ids:
                    fail(failures, f"{label} measure missing: {row['measure_id']}")
            for row in seed.get("construct_measure_links", []):
                pair = (row["construct_id"], row["measure_id"])
                if pair not in link_pairs:
                    fail(failures, f"{label} link missing: {pair[0]} -> {pair[1]}")

        for table, key in (("constructs", "construct_id"), ("measures", "measure_id")):
            null_count = db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {key} IS NULL OR trim({key}) = ''"
            ).fetchone()[0]
            if null_count:
                fail(failures, f"{table} has {null_count} blank {key} values")

        dup_short_codes = list(
            db.execute(
                """
                SELECT short_code, COUNT(*)
                FROM measures
                GROUP BY short_code
                HAVING COUNT(*) > 1
                """
            )
        )
        for short_code, count in dup_short_codes:
            fail(failures, f"duplicate measure short_code {short_code!r}: {count}")

        bad_construct_refs = db.execute(
            """
            SELECT COUNT(*)
            FROM construct_measure_links AS l
            LEFT JOIN constructs AS c ON l.construct_id = c.construct_id
            WHERE c.construct_id IS NULL
            """
        ).fetchone()[0]
        if bad_construct_refs:
            fail(failures, f"links with missing construct refs: {bad_construct_refs}")

        bad_measure_refs = db.execute(
            """
            SELECT COUNT(*)
            FROM construct_measure_links AS l
            LEFT JOIN measures AS m ON l.measure_id = m.measure_id
            WHERE m.measure_id IS NULL
            """
        ).fetchone()[0]
        if bad_measure_refs:
            fail(failures, f"links with missing measure refs: {bad_measure_refs}")

        invalid_scores = db.execute(
            """
            SELECT COUNT(*)
            FROM construct_measure_links
            WHERE construct_validity < 0
               OR construct_validity > 1
               OR severity_average < 0
               OR severity_average > 1
            """
        ).fetchone()[0]
        if invalid_scores:
            fail(failures, f"links with out-of-range scores: {invalid_scores}")

        expected_counts = {
            "constructs": 35,
            "measures": 54,
            "construct_measure_links": 63,
        }
        for table, minimum in expected_counts.items():
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count < minimum:
                fail(failures, f"{table} count {count} below expected minimum {minimum}")
    finally:
        db.close()

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures = verify(args.db)
    if failures:
        print("substitution graph verification: FAIL")
        for item in failures:
            print(f"- {item}")
        return 1

    print("substitution graph verification: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
