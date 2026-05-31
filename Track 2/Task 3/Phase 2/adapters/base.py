from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class CandidateRecord:
    discovery_run_id: str
    discovered_via: str
    merged_from_sources: list[str]
    merged_from_queries: list[str]
    discovered_query: str
    discovered_query_display_id: str
    source_voi_score: float | None
    discovered_at: str
    result_position: int
    title_raw: str
    title_normalized: str
    doi: str | None
    url: str | None
    snippet: str | None
    authors_raw: str | None
    first_author_surname: str | None
    publication_year: int | None
    venue: str | None
    cited_by_count: int | None
    resource_pdf_url: str | None


@runtime_checkable
class HarvesterAdapter(Protocol):
    name: str
    discovered_via_tag: str
    rate_limit_s: float
    credit_cost_per_call: int

    def search(
        self,
        query: str,
        num_results: int,
        *,
        run_id: str,
        query_display_id: str,
        voi_score: float | None,
    ) -> list[CandidateRecord]: ...

    def health_check(self) -> bool: ...


class RateLimiter:
    def __init__(self, min_interval_s: float, sleep_fn=time.sleep):
        self._min_interval = min_interval_s
        self._sleep = sleep_fn
        self._last_call: float = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_call
        gap = self._min_interval - elapsed
        if gap > 0:
            self._sleep(gap)
        self._last_call = time.monotonic()
