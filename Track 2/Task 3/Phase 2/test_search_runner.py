"""Search-runner orchestration tests — all offline; no network, no credits."""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from conftest import FIXTURES_DIR, QUERY_RESULTS_PATH
from adapters.base import CandidateRecord
from adapters import normalize_title
from adapters.serpapi_adapter import SerpAPIAdapter
from adapters.scholarly_adapter import ScholarlyAdapter
from adapters.paperscraper_adapter import PaperscraperAdapter
from adapters.mock_adapter import MockAdapter
from search_runner import (
    run,
    cross_source_dedupe,
    cross_query_dedupe,
    preflight_query,
    SearchRunReport,
    SCHEMA_VERSION,
)

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_adapter(name="test_src", candidates=None, credit_cost=0):
    a = MagicMock()
    a.name = name
    a.discovered_via_tag = name
    a.rate_limit_s = 0.0
    a.credit_cost_per_call = credit_cost
    a.search.return_value = candidates if candidates is not None else []
    return a


def _candidate(
    *,
    doi: str | None = None,
    discovered_via: str = "test_src",
    title_raw: str = "Test Paper",
    merged_from_sources: list[str] | None = None,
    merged_from_queries: list[str] | None = None,
    query_display_id: str = "Q1-step1",
) -> CandidateRecord:
    return CandidateRecord(
        discovery_run_id="RUN-TEST",
        discovered_via=discovered_via,
        merged_from_sources=merged_from_sources if merged_from_sources is not None else [discovered_via],
        merged_from_queries=merged_from_queries if merged_from_queries is not None else [query_display_id],
        discovered_query="test query",
        discovered_query_display_id=query_display_id,
        source_voi_score=None,
        discovered_at="2026-05-27T00:00:00+00:00",
        result_position=1,
        title_raw=title_raw,
        title_normalized=normalize_title(title_raw),
        doi=doi,
        url=None,
        snippet=None,
        authors_raw=None,
        first_author_surname=None,
        publication_year=None,
        venue=None,
        cited_by_count=None,
        resource_pdf_url=None,
    )


def _write_queries(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps({"queries": rows}))


# ---------------------------------------------------------------------------
# Runner orchestration (6 tests)
# ---------------------------------------------------------------------------

def test_every_query_processed_once_per_source(tmp_path):
    """Each adapter.search is called exactly once per query."""
    adapter = _fake_adapter()
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": None},
        {"boolean_query": "q2", "display_id": "Q2", "step_number": 1, "voi_score": None},
    ])
    run(tmp_path / "q.json", tmp_path / "out.json", tmp_path / "null.json",
        tmp_path / "log.json", adapters=[adapter], run_id="RUN-T")
    assert adapter.search.call_count == 2


def test_credits_equal_serpapi_calls(tmp_path):
    """credits_used == number of queries processed by the serpapi adapter."""
    adapter = _fake_adapter(name="serpapi_scholar", credit_cost=1)
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": None},
        {"boolean_query": "q2", "display_id": "Q2", "step_number": 1, "voi_score": None},
    ])
    report = run(tmp_path / "q.json", tmp_path / "out.json", tmp_path / "null.json",
                 tmp_path / "log.json", adapters=[adapter], run_id="RUN-T")
    assert report.credits_used == 2
    assert adapter.search.call_count == 2


def test_max_credits_skips_overflow(tmp_path):
    """With max_credits=1 and 3 queries, only the first is processed; 2 are skipped."""
    adapter = _fake_adapter(name="serpapi_scholar", credit_cost=1)
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": None},
        {"boolean_query": "q2", "display_id": "Q2", "step_number": 1, "voi_score": None},
        {"boolean_query": "q3", "display_id": "Q3", "step_number": 1, "voi_score": None},
    ])
    report = run(tmp_path / "q.json", tmp_path / "out.json", tmp_path / "null.json",
                 tmp_path / "log.json", adapters=[adapter], run_id="RUN-T", max_credits=1)
    assert adapter.search.call_count == 1
    assert report.queries_skipped.get("credit_cap_reached", 0) == 2


