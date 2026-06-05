#!/usr/bin/env python3
"""Phase 2 Search Runner — fan out boolean queries across SerpAPI, scholarly, paperscraper."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

_HERE = Path(__file__).resolve().parent
_TASK3 = _HERE.parent
if str(_TASK3) not in sys.path:
    sys.path.insert(0, str(_TASK3))

from workspace_paths import find_repository  # noqa: E402

_AF_ROOT = find_repository("Article_Finder", _HERE)
if _AF_ROOT and str(_AF_ROOT) not in sys.path:
    sys.path.insert(0, str(_AF_ROOT))

from adapters.base import CandidateRecord  # noqa: E402
from adapters import normalize_doi  # noqa: E402

MAX_QUERY_LEN = 256
DEFAULT_MAX_CREDITS = 50
DEFAULT_NUM_RESULTS = 10
SCHEMA_VERSION = "1.1.0"

# Title-only dedup guard: titles shorter than this many "significant" words
# (>= 3 chars each) are too generic to safely collapse. Examples that would
# otherwise collide: "Introduction", "Discussion", "Editorial".
MIN_TITLE_WORDS_FOR_DEDUPE = 4


def _is_title_safe_for_dedupe(title_normalized: str) -> bool:
    """A title is safe to use as a dedup key only if it has enough content."""
    if not title_normalized:
        return False
    significant = [w for w in title_normalized.split() if len(w) >= 3]
    return len(significant) >= MIN_TITLE_WORDS_FOR_DEDUPE


def _merge_citation_count(existing: int | None, incoming: int | None) -> int | None:
    """Take the maximum non-None citation count (citation counts grow over time)."""
    if existing is None:
        return incoming
    if incoming is None:
        return existing
    return max(existing, incoming)


def utc_now_iso() -> str:
    """Pinned ISO-8601 UTC format ending in 'Z' (RFC 3339 compatible)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SearchRunReport(NamedTuple):
    run_id: str
    queries_processed: int
    queries_skipped: dict
    per_source_stats: dict
    credits_used: int
    candidates_raw: int
    candidates_after_cross_query_dedupe: int
    null_result_queries: int


def make_run_id(now: datetime | None = None) -> str:
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"RUN-{ts}"


def make_candidate_id(run_id: str, idx: int) -> str:
    return f"CAND-{run_id}-{idx:06d}"


def preflight_query(query: str) -> tuple[bool, str | None]:
    if len(query) > MAX_QUERY_LEN:
        return False, "query_too_long"
    return True, None


def cross_source_dedupe(candidates: list[CandidateRecord]) -> list[CandidateRecord]:
    by_doi: dict[str, CandidateRecord] = {}
    no_doi: list[CandidateRecord] = []

    for c in candidates:
        if c.doi:
            if c.doi in by_doi:
                existing = by_doi[c.doi]
                if c.discovered_via not in existing.merged_from_sources:
                    existing.merged_from_sources.append(c.discovered_via)
                existing.cited_by_count = _merge_citation_count(
                    existing.cited_by_count, c.cited_by_count
                )
            else:
                by_doi[c.doi] = c
        else:
            no_doi.append(c)

    by_title: dict[str, CandidateRecord] = {}
    title_unsafe: list[CandidateRecord] = []
    for c in no_doi:
        key = c.title_normalized
        if not _is_title_safe_for_dedupe(key):
            # Too generic to safely dedup; keep as a distinct record
            title_unsafe.append(c)
            continue
        if key in by_title:
            existing = by_title[key]
            if c.discovered_via not in existing.merged_from_sources:
                existing.merged_from_sources.append(c.discovered_via)
            existing.cited_by_count = _merge_citation_count(
                existing.cited_by_count, c.cited_by_count
            )
        else:
            by_title[key] = c

    return list(by_doi.values()) + list(by_title.values()) + title_unsafe


