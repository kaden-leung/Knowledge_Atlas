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

if __name__ == "__main__":
    sys.argv[0] = str(_IMPL)
    runpy.run_path(str(_IMPL), run_name="__main__")
