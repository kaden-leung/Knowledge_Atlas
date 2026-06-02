"""Unit tests for openalex_client.py — all mocked, no network."""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from openalex_client import OpenAlexClient, decode_inverted_index


# ---------------------------------------------------------------------------
# decode_inverted_index
# ---------------------------------------------------------------------------

def test_decode_inverted_index_basic():
    idx = {"the": [0, 4], "quick": [1], "brown": [2], "fox": [3], "lazy": [5], "dog": [6]}
    assert decode_inverted_index(idx) == "the quick brown fox the lazy dog"


def test_decode_inverted_index_none_returns_none():
    assert decode_inverted_index(None) is None
    assert decode_inverted_index({}) is None


# ---------------------------------------------------------------------------
# Helper to build a mock HTTP response context manager
# ---------------------------------------------------------------------------

def _make_response(payload: dict, status: int = 200):
    """Return a MagicMock that supports `with urlopen(...) as resp: resp.read()`."""
    body = json.dumps(payload).encode("utf-8")

    class _Resp:
        def __enter__(self_inner):
            return self_inner
        def __exit__(self_inner, *a):
            return False
        def read(self_inner):
            return body

    return _Resp()


# ---------------------------------------------------------------------------
# fetch_abstract_by_doi
# ---------------------------------------------------------------------------

def test_fetch_abstract_by_doi_returns_decoded_abstract():
    payload = {
        "id": "https://openalex.org/W123",
        "abstract_inverted_index": {"This": [0], "is": [1], "a": [2], "test": [3]}
    }
    mock_urlopen = MagicMock(return_value=_make_response(payload))
    client = OpenAlexClient(urlopen=mock_urlopen, sleep_fn=lambda s: None)

    abstract = client.fetch_abstract_by_doi("10.1234/test.abc")

    assert abstract == "This is a test"
    assert mock_urlopen.called
    # Polite pool: URL must include mailto
    called_url = mock_urlopen.call_args[0][0].full_url
    assert "mailto=" in called_url
    assert "/works/doi:" in called_url


def test_fetch_abstract_by_doi_returns_none_on_empty_doi():
    client = OpenAlexClient(sleep_fn=lambda s: None)
    assert client.fetch_abstract_by_doi("") is None
    assert client.fetch_abstract_by_doi(None) is None


def test_fetch_abstract_by_doi_returns_none_when_no_abstract_index():
    payload = {"id": "https://openalex.org/W123", "title": "No abstract here"}
    mock_urlopen = MagicMock(return_value=_make_response(payload))
    client = OpenAlexClient(urlopen=mock_urlopen, sleep_fn=lambda s: None)

    assert client.fetch_abstract_by_doi("10.1234/no-abs") is None


def test_fetch_abstract_by_doi_404_returns_none():
    import urllib.error
    err = urllib.error.HTTPError(
        url="https://api.openalex.org/works/doi:10.x/y", code=404,
        msg="Not Found", hdrs=None, fp=None
    )
    mock_urlopen = MagicMock(side_effect=err)
    client = OpenAlexClient(urlopen=mock_urlopen, sleep_fn=lambda s: None)

    assert client.fetch_abstract_by_doi("10.x/y") is None


# ---------------------------------------------------------------------------
# fetch_abstract_by_title_year
# ---------------------------------------------------------------------------

def test_fetch_abstract_by_title_year_first_hit():
    payload = {
        "results": [
            {"id": "W1", "title": "First", "abstract_inverted_index": {"foo": [0], "bar": [1]}},
            {"id": "W2", "title": "Second", "abstract_inverted_index": {"qux": [0]}},
        ]
    }
    mock_urlopen = MagicMock(return_value=_make_response(payload))
    client = OpenAlexClient(urlopen=mock_urlopen, sleep_fn=lambda s: None)

    abstract = client.fetch_abstract_by_title_year("any title", 2024)

    assert abstract == "foo bar"
    # Per-page filter must be honored (we only ask for 1 result)
    called_url = mock_urlopen.call_args[0][0].full_url
    assert "per-page=1" in called_url
    assert "publication_year:2024" in called_url


def test_fetch_abstract_by_title_year_empty_results_returns_none():
    payload = {"results": []}
    mock_urlopen = MagicMock(return_value=_make_response(payload))
    client = OpenAlexClient(urlopen=mock_urlopen, sleep_fn=lambda s: None)

    assert client.fetch_abstract_by_title_year("nonexistent", 2024) is None


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------

def test_get_oa_pdf_url_returns_url_when_oa():
    """get_oa_pdf_url returns the oa_url when the work is open access."""
    payload = {
        "id": "https://openalex.org/W123",
        "open_access": {"is_oa": True, "oa_url": "https://example.com/paper.pdf"}
    }
    mock_urlopen = MagicMock(return_value=_make_response(payload))
    client = OpenAlexClient(urlopen=mock_urlopen, sleep_fn=lambda s: None)
    assert client.get_oa_pdf_url("10.1234/test.abc") == "https://example.com/paper.pdf"


def test_get_oa_pdf_url_returns_none_when_not_oa():
    """get_oa_pdf_url returns None when is_oa is False."""
    payload = {"id": "https://openalex.org/W123", "open_access": {"is_oa": False, "oa_url": None}}
    mock_urlopen = MagicMock(return_value=_make_response(payload))
    client = OpenAlexClient(urlopen=mock_urlopen, sleep_fn=lambda s: None)
    assert client.get_oa_pdf_url("10.1234/test.abc") is None


def test_rate_limit_invokes_sleep_between_calls():
    sleep_calls: list[float] = []
    mock_urlopen = MagicMock(
        side_effect=[
            _make_response({"abstract_inverted_index": {"a": [0]}}),
            _make_response({"abstract_inverted_index": {"b": [0]}}),
        ]
    )
    client = OpenAlexClient(
        urlopen=mock_urlopen,
        min_delay=0.1,
        sleep_fn=lambda s: sleep_calls.append(s),
    )
    # First call: limiter.wait() with no prior call → no sleep
    client.fetch_abstract_by_doi("10.x/a")
    # Second call: limiter.wait() now sees a recent call → sleep should fire
    client.fetch_abstract_by_doi("10.x/b")

    assert any(s > 0 for s in sleep_calls), f"Expected at least one sleep > 0; got {sleep_calls}"