def test_every_record_has_run_provenance(tmp_path):
    """Runner passes run_id to adapter.search; output records include provenance fields."""
    rec = _candidate(doi="10.1000/test.1", discovered_via="mock_src")
    adapter = _fake_adapter(name="mock_src", candidates=[rec])
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": None},
    ])
    out = tmp_path / "out.json"
    run(tmp_path / "q.json", out, tmp_path / "null.json", tmp_path / "log.json",
        adapters=[adapter], run_id="RUN-PROV")
    # Runner must forward run_id to the adapter
    assert adapter.search.call_args[1]["run_id"] == "RUN-PROV"
    # Output records must contain both provenance fields
    data = json.loads(out.read_text())
    assert "discovery_run_id" in data["results"][0]
    assert data["results"][0]["discovered_via"] == "mock_src"


def test_zero_results_records_null(tmp_path):
    """Query that returns no candidates from any source → recorded in null_results."""
    adapter = _fake_adapter(candidates=[])
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": None},
    ])
    run(tmp_path / "q.json", tmp_path / "out.json", tmp_path / "null.json",
        tmp_path / "log.json", adapters=[adapter], run_id="RUN-T")
    null_data = json.loads((tmp_path / "null.json").read_text())
    assert len(null_data) == 1
    assert null_data[0]["discovered_query_display_id"] == "Q1-step1"


def test_query_too_long_skipped(tmp_path):
    """Query string over 256 chars → skipped with reason 'query_too_long'."""
    adapter = _fake_adapter()
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "x" * 257, "display_id": "Q1", "step_number": 1, "voi_score": None},
    ])
    report = run(tmp_path / "q.json", tmp_path / "out.json", tmp_path / "null.json",
                 tmp_path / "log.json", adapters=[adapter], run_id="RUN-T")
    assert report.queries_skipped.get("query_too_long", 0) == 1
    adapter.search.assert_not_called()


# ---------------------------------------------------------------------------
# Output schema (1 test)
# ---------------------------------------------------------------------------

def test_output_validates_schema(tmp_path):
    """Output JSON has metadata.schema_version, results list, null_results, skipped_queries."""
    adapter = _fake_adapter()
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": 0.9},
    ])
    out = tmp_path / "out.json"
    run(tmp_path / "q.json", out, tmp_path / "null.json", tmp_path / "log.json",
        adapters=[adapter], run_id="RUN-SCHEMA")
    data = json.loads(out.read_text())
    assert data["metadata"]["schema_version"] == SCHEMA_VERSION
    assert data["metadata"]["run_id"] == "RUN-SCHEMA"
    assert isinstance(data["results"], list)
    assert isinstance(data["null_results"], list)
    assert isinstance(data["skipped_queries"], list)


# ---------------------------------------------------------------------------
# Deduplication (3 tests)
# ---------------------------------------------------------------------------

def test_cross_source_dedupe_same_doi():
    """Two candidates with the same DOI from different sources → merged into one record."""
    doi = "10.1073/pnas.1912264116"
    c1 = _candidate(doi=doi, discovered_via="serpapi_scholar")
    c2 = _candidate(doi=doi, discovered_via="scholarly_search")
    result = cross_source_dedupe([c1, c2])
    assert len(result) == 1
    assert set(result[0].merged_from_sources) == {"serpapi_scholar", "scholarly_search"}


def test_cross_source_dedupe_same_title_no_doi():
    """Two candidates with no DOI but same normalized title → merged into one record."""
    title = "Unique Paper Title Without DOI"
    c1 = _candidate(doi=None, discovered_via="serpapi_scholar", title_raw=title)
    c2 = _candidate(doi=None, discovered_via="paperscraper_search", title_raw=title)
    result = cross_source_dedupe([c1, c2])
    assert len(result) == 1
    assert set(result[0].merged_from_sources) == {"serpapi_scholar", "paperscraper_search"}


