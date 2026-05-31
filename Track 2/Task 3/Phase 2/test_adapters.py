"""Adapter-layer unit tests — all run offline via MockAdapter or direct patching."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from conftest import FIXTURES_DIR
from adapters.base import CandidateRecord
from adapters.serpapi_adapter import SerpAPIAdapter
from adapters.scholarly_adapter import ScholarlyAdapter
from adapters.paperscraper_adapter import PaperscraperAdapter
from adapters.mock_adapter import MockAdapter


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _search_kwargs(query_display_id="sc3"):
    return dict(run_id="RUN-TEST", query_display_id=query_display_id, voi_score=None)


# ---------------------------------------------------------------------------
# SerpAPI adapter (6 tests)
# ---------------------------------------------------------------------------

def test_serpapi_parse_titles():
    """Fixture sc3 → 5 records; first title matches expected paper."""
    adapter = MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR)
    results = adapter.search("q", 10, **_search_kwargs())
    assert len(results) == 5
    assert "Sensorimotor brain dynamics" in results[0].title_raw


def test_serpapi_doi_extraction():
    """DOI extracted from PNAS canonical URL in fixture position 1."""
    adapter = MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR)
    results = adapter.search("q", 10, **_search_kwargs())
    assert results[0].doi == "10.1073/pnas.1912264116"


@pytest.mark.parametrize("url,expected_doi", [
    # Canonical DOI URL (doi.org redirect)
    ("https://doi.org/10.1016/j.neuron.2012.09.005", "10.1016/j.neuron.2012.09.005"),
    # Publisher page with DOI path segment (PNAS style)
    ("https://www.pnas.org/doi/10.1073/pnas.1912264116", "10.1073/pnas.1912264116"),
    # bioRxiv preprint URL with DOI-shaped path
    ("https://www.biorxiv.org/content/10.1101/2026.01.15.123456", "10.1101/2026.01.15.123456"),
])
def test_doi_extraction_regex_three_url_patterns(url, expected_doi):
    """DOI regex extracts correctly from three distinct URL patterns."""
    from adapters.serpapi_adapter import _extract_doi_from_url
    assert _extract_doi_from_url(url) == expected_doi


def test_serpapi_pdf_extraction():
    """PDF resource link extracted for fixture position 1."""
    adapter = MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR)
    results = adapter.search("q", 10, **_search_kwargs())
    assert results[0].resource_pdf_url == "https://www.pnas.org/doi/pdf/10.1073/pnas.1912264116"


@patch("adapters.serpapi_adapter.GoogleSearch")
def test_serpapi_retry_on_rate_limit(mock_gs):
    """Rate-limit error on first call → sleep 30 s → retries → returns results."""
    sleep_calls: list[float] = []
    mock_inst = MagicMock()
    mock_inst.get_dict.side_effect = [
        {"error": "rate_limit exceeded 429 too many requests"},
        {"organic_results": []},
    ]
    mock_gs.return_value = mock_inst

    adapter = SerpAPIAdapter(api_key="test_key", sleep_fn=lambda s: sleep_calls.append(s))
    results = adapter.search("q", 5, run_id="R", query_display_id="q1", voi_score=None)

    assert results == []
    assert any(s == 30 for s in sleep_calls), f"Expected 30s sleep, got: {sleep_calls}"
    assert mock_inst.get_dict.call_count == 2


@patch("adapters.serpapi_adapter.GoogleSearch")
def test_serpapi_no_retry_on_400(mock_gs):
    """Non-transient 'invalid api key' error → raises ValueError immediately, no sleep."""
    sleep_calls: list[float] = []
    mock_inst = MagicMock()
    mock_inst.get_dict.return_value = {"error": "invalid api key provided"}
    mock_gs.return_value = mock_inst

    adapter = SerpAPIAdapter(api_key="bad_key", sleep_fn=lambda s: sleep_calls.append(s))
    with pytest.raises(ValueError, match="non-transient"):
        adapter.search("q", 5, run_id="R", query_display_id="q1", voi_score=None)

    assert sleep_calls == []
    assert mock_inst.get_dict.call_count == 1


def test_serpapi_missing_key_raises(monkeypatch):
    """No SERPAPI_KEY env var and no api_key kwarg → EnvironmentError at construction."""
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="SERPAPI_KEY"):
        SerpAPIAdapter()


# ---------------------------------------------------------------------------
# Scholarly adapter (3 tests)
# ---------------------------------------------------------------------------

def test_scholarly_rate_limit_sleep(monkeypatch):
    """Rate limiter invokes sleep_fn when the adapter is called within the interval."""
    sleep_calls: list[float] = []
    monkeypatch.setattr("scholarly.scholarly.search_pubs", lambda q: iter([]))

    adapter = ScholarlyAdapter(sleep_fn=lambda s: sleep_calls.append(s))
    adapter._limiter._last_call = time.monotonic()  # simulate very recent prior call

    adapter.search("q", 5, run_id="R", query_display_id="q1", voi_score=None)

    assert len(sleep_calls) == 1
    assert sleep_calls[0] > 0


def test_scholarly_block_raises_runtime(monkeypatch):
    """'cannot fetch' exception from scholarly → RuntimeError mentioning 'blocked'."""

    def _blocked(query):
        raise Exception("cannot fetch: Google Scholar blocked after captcha")

    monkeypatch.setattr("scholarly.scholarly.search_pubs", _blocked)

    adapter = ScholarlyAdapter()
    with pytest.raises(RuntimeError, match="blocked"):
        adapter.search("q", 5, run_id="R", query_display_id="q1", voi_score=None)


def test_scholarly_parse_fixture():
    """scholarly_response_sc3.json → 3 records; year, citations, and DOI correct."""
    adapter = MockAdapter(ScholarlyAdapter(), FIXTURES_DIR)
    results = adapter.search("q", 10, **_search_kwargs())

    assert len(results) == 3
    assert results[0].publication_year == 2019
    assert results[0].cited_by_count == 176
    assert results[0].doi == "10.1073/pnas.1912264116"


# ---------------------------------------------------------------------------
# Paperscraper adapter (2 tests)
# ---------------------------------------------------------------------------

def test_paperscraper_parse_fixture():
    """paperscraper_response_sc3.json → 2 records; venues from fixture journal field."""
    adapter = MockAdapter(PaperscraperAdapter(), FIXTURES_DIR)
    results = adapter.search("q", 10, **_search_kwargs())

    assert len(results) == 2
    assert results[0].venue == "bioRxiv"
    assert results[1].venue == "arXiv"


def test_paperscraper_venue_defaults_to_arxiv():
    """Entry with no journal/venue field → venue defaults to 'arXiv'."""
    adapter = PaperscraperAdapter()
    hits = [
        {
            "title": "A Preprint Paper",
            "authors": "J Doe",
            "date": "2025-01-01",
            "abstract": "Abstract here.",
            "doi": None,
            "url": "https://arxiv.org/abs/2501.12345",
        }
    ]
    results = adapter._parse(hits, run_id="R", query="q", query_display_id="q1", voi_score=None)
    assert results[0].venue == "arXiv"


# ---------------------------------------------------------------------------
# Mock adapter + credit cost (2 tests)
# ---------------------------------------------------------------------------

def test_mock_adapter_reads_fixture():
    """MockAdapter wrapping SerpAPI reads sc3 fixture → 5 CandidateRecords, correct tag."""
    adapter = MockAdapter(SerpAPIAdapter(api_key="dummy"), FIXTURES_DIR)
    results = adapter.search("q", 10, **_search_kwargs())

    assert len(results) == 5
    for r in results:
        assert isinstance(r, CandidateRecord)
        assert r.discovered_via == "serpapi_scholar"


@patch("adapters.serpapi_adapter.GoogleSearch")
def test_serpapi_engine_param(mock_gs):
    """SerpAPI always passes engine='google_scholar' to GoogleSearch, never bare 'google'."""
    mock_inst = MagicMock()
    mock_inst.get_dict.return_value = {"organic_results": []}
    mock_gs.return_value = mock_inst

    SerpAPIAdapter(api_key="test_key").search(
        "q", 5, run_id="R", query_display_id="q1", voi_score=None
    )

    call_params = mock_gs.call_args[0][0]
    assert call_params["engine"] == "google_scholar"


def test_credit_cost_per_call():
    """SerpAPI costs 1 credit per call; scholarly and paperscraper cost 0."""
    assert SerpAPIAdapter(api_key="k").credit_cost_per_call == 1
    assert ScholarlyAdapter().credit_cost_per_call == 0
    assert PaperscraperAdapter().credit_cost_per_call == 0