def cross_query_dedupe(
    new: list[CandidateRecord], existing: list[CandidateRecord]
) -> list[CandidateRecord]:
    result = list(existing)
    doi_map: dict[str, CandidateRecord] = {c.doi: c for c in result if c.doi}
    title_map: dict[str, CandidateRecord] = {
        c.title_normalized: c
        for c in result
        if not c.doi and _is_title_safe_for_dedupe(c.title_normalized)
    }

    for c in new:
        if c.doi and c.doi in doi_map:
            existing_rec = doi_map[c.doi]
            for q in c.merged_from_queries:
                if q not in existing_rec.merged_from_queries:
                    existing_rec.merged_from_queries.append(q)
            existing_rec.cited_by_count = _merge_citation_count(
                existing_rec.cited_by_count, c.cited_by_count
            )
        elif (
            not c.doi
            and _is_title_safe_for_dedupe(c.title_normalized)
            and c.title_normalized in title_map
        ):
            existing_rec = title_map[c.title_normalized]
            for q in c.merged_from_queries:
                if q not in existing_rec.merged_from_queries:
                    existing_rec.merged_from_queries.append(q)
            existing_rec.cited_by_count = _merge_citation_count(
                existing_rec.cited_by_count, c.cited_by_count
            )
        else:
            result.append(c)
            if c.doi:
                doi_map[c.doi] = c
            elif _is_title_safe_for_dedupe(c.title_normalized):
                title_map[c.title_normalized] = c

    return result


