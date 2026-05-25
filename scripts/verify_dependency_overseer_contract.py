#!/usr/bin/env python3
"""Strict data verifier for the dependency overseer.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §10

Usage:
    python3 scripts/verify_dependency_overseer_contract.py --strict
    python3 scripts/verify_dependency_overseer_contract.py --strict --db PATH

Exits 0 if every check passes, 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from overseer.db import resolve_db_path  # noqa: E402
from overseer.verifier_data import report_to_dict, verify_strict  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Override lifecycle DB path")
    parser.add_argument("--strict", action="store_true",
                        help="Required flag; reserved for future strictness levels")
    args = parser.parse_args(argv)

    db_path = resolve_db_path(args.db)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        report = verify_strict(
            conn,
            db_path=str(db_path),
            triggered_by="manual:verify_dependency_overseer_contract",
        )
    finally:
        conn.close()

    out = report_to_dict(report)
    out["db"] = str(db_path)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if report.overall_passed else 1


if __name__ == "__main__":
    sys.exit(main())
