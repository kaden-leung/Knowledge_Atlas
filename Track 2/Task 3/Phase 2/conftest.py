"""Pytest configuration: add Phase 2 and Article_Finder to sys.path."""
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TASK3 = _HERE.parent
if str(_TASK3) not in sys.path:
    sys.path.insert(0, str(_TASK3))

from workspace_paths import find_repository  # noqa: E402

_AF_ROOT = find_repository("Article_Finder", _HERE)

for _p in (
    str(_HERE),
    str(_AF_ROOT) if _AF_ROOT else "",
):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

FIXTURES_DIR = _HERE / "fixtures"
# Vendored Task 2 query artifact, local to Task 3 (see inputs/QUERY_PROVENANCE.md).
QUERY_RESULTS_PATH = _HERE.parents[0] / "inputs" / "query_results.json"
