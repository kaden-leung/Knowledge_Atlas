from __future__ import annotations
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone

from .base import CandidateRecord, RateLimiter
from . import normalize_doi, normalize_title

DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)")
_AND_SPLIT_RE = re.compile(r"\s+AND\s+", re.IGNORECASE)
_OR_SPLIT_RE = re.compile(r"\s+OR\s+", re.IGNORECASE)
_QUOTED_RE = re.compile(r'"([^"]+)"')


def _parse_boolean_to_keywords(query: str) -> list[list[str]]:
    """Convert boolean query string to paperscraper keyword format [[OR…] AND [OR…] …]."""
    query = re.sub(r"\s*-review\s*$", "", query.strip())
    and_groups = _AND_SPLIT_RE.split(query)
    result = []
    for group in and_groups:
        group = group.strip().strip("()")
        quoted = _QUOTED_RE.findall(group)
        if quoted:
            result.append(quoted)
        else:
            terms = [t.strip().strip('"') for t in _OR_SPLIT_RE.split(group) if t.strip()]
            result.append(terms if terms else [group.strip('"')])
    return [g for g in result if g]


def _extract_doi_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = DOI_RE.search(url)
    return normalize_doi(m.group(1)) if m else None


class PaperscraperAdapter:
    name = "paperscraper_search"
    discovered_via_tag = "paperscraper_search"
    rate_limit_s = 0.0
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
        from paperscraper.arxiv import get_and_dump_arxiv_papers

        self._limiter.wait()
        keywords = _parse_boolean_to_keywords(query)

        # paperscraper ≥ 0.2 requires a .jsonl extension; older versions used .json.
        # The error "Please provide a filepath with .jsonl extension" means the installed
        # version enforces this. We write JSONL, parse it line-by-line, and discard the file.
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jsonl", prefix="ps_tmp_")
        os.close(tmp_fd)
        try:
            get_and_dump_arxiv_papers(keywords, tmp_path, max_results=num_results)
            raw_results = []
            with open(tmp_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            raw_results.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception as exc:
            raise RuntimeError(f"paperscraper error: {exc}") from exc
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return self._parse(
            raw_results if isinstance(raw_results, list) else [],
            run_id=run_id,
            query=query,
            query_display_id=query_display_id,
            voi_score=voi_score,
        )

    def _parse(
        self,
        hits: list[dict],
        *,
        run_id: str,
        query: str,
        query_display_id: str,
        voi_score: float | None,
    ) -> list[CandidateRecord]:
        records = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i, hit in enumerate(hits, start=1):
            title = hit.get("title", "") or ""
            doi_raw = hit.get("doi")
            doi = normalize_doi(doi_raw) if doi_raw else _extract_doi_from_url(hit.get("url"))

            authors_raw = hit.get("authors", "")
            if isinstance(authors_raw, list):
                authors_raw = ", ".join(str(a) for a in authors_raw)

            first_surname = None
            if authors_raw:
                first = authors_raw.split(",")[0].strip()
                parts = first.split()
                first_surname = parts[-1] if parts else None

            year = None
            date_str = hit.get("date", "")
            if date_str:
                m = re.search(r"\b((?:19|20)\d{2})\b", str(date_str))
                year = int(m.group(1)) if m else None

            venue = hit.get("journal") or hit.get("venue") or "arXiv"
            url = hit.get("url")
            pdf_url = url if url and "arxiv.org" in url else None

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
                doi=doi or None,
                url=url,
                snippet=hit.get("abstract"),
                authors_raw=authors_raw or None,
                first_author_surname=first_surname,
                publication_year=year,
                venue=str(venue) if venue else None,
                cited_by_count=None,
                resource_pdf_url=pdf_url,
            ))
        return records

    def health_check(self) -> bool:
        try:
            from paperscraper.arxiv import get_and_dump_arxiv_papers  # noqa: F401
            return True
        except ImportError:
            return False
