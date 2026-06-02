"""
Task 3 setup verification script.
Run with: python3 setup_verify.py
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COGS160 = ROOT.parents[1]
AE_ROOT = COGS160 / "Article_Eater"
AF_ROOT = COGS160 / "Article_Finder"

# Load .env from Task 3 root so SERPAPI_KEY etc. are available
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"

results: list[tuple[str, str, str]] = []  # (check, status, detail)


def check(name: str, fn):
    try:
        detail = fn()
        results.append((name, PASS, detail or ""))
    except Exception as exc:
        results.append((name, FAIL, str(exc)[:80]))


# ── Python ────────────────────────────────────────────────────────────────────
check("Python ≥ 3.10", lambda: (
    f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info >= (3, 10) else (_ for _ in ()).throw(RuntimeError("need 3.10+"))
))

# ── SQLite ────────────────────────────────────────────────────────────────────
check("SQLite ≥ 3.30 (FILTER WHERE)", lambda: (
    sqlite3.sqlite_version
    if tuple(int(x) for x in sqlite3.sqlite_version.split(".")) >= (3, 30)
    else (_ for _ in ()).throw(RuntimeError("too old"))
))

# ── Search / scraper packages ─────────────────────────────────────────────────
def _check_serpapi():
    from serpapi import GoogleSearch  # noqa
    return "google-search-results installed"

check("google-search-results (SerpAPI)", _check_serpapi)

def _check_scholarly():
    from scholarly import scholarly  # noqa
    return "scholarly installed"

check("scholarly", _check_scholarly)

def _check_paperscraper():
    import paperscraper  # noqa
    return f"paperscraper {paperscraper.__version__}"

check("paperscraper", _check_paperscraper)

def _check_scidownl():
    from scidownl import scihub_download  # noqa
    return "scidownl installed"

check("scidownl", _check_scidownl)

# ── Core packages already in venv ─────────────────────────────────────────────
def _check_pytest():
    import pytest
    return f"pytest {pytest.__version__}"

check("pytest", _check_pytest)

def _check_pdfplumber():
    import pdfplumber
    return f"pdfplumber {pdfplumber.__version__}"

check("pdfplumber", _check_pdfplumber)

def _check_sentence_transformers():
    import sentence_transformers
    return f"sentence-transformers {sentence_transformers.__version__}"

check("sentence-transformers", _check_sentence_transformers)

# ── Reuse imports ─────────────────────────────────────────────────────────────
def _check_ae_corpus_dedupe():
    sys.path.insert(0, str(AF_ROOT))
    from core.ae_corpus_dedupe import normalize_doi, normalize_title
    assert normalize_doi("https://doi.org/10.1000/xyz") == "10.1000/xyz"
    return "normalize_doi/normalize_title ok"

check("Article_Finder core.ae_corpus_dedupe", _check_ae_corpus_dedupe)

def _check_paper_fetcher():
    sys.path.insert(0, str(AE_ROOT))
    sys.path.insert(0, str(AE_ROOT / "src"))
    from services.paper_fetcher import SemanticScholarClient, CrossRefClient, PubMedClient, UnpaywallClient
    return "S2/CrossRef/PubMed/Unpaywall clients ok"

check("Article_Eater paper_fetcher clients", _check_paper_fetcher)

def _check_voi_scoring():
    spec = importlib.util.spec_from_file_location(
        "voi_scoring",
        str(AE_ROOT / "src" / "cmr" / "voi_scoring.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sample = [{"gap_type": "DIRECTION", "confidence": 0.3, "effect_size": 0.5, "maturity": "preliminary"}]
    result = mod.score_voi(sample)
    assert result[0]["voi_score"] == 0.4
    return f"score_voi ok (sample VOI={result[0]['voi_score']})"

check("Article_Eater voi_scoring (direct load)", _check_voi_scoring)

def _check_classifier():
    sys.path.insert(0, str(AF_ROOT))
    from triage.classifier import HierarchicalClassifier
    return "HierarchicalClassifier ok"

check("Article_Finder HierarchicalClassifier", _check_classifier)

def _check_atlas_shared():
    import atlas_shared
    return f"atlas-shared {atlas_shared.__version__ if hasattr(atlas_shared, '__version__') else 'ok'}"

check("atlas-shared", _check_atlas_shared)

# ── API keys ──────────────────────────────────────────────────────────────────
def _check_serpapi_key():
    key = os.environ.get("SERPAPI_KEY", "")
    if not key:
        raise RuntimeError("SERPAPI_KEY not set — export SERPAPI_KEY=<your-key>")
    return f"set ({len(key)} chars)"

# WARN-only for SERPAPI_KEY (not blocking)
try:
    _check_serpapi_key()
    results.append(("SERPAPI_KEY env var", PASS, "set"))
except Exception as exc:
    results.append(("SERPAPI_KEY env var", WARN, str(exc)))

def _check_ncbi():
    key = os.environ.get("NCBI_API_KEY", "")
    return f"set ({len(key)} chars)" if key else "(not set — rate limit 3 req/s)"

results.append(("NCBI_API_KEY (optional)", WARN if not os.environ.get("NCBI_API_KEY") else PASS,
                _check_ncbi()))

# ── Directory structure ───────────────────────────────────────────────────────
for subdir in [
    "Phase 2/adapters", "Phase 2/fixtures",
    "Phase 3/migrations",
    "Phase 4/fixtures",
    "Phase 5/fixtures",
]:
    path = ROOT / subdir
    if path.is_dir():
        results.append((f"Dir: {subdir}", PASS, ""))
    else:
        results.append((f"Dir: {subdir}", FAIL, "missing — run setup again"))

# ── Print results ─────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("  Track 2 Task 3 — Setup Verification")
print("=" * 70)
max_name = max(len(r[0]) for r in results)
for name, status, detail in results:
    line = f"  {name:<{max_name}}  {status}"
    if detail:
        line += f"  ({detail})"
    print(line)

failures = [r for r in results if FAIL in r[1]]
warnings = [r for r in results if WARN in r[1]]
print("=" * 70)
if failures:
    print(f"  {len(failures)} FAIL(s) — fix before building")
elif warnings:
    print(f"  All checks pass. {len(warnings)} warning(s) — see above.")
else:
    print("  All checks pass. Ready to build.")
print()
