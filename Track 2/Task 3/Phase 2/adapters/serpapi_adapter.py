from __future__ import annotations
import os
import re
import time
from datetime import datetime, timezone

from serpapi import GoogleSearch

from .base import CandidateRecord, RateLimiter
from . import normalize_doi, normalize_title

DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)")
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_RATE_LIMIT_KEYWORDS = ("ratelimit", "rate limit", "rate_limit", "429", "too many requests")
_NONTRANSIENT_KEYWORDS = ("invalid api", "unauthorized", "bad request", "invalid key")


def _extract_doi_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = DOI_RE.search(url)
    return normalize_doi(m.group(1)) if m else None


def _extract_year(text: str) -> int | None:
    m = YEAR_RE.search(text or "")
    return int(m.group(1)) if m else None


def _extract_venue(summary: str) -> str | None:
    # Format: "Authors - Venue, Year - publisher"
    parts = summary.split(" - ")
    if len(parts) >= 2:
        venue_year = parts[1]
        venue = re.sub(r",?\s*(?:19|20)\d{2}\s*$", "", venue_year).strip()
        return venue or None
    return None


def _authors_from_summary(summary: str) -> str | None:
    parts = summary.split(" - ")
    return parts[0].strip() if parts else None


def _first_surname(authors_raw: str | None) -> str | None:
    if not authors_raw:
        return None
    first = authors_raw.split(",")[0].strip()
    parts = first.split()
    return parts[-1] if parts else None


class SerpAPIAdapter:
    name = "serpapi_scholar"
    discovered_via_tag = "serpapi_scholar"
    rate_limit_s = 0.0
    credit_cost_per_call = 1

    def __init__(self, api_key: str | None = None, sleep_fn=time.sleep):
        key = api_key or os.environ.get("SERPAPI_KEY", "")
        if not key:
            raise EnvironmentError(
                "SERPAPI_KEY not set — export SERPAPI_KEY=<your-key> or pass api_key= explicitly"
            )
        self._key = key
        self._sleep = sleep_fn
        self._limiter = RateLimiter(self.rate_limit_s, sleep_fn=sleep_fn)

    def search(
        self,
        query: str,
        num_results: int,
        *,
        run_id: str,
        query_display_id: str,
        voi_score: float | None,
    ) -> list[CandidateRecord]:
        self._limiter.wait()
        params = {
            "engine": "google_scholar",
            "q": query,
            "num": num_results,
            "api_key": self._key,
        }
        raw = self._call_with_retry(params)
        return self._parse(
            raw,
            run_id=run_id,
            query=query,
            query_display_id=query_display_id,
            voi_score=voi_score,
        )

    def _call_with_retry(self, params: dict) -> dict:
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                client = GoogleSearch(params)
                result = client.get_dict()
                if "error" in result:
                    err = str(result["error"]).lower()
                    if any(k in err for k in _NONTRANSIENT_KEYWORDS):
                        raise ValueError(f"SerpAPI non-transient error: {result['error']}")
                    if attempt == 0:
                        delay = 30 if any(k in err for k in _RATE_LIMIT_KEYWORDS) else 5
                        self._sleep(delay)
                        continue
                    raise RuntimeError(f"SerpAPI transient error after retry: {result['error']}")
                return result
            except (TimeoutError, ConnectionError, OSError) as exc:
                last_exc = exc
                if attempt == 0:
                    self._sleep(5)
                    continue
                raise RuntimeError(f"SerpAPI network error after retry: {exc}") from exc
        if last_exc:
            raise RuntimeError(f"SerpAPI failed: {last_exc}") from last_exc
        return {}

    def _parse(
        self,
        raw: dict,
        *,
        run_id: str,
        query: str,
        query_display_id: str,
        voi_score: float | None,
    ) -> list[CandidateRecord]:
        records = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i, hit in enumerate(raw.get("organic_results", []), start=1):
            title = hit.get("title", "") or ""
            url = hit.get("link", "") or ""

            doi = _extract_doi_from_url(url)
            if not doi:
                for res in hit.get("resources", []):
                    doi = _extract_doi_from_url(res.get("link", ""))
                    if doi:
                        break

            pub_info = hit.get("publication_info") or {}
            summary = pub_info.get("summary", "") or ""
            authors_list = pub_info.get("authors") or []
            if authors_list:
                authors_raw = ", ".join(a.get("name", "") for a in authors_list)
            else:
                authors_raw = _authors_from_summary(summary)

            pdf_url = None
            for res in hit.get("resources", []):
                if res.get("file_format", "").upper() == "PDF":
                    pdf_url = res.get("link")
                    break

            cited = hit.get("cited_by") or {}
            cited_by_count = cited.get("total") if isinstance(cited, dict) else None

            records.append(CandidateRecord(
                discovery_run_id=run_id,
                discovered_via=self.discovered_via_tag,
                merged_from_sources=[self.discovered_via_tag],
                merged_from_queries=[query_display_id],
                discovered_query=query,
                discovered_query_display_id=query_display_id,
                source_voi_score=voi_score,
                discovered_at=now,
                result_position=i,
                title_raw=title,
                title_normalized=normalize_title(title),
                doi=doi,
                url=url or None,
                snippet=hit.get("snippet"),
                authors_raw=authors_raw or None,
                first_author_surname=_first_surname(authors_raw),
                publication_year=_extract_year(summary),
                venue=_extract_venue(summary),
                cited_by_count=cited_by_count,
                resource_pdf_url=pdf_url,
            ))
        return records

    def health_check(self) -> bool:
        try:
            client = GoogleSearch({"engine": "google_scholar", "q": "test", "num": 1, "api_key": self._key})
            result = client.get_dict()
            return "error" not in result
        except Exception:
            return False