def test_cross_query_dedupe_same_paper():
    """Same DOI appearing in two different queries → merged_from_queries contains both."""
    doi = "10.1073/pnas.1912264116"
    c1 = _candidate(doi=doi, query_display_id="Q1-step1", merged_from_queries=["Q1-step1"])
    c2 = _candidate(doi=doi, query_display_id="Q2-step1", merged_from_queries=["Q2-step1"])
    result = cross_query_dedupe([c2], [c1])
    assert len(result) == 1
    assert set(result[0].merged_from_queries) == {"Q1-step1", "Q2-step1"}


def test_first_seen_wins_for_scalar_fields():
    """When two same-DOI candidates merge: first-seen wins for most scalars; cited_by_count takes the max."""
    doi = "10.1073/pnas.1912264116"
    first = _candidate(doi=doi, discovered_via="serpapi_scholar", title_raw="First-seen Title")
    first.cited_by_count = 176
    second = _candidate(doi=doi, discovered_via="scholarly_search", title_raw="Second-seen Title")
    second.cited_by_count = 180
    result = cross_source_dedupe([first, second])
    assert len(result) == 1
    merged = result[0]
    # Scalar fields other than cited_by_count keep the first-seen value
    assert merged.title_raw == "First-seen Title"
    # cited_by_count takes max (citation counts grow over time)
    assert merged.cited_by_count == 180
    # Only the source list takes the union
    assert set(merged.merged_from_sources) == {"serpapi_scholar", "scholarly_search"}


# ---------------------------------------------------------------------------
# DOI normalization (1 test)
# ---------------------------------------------------------------------------

def test_doi_normalized_lowercase():
    """All DOIs in mock-adapter output are lowercase (normalize_doi applied)."""
    adapter = MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR)
    results = adapter.search("q", 10, run_id="R", query_display_id="sc3", voi_score=None)
    for r in results:
        if r.doi:
            assert r.doi == r.doi.lower(), f"DOI not lowercase: {r.doi}"


# ---------------------------------------------------------------------------
# Dry-run and determinism (2 tests)
# ---------------------------------------------------------------------------

def test_dry_run_no_writes_no_network(tmp_path):
    """dry_run=True → output files not written, adapter.search never called."""
    adapter = _fake_adapter()
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": None},
    ])
    out = tmp_path / "out.json"
    run(tmp_path / "q.json", out, tmp_path / "null.json", tmp_path / "log.json",
        adapters=[adapter], run_id="RUN-T", dry_run=True)
    assert not out.exists()
    adapter.search.assert_not_called()


def test_mock_mode_deterministic(tmp_path):
    """Two mock runs with same fixture produce the same candidate count."""
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "sc3", "step_number": None, "voi_score": None},
    ])

    def _make_run(run_id: str) -> SearchRunReport:
        adapters = [MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR)]
        return run(
            tmp_path / "q.json",
            tmp_path / f"out_{run_id}.json",
            tmp_path / f"null_{run_id}.json",
            tmp_path / f"log_{run_id}.json",
            adapters=adapters,
            run_id=run_id,
        )

    r1 = _make_run("RUN-A")
    r2 = _make_run("RUN-B")
    assert r1.candidates_after_cross_query_dedupe == r2.candidates_after_cross_query_dedupe


# ---------------------------------------------------------------------------
# Smoke test against real Task 2 input (1 test)
# ---------------------------------------------------------------------------