def run(
    queries_path: Path,
    output_path: Path,
    null_path: Path,
    run_log_path: Path,
    *,
    adapters: list,
    run_id: str | None = None,
    max_queries: int | None = None,
    num_results: int = DEFAULT_NUM_RESULTS,
    max_credits: int = DEFAULT_MAX_CREDITS,
    dry_run: bool = False,
) -> SearchRunReport:
    run_id = run_id or make_run_id()
    started_at = utc_now_iso()

    with open(queries_path) as f:
        query_data = json.load(f)

    all_queries = query_data.get("queries", [])
    queries = all_queries[:max_queries] if max_queries is not None else all_queries

    credits_used = 0
    skipped: dict[str, int] = {}
    null_results: list[dict] = []
    skipped_queries: list[dict] = []
    all_candidates: list[CandidateRecord] = []
    total_raw = 0

    per_source_stats: dict[str, dict] = {
        a.name: {"queries_run": 0, "results_raw": 0, "retries": 0, "errors": 0}
        for a in adapters
    }

    # Circuit breaker state: track consecutive rate-limit errors per source.
    # After CIRCUIT_OPEN_THRESHOLD consecutive 429s, mark the source degraded
    # for the rest of this run and log circuit_open status.
    _CIRCUIT_OPEN_THRESHOLD = 3
    _consecutive_429s: dict[str, int] = {a.name: 0 for a in adapters}
    _circuit_open: dict[str, bool] = {a.name: False for a in adapters}

    for q_index, qrow in enumerate(queries, start=1):
        boolean_query = qrow.get("boolean_query", "")
        display_id = qrow.get("display_id", "unknown")
        step = qrow.get("step_number")
        display_key = f"{display_id}-step{step}" if step is not None else display_id
        voi_score = qrow.get("voi_score")
        queried_at = utc_now_iso()

        if not dry_run:
            print(
                f"[{q_index}/{len(queries)}] {display_key} "
                f"(credits used: {credits_used}/{max_credits})",
                file=sys.stderr,
                flush=True,
            )

        ok, skip_reason = preflight_query(boolean_query)
        if not ok:
            skipped[skip_reason] = skipped.get(skip_reason, 0) + 1
            skipped_queries.append({
                "discovered_query_display_id": display_key,
                "discovered_query": boolean_query,
                "skip_reason": skip_reason,
                "skipped_at": queried_at,
            })
            continue

        query_candidates: list[CandidateRecord] = []

        for adapter in adapters:
            # Credit cap pre-check (SerpAPI only)
            if adapter.credit_cost_per_call > 0:
                if credits_used + adapter.credit_cost_per_call > max_credits:
                    skipped["credit_cap_reached"] = skipped.get("credit_cap_reached", 0) + 1
                    skipped_queries.append({
                        "discovered_query_display_id": display_key,
                        "discovered_query": boolean_query,
                        "skip_reason": "credit_cap_reached",
                        "skipped_at": queried_at,
                    })
                    continue

            # Circuit breaker: skip this source for the rest of the run if open
            if _circuit_open[adapter.name]:
                skipped["circuit_open"] = skipped.get("circuit_open", 0) + 1
                print(
                    f"[CIRCUIT_OPEN] {adapter.name} skipped for '{display_key}' "
                    f"(3 consecutive 429s this run)",
                    file=sys.stderr,
                )
                continue

            per_source_stats[adapter.name]["queries_run"] += 1

            if dry_run:
                continue

            # Pessimistic credit accounting: count the credit BEFORE the call.
            # If adapter.search raises after the network spent the credit, we
            # still record the spend. The credit cap pre-check above guarantees
            # this can never push credits_used over max_credits.
            credits_used += adapter.credit_cost_per_call
            try:
                results = adapter.search(
                    boolean_query,
                    num_results,
                    run_id=run_id,
                    query_display_id=display_key,
                    voi_score=voi_score,
                )
                per_source_stats[adapter.name]["results_raw"] += len(results)
                total_raw += len(results)
                query_candidates.extend(results)
                _consecutive_429s[adapter.name] = 0  # success resets the counter
            except Exception as exc:
                per_source_stats[adapter.name]["errors"] += 1
                err_str = str(exc).lower()
                is_rate_limit = any(kw in err_str for kw in ("429", "rate limit", "ratelimit", "too many"))
                if is_rate_limit:
                    _consecutive_429s[adapter.name] += 1
                    if _consecutive_429s[adapter.name] >= _CIRCUIT_OPEN_THRESHOLD:
                        _circuit_open[adapter.name] = True
                        print(
                            f"[CIRCUIT_OPEN] {adapter.name}: {_CIRCUIT_OPEN_THRESHOLD} "
                            f"consecutive 429s — skipping for rest of run",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"[WARN] {adapter.name} 429 on '{display_key}' "
                            f"({_consecutive_429s[adapter.name]}/{_CIRCUIT_OPEN_THRESHOLD}): {exc}",
                            file=sys.stderr,
                        )
                else:
                    _consecutive_429s[adapter.name] = 0
                    print(
                        f"[WARN] {adapter.name} error on '{display_key}': {exc}",
                        file=sys.stderr,
                    )

        if not dry_run:
            deduped_for_query = cross_source_dedupe(query_candidates)
            all_candidates = cross_query_dedupe(deduped_for_query, all_candidates)

            if not query_candidates:
                null_results.append({
                    "discovered_query_display_id": display_key,
                    "discovered_query": boolean_query,
                    "source_voi_score": voi_score,
                    "reason": "zero_results_across_all_sources",
                    "queried_at": queried_at,
                })

    ended_at = utc_now_iso()

    report = SearchRunReport(
        run_id=run_id,
        queries_processed=len(queries),
        queries_skipped=skipped,
        per_source_stats=per_source_stats,
        credits_used=credits_used,
        candidates_raw=total_raw,
        candidates_after_cross_query_dedupe=len(all_candidates),
        null_result_queries=len(null_results),
    )

    if dry_run:
        print(
            f"[DRY-RUN] run_id={run_id} queries={len(queries)} "
            f"sources={[a.name for a in adapters]}",
            file=sys.stderr,
        )
        return report

    output = {
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "generated_at": ended_at,
            "input_query_count": len(all_queries),
            "queries_processed": len(queries) - sum(skipped.values()),
            "queries_skipped": skipped,
            "sources_enabled": [a.name for a in adapters],
            "per_source_stats": per_source_stats,
            "credits_used": credits_used,
            "credits_max": max_credits,
            "candidates_total_raw": total_raw,
            "candidates_after_dedupe": len(all_candidates),
            "null_result_queries": len(null_results),
            "mock_mode": any(type(a).__name__ == "MockAdapter" for a in adapters),
            "serpapi_engine": "google_scholar",
        },
        "results": [
            {"candidate_id": make_candidate_id(run_id, i), **_candidate_to_dict(c)}
            for i, c in enumerate(all_candidates, start=1)
        ],
        "null_results": null_results,
        "skipped_queries": skipped_queries,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    with open(null_path, "w") as f:
        json.dump(null_results, f, indent=2)

    run_log = {
        "run_id": run_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "sources": [a.name for a in adapters],
        "queries_processed": len(queries),
        "credits_used": credits_used,
        "per_source_stats": per_source_stats,
        "null_result_queries": len(null_results),
        "skipped_queries": len(skipped_queries),
    }
    with open(run_log_path, "w") as f:
        json.dump(run_log, f, indent=2)

    return report


