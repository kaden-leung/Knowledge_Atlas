from __future__ import annotations
import json
from pathlib import Path
from typing import Union

from .base import CandidateRecord
from .serpapi_adapter import SerpAPIAdapter
from .scholarly_adapter import ScholarlyAdapter
from .paperscraper_adapter import PaperscraperAdapter

_RealAdapter = Union[SerpAPIAdapter, ScholarlyAdapter, PaperscraperAdapter]

_SOURCE_PREFIX = {
    "serpapi_scholar": "serpapi",
    "scholarly_search": "scholarly",
    "paperscraper_search": "paperscraper",
}

_EMPTY_FIXTURE: dict = {
    "serpapi_scholar": {"organic_results": []},
    "scholarly_search": [],
    "paperscraper_search": [],
}


class MockAdapter:
    """Reads fixture files and delegates parsing to the real adapter's _parse method."""

    def __init__(self, real_adapter: _RealAdapter, fixture_dir: Path):
        self._real = real_adapter
        self._fixture_dir = Path(fixture_dir)

    @property
    def name(self) -> str:
        return self._real.name

    @property
    def discovered_via_tag(self) -> str:
        return self._real.discovered_via_tag

    @property
    def rate_limit_s(self) -> float:
        return 0.0

    @property
    def credit_cost_per_call(self) -> int:
        return self._real.credit_cost_per_call

    def search(
        self,
        query: str,
        num_results: int,
        *,
        run_id: str,
        query_display_id: str,
        voi_score: float | None,
    ) -> list[CandidateRecord]:
        raw = self._load_fixture(query_display_id)
        return self._real._parse(
            raw,
            run_id=run_id,
            query=query,
            query_display_id=query_display_id,
            voi_score=voi_score,
        )

    def _load_fixture(self, query_display_id: str) -> dict | list:
        prefix = _SOURCE_PREFIX.get(self._real.name, self._real.name)
        safe_id = query_display_id.lower().replace(" ", "_").replace("-", "_")
        candidates = [
            self._fixture_dir / f"{prefix}_response_{safe_id}.json",
            self._fixture_dir / f"{prefix}_response_default.json",
        ]
        for path in candidates:
            if path.exists():
                with open(path) as f:
                    return json.load(f)
        return _EMPTY_FIXTURE[self._real.name]

    def health_check(self) -> bool:
        return True