def test_smoke_run_real_queries_input(tmp_path):
    """Load actual query_results.json; run 3 queries via mock adapters — no exceptions."""
    if not QUERY_RESULTS_PATH.exists():
        pytest.skip(f"query_results.json not found at {QUERY_RESULTS_PATH}")

    adapters = [
        MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR),
        MockAdapter(ScholarlyAdapter(), FIXTURES_DIR),
        MockAdapter(PaperscraperAdapter(), FIXTURES_DIR),
    ]
    report = run(
        QUERY_RESULTS_PATH,
        tmp_path / "out.json",
        tmp_path / "null.json",
        tmp_path / "log.json",
        adapters=adapters,
        run_id="RUN-SMOKE",
        max_queries=3,
    )
    assert report.run_id == "RUN-SMOKE"
    assert report.queries_processed == 3


def test_cli_refuses_live_without_confirm_flag(tmp_path, monkeypatch, capsys):
    """CLI exits 1 with an error to stderr when no mock dir, no --dry-run, no --confirm-live."""
    from search_runner import main

    # Ensure SERPAPI_KEY exists so the refusal isn't due to missing key
    monkeypatch.setenv("SERPAPI_KEY", "test_key_unused")

    rc = main([
        "--queries", str(QUERY_RESULTS_PATH),
        "--output", str(tmp_path / "out.json"),
        "--null-output", str(tmp_path / "null.json"),
        "--run-log", str(tmp_path / "log.json"),
        "--sources", "serpapi",
    ])
    captured = capsys.readouterr()

    assert rc == 1
    assert "confirm-live" in captured.err.lower()
    # And nothing was written
    assert not (tmp_path / "out.json").exists()


# ---------------------------------------------------------------------------
# New tests for v1.2.0 SCs (SC-15 supplementary, SC-22, SC-24 supplementary,
# SC-30, SC-31, SC-32)
# ---------------------------------------------------------------------------

def test_credit_counted_even_on_adapter_exception(tmp_path):
    """SC-15: credit is debited even if adapter.search raises after the network spent it."""
    adapter = MagicMock()
    adapter.name = "serpapi_scholar"
    adapter.discovered_via_tag = "serpapi_scholar"
    adapter.rate_limit_s = 0.0
    adapter.credit_cost_per_call = 1
    adapter.search.side_effect = RuntimeError("mid-call failure after credit spent")

    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": None},
        {"boolean_query": "q2", "display_id": "Q2", "step_number": 1, "voi_score": None},
    ])
    report = run(
        tmp_path / "q.json", tmp_path / "out.json", tmp_path / "null.json",
        tmp_path / "log.json", adapters=[adapter], run_id="RUN-T",
    )
    # Both calls raised, but both credits are debited
    assert report.credits_used == 2
    assert adapter.search.call_count == 2


def test_short_titles_not_collapsed_by_dedup():
    """SC-22: two records sharing only a generic short title are kept distinct."""
    # Both candidates have title that normalizes to fewer than 4 significant words.
    c1 = _candidate(doi=None, discovered_via="serpapi_scholar", title_raw="Introduction")
    c2 = _candidate(doi=None, discovered_via="paperscraper_search", title_raw="Introduction")
    result = cross_source_dedupe([c1, c2])
    # Must NOT collapse — generic titles aren't safe dedup keys
    assert len(result) == 2


def test_cited_by_count_takes_max_on_merge():
    """SC-24: cited_by_count uses max-wins across a merge, not first-seen."""
    doi = "10.1073/pnas.1912264116"
    older = _candidate(doi=doi, discovered_via="serpapi_scholar")
    older.cited_by_count = 100
    newer = _candidate(doi=doi, discovered_via="scholarly_search")
    newer.cited_by_count = 250
    result = cross_source_dedupe([older, newer])
    assert len(result) == 1
    assert result[0].cited_by_count == 250  # higher wins regardless of order


