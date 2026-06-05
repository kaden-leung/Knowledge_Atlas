from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TASK3 = _HERE.parents[1]
if str(_TASK3) not in sys.path:
    sys.path.insert(0, str(_TASK3))

from workspace_paths import require_repository  # noqa: E402

_AF_ROOT = require_repository("Article_Finder", _HERE)
if str(_AF_ROOT) not in sys.path:
    sys.path.insert(0, str(_AF_ROOT))

from core.ae_corpus_dedupe import (  # noqa: E402
    normalize_doi as _normalize_doi,
    normalize_title,
)

__all__ = ["normalize_doi", "normalize_title"]


def normalize_doi(value: str | None) -> str | None:
    """Wrap ae_corpus_dedupe normalize_doi; return None instead of empty string."""
    result = _normalize_doi(value)
    return result if result else None
