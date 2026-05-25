#!/usr/bin/env python3
"""Run one tick of the Article Finder ↔ KA reconciler.

Designed to be cron-able. Reads AF DB read-only; writes only to the KA
lifecycle DB. Output is a JSON report.

Usage:
    python3 scripts/dependency_overseer_reconciler_tick.py
    python3 scripts/dependency_overseer_reconciler_tick.py --db PATH
    python3 scripts/dependency_overseer_reconciler_tick.py --af-db PATH
    python3 scripts/dependency_overseer_reconciler_tick.py --accepted-filter processed_partial --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from overseer.article_finder_connector import (
    ArticleFinderNotFound,
    connect_readonly,
)
from overseer.article_finder_reconciler import tick
from overseer.db import connect as ka_connect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Override KA lifecycle DB path")
    parser.add_argument("--af-db", help="Override AF DB path")
    parser.add_argument(
        "--accepted-filter", default="none",
        help="AF.papers.status value to treat as accepted (default 'none' "
             "disables status filtering — the new criterion uses "
             "--accepted-intake-decision instead per pause plan §4.1)",
    )
    parser.add_argument(
        "--accepted-intake-decision", default="accept_candidate",
        help="AF.papers.atlas_intake_decision value to treat as accepted "
             "(default 'accept_candidate' — 754 rows on live AF; replaces "
             "the legacy 'processed_partial' status proxy)",
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap rows scanned per tick")
    args = parser.parse_args(argv)

    accepted = None if args.accepted_filter.lower() == "none" else args.accepted_filter
    intake = None if args.accepted_intake_decision.lower() == "none" else args.accepted_intake_decision

    try:
        af_conn = connect_readonly(args.af_db)
    except ArticleFinderNotFound as e:
        print(json.dumps({"error": str(e)}, indent=2))
        return 2

    ka_conn = ka_connect(args.db)
    try:
        report = tick(
            ka_conn, af_conn=af_conn,
            accepted_filter=accepted,
            accepted_intake_decision=intake,
            limit=args.limit,
        )
    finally:
        ka_conn.close()
        af_conn.close()
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