def test_voi_score_passes_through_to_candidate(tmp_path):
    """SC-30: source_voi_score on the output record equals voi_score on the input query."""
    rec = _candidate(doi="10.1000/test.1", discovered_via="serpapi_scholar")
    rec.source_voi_score = 0.85  # the adapter is responsible for this assignment
    adapter = _fake_adapter(name="serpapi_scholar", candidates=[rec], credit_cost=1)

    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": 0.85},
    ])
    out = tmp_path / "out.json"
    run(tmp_path / "q.json", out, tmp_path / "null.json", tmp_path / "log.json",
        adapters=[adapter], run_id="RUN-VOI")

    # The runner must have forwarded the input voi_score to the adapter
    assert adapter.search.call_args[1]["voi_score"] == 0.85
    # And the output record carries the same value verbatim
    data = json.loads(out.read_text())
    assert data["results"][0]["source_voi_score"] == 0.85


def test_mock_mode_flag_in_metadata(tmp_path):
    """SC-31: metadata.mock_mode is True iff any adapter is a MockAdapter."""
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": None},
    ])
    # Case 1: a real-ish (non-mock) MagicMock adapter → mock_mode should be False
    real_like = _fake_adapter(name="some_real_source", candidates=[])
    out1 = tmp_path / "out1.json"
    run(tmp_path / "q.json", out1, tmp_path / "null1.json", tmp_path / "log1.json",
        adapters=[real_like], run_id="RUN-NOMOCK")
    assert json.loads(out1.read_text())["metadata"]["mock_mode"] is False

    # Case 2: a MockAdapter → mock_mode should be True
    mock_adapter = MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR)
    out2 = tmp_path / "out2.json"
    run(tmp_path / "q.json", out2, tmp_path / "null2.json", tmp_path / "log2.json",
        adapters=[mock_adapter], run_id="RUN-MOCK")
    assert json.loads(out2.read_text())["metadata"]["mock_mode"] is True


def test_timestamps_end_in_z(tmp_path):
    """SC-32: every timestamp in every output matches YYYY-MM-DDTHH:MM:SSZ."""
    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": None},
        {"boolean_query": "x" * 257, "display_id": "Q2", "step_number": 1, "voi_score": None},
    ])
    adapter = MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR)
    out = tmp_path / "out.json"
    null_path = tmp_path / "null.json"
    log_path = tmp_path / "log.json"
    run(tmp_path / "q.json", out, null_path, log_path,
        adapters=[adapter], run_id="RUN-TS")

    out_data = json.loads(out.read_text())
    null_data = json.loads(null_path.read_text())
    log_data = json.loads(log_path.read_text())

    # Collect every timestamp field we expect in outputs
    timestamps: list[str] = [
        out_data["metadata"]["generated_at"],
        log_data["started_at"],
        log_data["ended_at"],
    ]
    for r in out_data["results"]:
        timestamps.append(r["discovered_at"])
    for nr in out_data["null_results"]:
        timestamps.append(nr["queried_at"])
    for nr in null_data:
        timestamps.append(nr["queried_at"])
    for sq in out_data["skipped_queries"]:
        timestamps.append(sq["skipped_at"])

    assert timestamps, "Expected at least one timestamp in outputs"
    for ts in timestamps:
        assert _TS_RE.match(ts), f"Timestamp not in YYYY-MM-DDTHH:MM:SSZ form: {ts!r}"


def test_output_validates_against_json_schema(tmp_path):
    """The output JSON validates against schema/search_results.schema.json."""
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema package not installed; skipping schema validation")

    schema_path = Path(__file__).parent / "schema" / "search_results.schema.json"
    schema = json.loads(schema_path.read_text())

    _write_queries(tmp_path / "q.json", [
        {"boolean_query": "q1", "display_id": "Q1", "step_number": 1, "voi_score": 0.5},
    ])
    adapter = MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR)
    out = tmp_path / "out.json"
    run(tmp_path / "q.json", out, tmp_path / "null.json", tmp_path / "log.json",
        adapters=[adapter], run_id="RUN-20260527-143200")

    data = json.loads(out.read_text())
    jsonschema.validate(data, schema)
