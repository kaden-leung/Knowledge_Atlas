"""Pytest configuration: add Phase 2 and Article_Finder to sys.path."""
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COGS160 = _HERE.parents[2]  # Phase 2 → Task 3 → Track 2 → COGS 160

for _p in (
    str(_HERE),
    str(_COGS160 / "Article_Finder"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FIXTURES_DIR = _HERE / "fixtures"
QUERY_RESULTS_PATH = _HERE.parents[1] / "Task 2" / "Phase 3" / "query_results.json"
