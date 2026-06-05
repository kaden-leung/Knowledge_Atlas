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

import sqlite3
import sys
import warnings
from pathlib import Path

_HERE = Path(__file__).resolve().parent      # Track 2/Task 3
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from workspace_paths import find_repository  # noqa: E402

# Suites whose import chain pulls in the sibling repos (verified empirically: each
# fails with "ModuleNotFoundError: No module named 'core'" when the siblings are
# absent).
_SIBLING_DEPENDENT = [
    "Phase 2/test_adapters.py",
    "Phase 2/test_search_runner.py",
    "Phase 3/test_db_loader.py",
    "Phase 3/test_dedupe.py",
    "Phase 3/test_idempotency.py",
    "Phase 3/test_reference_harvester.py",
    "Phase 4/test_abstract_collector.py",
]

# `core` lives at Article_Finder/core. Article Eater is also required by the
# abstract-collection suites.
_article_finder = find_repository("Article_Finder", _HERE)
_article_eater = find_repository("Article_Eater", _HERE)
_siblings_present = bool(
    _article_finder
    and (_article_finder / "core").is_dir()
    and _article_eater
    and (_article_eater / "src").is_dir()
)

collect_ignore: list[str] = []
if not _siblings_present:
    collect_ignore = list(_SIBLING_DEPENDENT)
    warnings.warn(
        "Article_Finder/Article_Eater siblings not found beside this checkout; "
        f"skipping {len(collect_ignore)} suite(s) that require them. Run from a "
        "full COGS-160 checkout for the complete offline test suite.",
        stacklevel=1,
    )

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = _HERE / "Phase 3" / "migrations"


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all Phase 3 migrations to a connection in order."""
    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        conn.executescript(sql_file.read_text(encoding="utf-8"))
    conn.commit()


def fresh_db(tmp_path):
    """Return a path to a freshly migrated, empty SQLite DB in tmp_path.

    All integration tests that write data should use this fixture instead of
    opening the committed task3_pipeline_lifecycle.db, which is a read-only
    evidence artifact for the chain verifier.
    """
    import pytest  # noqa: F401 — imported here so conftest doesn't require pytest at import time
    db_path = tmp_path / "test_pipeline.db"
    conn = sqlite3.connect(str(db_path))
    _apply_migrations(conn)
    conn.close()
    return db_path


# Register as a pytest fixture so tests can request it by name
try:
    import pytest

    @pytest.fixture
    def fresh_db_path(tmp_path):
        """Pytest fixture: freshly migrated empty DB in a temp directory."""
        return fresh_db(tmp_path)

except ImportError:
    pass
