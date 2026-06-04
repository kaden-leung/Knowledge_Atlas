#!/usr/bin/env python3
"""Task 3 submission entry point — search execution (SerpAPI).

This is a thin submission-root shim required by the course deliverable layout
(`search_runner.py` at the submission root). It does NOT duplicate logic — it
delegates to the canonical implementation in `Phase 2/search_runner.py`, which
calls SerpAPI with the Boolean queries using the `google_scholar` engine and
also drives the `scholarly` and `paperscraper` free fallbacks.

Run (same flags as the canonical script):

    python3 search_runner.py --queries inputs/query_results.json --confirm-live

The Phase-structured project keeps the real code under `Phase 2/`; this root
shim exists so the autograder and the spec's `python3 search_runner.py ...`
command resolve from the submission root. See MANIFEST.md → "Submission-root
shims".
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parent / "Phase 2" / "search_runner.py"

if __name__ == "__main__":
    # Re-exec the canonical Phase 2 implementation as __main__, preserving argv.
    sys.argv[0] = str(_IMPL)
    runpy.run_path(str(_IMPL), run_name="__main__")
