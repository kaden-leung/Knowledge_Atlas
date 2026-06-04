#!/usr/bin/env python3
"""Task 3 submission entry point — abstract collection (fallback chain).

Thin submission-root shim required by the course deliverable layout
(`abstract_collector.py` at the submission root). It delegates to the canonical
implementation in `Phase 4/abstract_collector.py` — no logic is duplicated.

The canonical collector resolves an abstract for each candidate through a
four-source fallback chain:

    semantic_scholar  ->  crossref  ->  pubmed  ->  openalex

(`semantic_scholar` = `SemanticScholarClient`; `crossref` = `CrossRefClient`;
`pubmed` = `PubMedClient`; `openalex` = OpenAlex inverted-index decoder.)

Run (same flags as the canonical script):

    python3 abstract_collector.py --results Phase\\ 2/search_results.json

See MANIFEST.md → "Submission-root shims".
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parent / "Phase 4" / "abstract_collector.py"
_IMPL_DIR = _IMPL.parent

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
    if str(_IMPL_DIR) not in sys.path:
        sys.path.insert(0, str(_IMPL_DIR))
    sys.argv[0] = str(_IMPL)
    runpy.run_path(str(_IMPL), run_name="__main__")
