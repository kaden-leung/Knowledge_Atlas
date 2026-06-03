#!/usr/bin/env python3
"""Thin orchestrator for Track 2 Task 3 evidence and optional live steps."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def run_step(name: str, args: list[str]) -> None:
    print(f"\n== {name} ==", flush=True)
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("verify", "handoff", "dashboard", "all-evidence", "live-search"),
        default="all-evidence",
        help="Pipeline slice to run. live-search requires --confirm-live.",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Required before running live network search steps.",
    )
    parser.add_argument(
        "--handoff-limit",
        type=int,
        default=None,
        help="Optional max ACCEPT rows to export during handoff.",
    )
    return parser.parse_args()


def run_verify() -> None:
    run_step("Workflow evidence verification", [PYTHON, "verify_track2_workflow.py"])


def run_handoff(limit: int | None) -> None:
    handoff_cmd = [PYTHON, "Phase 7/ae_handoff.py"]
    if limit is not None:
        handoff_cmd.extend(["--limit", str(limit)])
    run_step("AE handoff export", handoff_cmd)
    run_step("AE inbox validation", [PYTHON, "Phase 7/ae_inbox_stub.py"])


def run_dashboard() -> None:
    run_step("PRISMA dashboard regeneration", [PYTHON, "Phase 6/generate_prisma_report.py"])


def run_live_search(confirm_live: bool) -> None:
    if not confirm_live:
        raise SystemExit("live-search requires --confirm-live")
    run_step(
        "Live search runner",
        [
            PYTHON,
            "Phase 2/search_runner.py",
            "--queries",
            "inputs/query_results.json",
            "--confirm-live",
        ],
    )


def main() -> int:
    args = parse_args()

    if args.mode == "verify":
        run_verify()
    elif args.mode == "handoff":
        run_handoff(args.handoff_limit)
        run_verify()
    elif args.mode == "dashboard":
        run_dashboard()
        run_verify()
    elif args.mode == "all-evidence":
        run_handoff(args.handoff_limit)
        run_dashboard()
        run_verify()
    elif args.mode == "live-search":
        run_live_search(args.confirm_live)
        run_verify()
    else:
        raise SystemExit(f"unknown mode: {args.mode}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
