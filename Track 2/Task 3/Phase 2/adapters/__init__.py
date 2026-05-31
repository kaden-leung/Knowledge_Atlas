from __future__ import annotations
import sys
from pathlib import Path

_COGS160 = Path(__file__).resolve().parents[4]
_AF_ROOT = _COGS160 / "Article_Finder"
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
