"""Root conftest for Track 2 / Task 3 — portable test collection.

Task 3 reuses code from two sibling checkouts that are NOT part of this
submission: `Article_Finder/` (e.g. `core.ae_corpus_dedupe`) and `Article_Eater/`
(abstract clients, VOI scoring). When this directory is cloned on its own (e.g. a
Knowledge_Atlas-only checkout), those siblings are absent and the suites that
import them would otherwise abort collection with `ModuleNotFoundError`.

This conftest makes the suite *portable*: when the siblings are absent it cleanly
**ignores** the sibling-dependent suites so `pytest` exits 0 (the standalone
suites still run) instead of erroring. Run from a full COGS-160 checkout for the
complete suite.

Note: this file deliberately does NOT touch `sys.path`. Each source module sets
up its own sibling paths, and `Article_Eater/src/core` would shadow
`Article_Finder/core` if added in the wrong order. We only *probe by filesystem*
and decide what to collect.
"""
from __future__ import annotations

import warnings
from pathlib import Path

_HERE = Path(__file__).resolve().parent      # Track 2/Task 3
_COGS160 = _HERE.parents[1]                   # Track 2/Task 3 -> Track 2 -> COGS 160

# Suites whose import chain pulls in the sibling repos (verified empirically: each
# fails with "ModuleNotFoundError: No module named 'core'" when the siblings are
# absent).
_SIBLING_DEPENDENT = [
    "Phase 2/test_adapters.py",
    "Phase 2/test_search_runner.py",
    "Phase 3/test_db_loader.py",
    "Phase 3/test_dedupe.py",
    "Phase 3/test_reference_harvester.py",
    "Phase 4/test_abstract_collector.py",
]

# `core` (the dependency that breaks all six) lives at Article_Finder/core.
_siblings_present = (_COGS160 / "Article_Finder" / "core").is_dir()

collect_ignore: list[str] = []
if not _siblings_present:
    collect_ignore = list(_SIBLING_DEPENDENT)
    warnings.warn(
        "Article_Finder/Article_Eater siblings not found beside this checkout; "
        f"skipping {len(collect_ignore)} suite(s) that require them. Run from a "
        "full COGS-160 checkout for the complete 185-test suite.",
        stacklevel=1,
    )