def _candidate_to_dict(c: CandidateRecord) -> dict:
    return {
        "discovery_run_id": c.discovery_run_id,
        "discovered_via": c.discovered_via,
        "merged_from_sources": c.merged_from_sources,
        "merged_from_queries": c.merged_from_queries,
        "discovered_query": c.discovered_query,
        "discovered_query_display_id": c.discovered_query_display_id,
        "source_voi_score": c.source_voi_score,
        "discovered_at": c.discovered_at,
        "result_position": c.result_position,
        "title_raw": c.title_raw,
        "title_normalized": c.title_normalized,
        "doi": c.doi,
        "url": c.url,
        "snippet": c.snippet,
        "authors_raw": c.authors_raw,
        "first_author_surname": c.first_author_surname,
        "publication_year": c.publication_year,
        "venue": c.venue,
        "cited_by_count": c.cited_by_count,
        "resource_pdf_url": c.resource_pdf_url,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 3 Phase 2 — Search Runner")
    parser.add_argument(
        "--queries",
        default=str(_HERE.parents[0] / "inputs" / "query_results.json"),
        help="Path to vendored Task 2 query_results.json (see inputs/QUERY_PROVENANCE.md)",
    )
    parser.add_argument("--output", default=str(_HERE / "search_results.json"))
    parser.add_argument("--null-output", default=str(_HERE / "null_results.json"))
    parser.add_argument("--run-log", default=str(_HERE / "run_log.json"))
    parser.add_argument(
        "--sources",
        default="serpapi,scholarly,paperscraper",
        help="Comma-separated subset of: serpapi,scholarly,paperscraper",
    )
    parser.add_argument(
        "--mock-from",
        metavar="DIR",
        help="Fixture directory for mock mode (no network, no credits)",
    )
    parser.add_argument("--num-results", type=int, default=DEFAULT_NUM_RESULTS)
    parser.add_argument("--max-credits", type=int, default=DEFAULT_MAX_CREDITS)
    parser.add_argument("--max-queries", type=int, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true", help="No network, no JSON write")
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Required for live network calls (prevents accidental credit spend)",
    )
    args = parser.parse_args(argv)

    enabled = [s.strip() for s in args.sources.split(",") if s.strip()]
    fixture_dir = Path(args.mock_from) if args.mock_from else None
    use_mock = fixture_dir is not None

    if not use_mock and not args.confirm_live and not args.dry_run:
        print(
            "ERROR: Live network calls require --confirm-live.\n"
            "  Use --mock-from Phase\\ 2/fixtures for offline testing.\n"
            "  Pass --confirm-live only when you intend to spend SerpAPI credits.",
            file=sys.stderr,
        )
        return 1

    from adapters.serpapi_adapter import SerpAPIAdapter
    from adapters.scholarly_adapter import ScholarlyAdapter
    from adapters.paperscraper_adapter import PaperscraperAdapter
    from adapters.mock_adapter import MockAdapter

    adapter_instances = []

    if "serpapi" in enabled:
        try:
            real = SerpAPIAdapter()
        except EnvironmentError:
            if not use_mock:
                print("ERROR: SERPAPI_KEY not set.", file=sys.stderr)
                return 1
            real = SerpAPIAdapter(api_key="mock_key_unused")
        adapter_instances.append(MockAdapter(real, fixture_dir) if use_mock else real)

    if "scholarly" in enabled:
        real_s = ScholarlyAdapter()
        adapter_instances.append(MockAdapter(real_s, fixture_dir) if use_mock else real_s)

    if "paperscraper" in enabled:
        real_p = PaperscraperAdapter()
        adapter_instances.append(MockAdapter(real_p, fixture_dir) if use_mock else real_p)

    report = run(
        queries_path=Path(args.queries),
        output_path=Path(args.output),
        null_path=Path(args.null_output),
        run_log_path=Path(args.run_log),
        adapters=adapter_instances,
        run_id=args.run_id,
        max_queries=args.max_queries,
        num_results=args.num_results,
        max_credits=args.max_credits,
        dry_run=args.dry_run,
    )

    print(
        f"Run {report.run_id}: {report.candidates_after_cross_query_dedupe} candidates, "
        f"{report.credits_used} credits, {report.null_result_queries} null results",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
