"""OpenAlex API client — 4th source in the abstract fallback chain.

OpenAlex exposes a free, unauthenticated REST API. Polite-pool access via the
`?mailto=` query parameter gives reliable ~10 req/s budget. No API key needed.

Reference: https://docs.openalex.org/how-to-use-the-api/api-overview
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

# macOS Python framework installs omit the system CA bundle. Use certifi if available.
try:
    import certifi as _certifi
    _SSL_CTX = ssl.create_default_context(cafile=_certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

POLITE_EMAIL = "kaden-leung@users.noreply.github.com"
BASE = "https://api.openalex.org"


class _RateLimiter:
    """Same pattern as paper_fetcher._RateLimiter — kept local to avoid cross-repo coupling."""

    def __init__(self, min_delay: float, sleep_fn: Callable[[float], None] = time.sleep):
        self._min_delay = min_delay
        self._sleep = sleep_fn
        self._last_call: float = 0.0

    def wait(self) -> None:
        if self._min_delay <= 0:
            return
        elapsed = time.monotonic() - self._last_call
        gap = self._min_delay - elapsed
        if gap > 0:
            self._sleep(gap)
        self._last_call = time.monotonic()


def decode_inverted_index(d: dict[str, list[int]] | None) -> str | None:
    """Reconstruct an abstract from OpenAlex's `abstract_inverted_index` format.

    Input shape: `{"word": [pos, pos, ...], ...}`
    Output: words joined by space in position order, or None if input is empty/None.

    Limitation: punctuation isn't carried in the index, so reconstructed text
    may differ in punctuation placement from the original abstract. Good enough
    for downstream classification; not suitable for verbatim quotation.
    """
    if not d:
        return None
    by_pos: dict[int, str] = {}
    for word, positions in d.items():
        for pos in positions:
            by_pos[pos] = word
    if not by_pos:
        return None
    return " ".join(by_pos[i] for i in sorted(by_pos))


class OpenAlexClient:
    """Free public API; polite-pool via ?mailto=. No API key required."""

    BASE = BASE
    POLITE_EMAIL = POLITE_EMAIL

    def __init__(
        self,
        mailto: str | None = None,
        min_delay: float = 0.12,
        sleep_fn: Callable[[float], None] = time.sleep,
        urlopen: Callable | None = None,
    ):
        self._mailto = mailto or POLITE_EMAIL
        self._limiter = _RateLimiter(min_delay, sleep_fn=sleep_fn)
        # Allow injection for tests; defaults to stdlib urlopen
        self._urlopen = urlopen or urllib.request.urlopen

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_abstract_by_doi(self, doi: str) -> str | None:
        """GET /works/doi:{doi} → decoded abstract or None."""
        if not doi:
            return None
        url = f"{self.BASE}/works/doi:{urllib.parse.quote(doi, safe='')}"
        data = self._get_json(url)
        if not data:
            return None
        return decode_inverted_index(data.get("abstract_inverted_index"))

    def fetch_abstract_by_title_year(self, title: str, year: int | None) -> str | None:
        """GET /works?filter=title.search:{title}[,publication_year:{year}] → first hit's abstract."""
        if not title:
            return None
        filt_parts = [f"title.search:{urllib.parse.quote(title, safe='')}"]
        if year is not None:
            filt_parts.append(f"publication_year:{year}")
        params = {
            "filter": ",".join(filt_parts),
            "per-page": "1",
            "select": "id,title,abstract_inverted_index",
        }
        url = f"{self.BASE}/works?{urllib.parse.urlencode(params, safe=',:')}"
        data = self._get_json(url)
        if not data:
            return None
        results = data.get("results") or []
        if not results:
            return None
        return decode_inverted_index(results[0].get("abstract_inverted_index"))

    def get_oa_pdf_url(self, doi: str) -> str | None:
        """GET /works/doi:{doi} → direct OA PDF URL when the work is open-access.

        OpenAlex's open_access.oa_url points to the best freely accessible copy.
        This is Phase 5's second source in the acquisition cascade (after Unpaywall).
        Returns None when the work is not OA or no URL is available.
        """
        if not doi:
            return None
        url = f"{self.BASE}/works/doi:{urllib.parse.quote(doi, safe='')}"
        data = self._get_json(url)
        if not data:
            return None
        oa = data.get("open_access") or {}
        if oa.get("is_oa") and oa.get("oa_url"):
            return oa["oa_url"]
        return None

    def health_check(self) -> bool:
        """Cheap connectivity probe."""
        url = f"{self.BASE}/works?per-page=1&select=id"
        try:
            data = self._get_json(url)
            return data is not None
        except Exception:
            return False

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    def _get_json(self, url: str) -> dict | None:
        """GET a URL with the polite-pool mailto query param appended; parse JSON.

        Returns None on 404, 410, or any post-retry failure. Raises only on the
        adapter-level invariant 'unexpected'. One retry on 429 / 5xx with a 10s
        sleep; no retry on other 4xx.
        """
        # Append mailto for polite pool
        sep = "&" if "?" in url else "?"
        polite_url = f"{url}{sep}mailto={urllib.parse.quote(self._mailto)}"
        req = urllib.request.Request(
            polite_url,
            headers={"User-Agent": f"ATLAS-Phase4/1.0 (mailto:{self._mailto})"},
        )
        for attempt in range(2):
            self._limiter.wait()
            try:
                with self._urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 410):
                    return None
                if exc.code == 429 or exc.code >= 500:
                    if attempt == 0:
                        time.sleep(10)
                        continue
                # 4xx other than 404/410/429 → give up (non-transient)
                return None
            except urllib.error.URLError:
                if attempt == 0:
                    time.sleep(5)
                    continue
                return None
        return None
