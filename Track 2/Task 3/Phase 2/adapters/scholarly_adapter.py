from __future__ import annotations
import re
import time
from datetime import datetime, timezone

from scholarly import scholarly as _scholarly

from .base import CandidateRecord, RateLimiter
from . import normalize_doi, normalize_title

DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)")


def _extract_doi_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = DOI_RE.search(url)
    return normalize_doi(m.group(1)) if m else None


def _first_surname(authors: list[str] | None) -> str | None:
    if not authors:
        return None
    first = str(authors[0]).strip()
    parts = first.split()
    return parts[-1] if parts else None


class ScholarlyAdapter:
    name = "scholarly_search"
    discovered_via_tag = "scholarly_search"
    rate_limit_s = 5.0
    credit_cost_per_call = 0

    def __init__(self, sleep_fn=time.sleep):
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
        try:
            gen = _scholarly.search_pubs(query)
            hits: list = []
            for _ in range(num_results):
                try:
                    hits.append(next(gen))
                except StopIteration:
                    break
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in ("cannot fetch", "blocked", "captcha", "too many")):
                raise RuntimeError(
                    f"scholarly: Google Scholar blocked this query — {exc}"
                ) from exc
            raise RuntimeError(f"scholarly: unexpected error — {exc}") from exc

        return self._parse(
            hits,
            run_id=run_id,
            query=query,
            query_display_id=query_display_id,
            voi_score=voi_score,
        )

    def _parse(
        self,
        hits: list,
        *,
        run_id: str,
        query: str,
        query_display_id: str,
        voi_score: float | None,
    ) -> list[CandidateRecord]:
        records = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i, pub in enumerate(hits, start=1):
            bib = pub.get("bib", {}) if isinstance(pub, dict) else getattr(pub, "bib", {})
            title = bib.get("title", "") or ""
            authors = bib.get("author", []) or []
            if isinstance(authors, str):
                authors = [a.strip() for a in authors.split(" and ")]

            year_raw = bib.get("year") or bib.get("pub_year")
            year = int(year_raw) if year_raw and str(year_raw).isdigit() else None
            venue = bib.get("venue") or bib.get("journal") or bib.get("booktitle")
            abstract = bib.get("abstract")

            pub_url = pub.get("pub_url") if isinstance(pub, dict) else getattr(pub, "pub_url", None)
            eprint_url = pub.get("eprint_url") if isinstance(pub, dict) else getattr(pub, "eprint_url", None)
            cited_by = pub.get("num_citations") if isinstance(pub, dict) else getattr(pub, "num_citations", None)

            doi = _extract_doi_from_url(pub_url) or _extract_doi_from_url(eprint_url)
            authors_raw = ", ".join(str(a) for a in authors) if authors else None

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
                url=pub_url or None,
                snippet=abstract,
                authors_raw=authors_raw,
                first_author_surname=_first_surname(authors if isinstance(authors, list) else None),
                publication_year=year,
                venue=str(venue) if venue else None,
                cited_by_count=int(cited_by) if cited_by is not None else None,
                resource_pdf_url=eprint_url or None,
            ))
        return records

    def health_check(self) -> bool:
        try:
            gen = _scholarly.search_pubs("test")
            next(gen)
            return True
        except Exception:
            return False
