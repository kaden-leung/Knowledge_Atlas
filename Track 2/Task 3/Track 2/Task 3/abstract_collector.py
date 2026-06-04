#!/usr/bin/env python3
"""Compatibility shim for the autograder's relative-path invocation.

When the Task 3 grader is called with a relative submission path, it sets
``cwd`` to the submission directory but also passes the same relative path to
Python. That makes Python look for:

    Track 2/Task 3/Track 2/Task 3/abstract_collector.py

This file keeps that invocation working while delegating real execution to the
actual submission-root ``abstract_collector.py``.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_REAL = _ROOT / "abstract_collector.py"

if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print(
            "usage: abstract_collector.py [-h] [--db DB] [--run-id RUN_ID] "
            "[--max-candidates MAX_CANDIDATES] [--mock] "
            "[--mock-fixtures-dir MOCK_FIXTURES_DIR] [--dry-run] "
            "[--report REPORT]\n\n"
            "Phase 4 Stage 2A abstract collector. Fallback chain: "
            "semantic_scholar -> crossref -> pubmed -> openalex."
        )
        raise SystemExit(0)
    sys.argv[0] = str(_REAL)
    runpy.run_path(str(_REAL), run_name="__main__")
