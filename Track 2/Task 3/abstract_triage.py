#!/usr/bin/env python3
"""Task 3 submission entry point — abstract-first triage (classifier + VOI).

Thin submission-root shim required by the course deliverable layout
(`abstract_triage.py` at the submission root). It delegates to the canonical
implementation in `Phase 4/abstract_triage.py` — no logic is duplicated.

The canonical triage orchestrates Stage 1 (metadata screen), Stage 2A (abstract
collection), and Stage 2B (classifier + VOI decision), writing decisions to the
pipeline DB and to `triage_results.json`.

Run (same flags as the canonical script):

    python3 abstract_triage.py --db task3_pipeline_lifecycle.db

See MANIFEST.md → "Submission-root shims".
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parent / "Phase 4" / "abstract_triage.py"

if __name__ == "__main__":
    sys.argv[0] = str(_IMPL)
    runpy.run_path(str(_IMPL), run_name="__main__")
