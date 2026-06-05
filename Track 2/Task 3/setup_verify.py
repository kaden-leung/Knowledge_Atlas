"""
Task 3 setup verification script.

Usage:
  python3 setup_verify.py                 # full mode (default)
  python3 setup_verify.py --mode pr-only  # lightweight grader/CI check only
  python3 setup_verify.py --mode full     # all checks including sibling repos
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workspace_paths import find_repository  # noqa: E402

AE_ROOT = find_repository("Article_Eater", ROOT)
AF_ROOT = find_repository("Article_Finder", ROOT)

# Load .env from Task 3 root so SERPAPI_KEY etc. are available
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"

results: list[tuple[str, str, str]] = []


def check(name: str, fn):
    try:
        detail = fn()
        results.append((name, PASS, detail or ""))
    except Exception as exc:
        results.append((name, FAIL, str(exc)[:80]))


def warn_check(name: str, fn):
    """Run fn; always records WARN or PASS (never FAIL — doesn't block)."""
    try:
        detail = fn()
        results.append((name, PASS, detail or ""))
    except Exception as exc:
        results.append((name, WARN, str(exc)[:80]))


# ---------------------------------------------------------------------------
# Tier 1 — always run (pr-only and full)
# ---------------------------------------------------------------------------

def _run_pr_only_checks():
    check("Python ≥ 3.10", lambda: (
        f"{sys.version_info.major}.{sys.version_info.minor}"
        if sys.version_info >= (3, 10)
        else (_ for _ in ()).throw(RuntimeError("need 3.10+"))
    ))

    check("SQLite ≥ 3.30 (FILTER WHERE)", lambda: (
        sqlite3.sqlite_version
        if tuple(int(x) for x in sqlite3.sqlite_version.split(".")) >= (3, 30)
        else (_ for _ in ()).throw(RuntimeError("too old"))
    ))

    def _check_pytest():
        import pytest
        return f"pytest {pytest.__version__}"
    check("pytest", _check_pytest)

    for subdir in [
        "Phase 2/adapters", "Phase 2/fixtures",
        "Phase 3/migrations",
        "Phase 4/fixtures",
    ]:
        path = ROOT / subdir
        if path.is_dir():
            results.append((f"Dir: {subdir}", PASS, ""))
        else:
            results.append((f"Dir: {subdir}", FAIL, "missing — run setup again"))

    # DB sanity: committed evidence DB exists and has the expected row counts
    db = ROOT / "task3_pipeline_lifecycle.db"
    if db.exists():
        try:
            conn = sqlite3.connect(str(db))
            total = conn.execute("SELECT COUNT(*) FROM article_references").fetchone()[0]
            accepts = conn.execute(
                "SELECT COUNT(*) FROM article_references WHERE triage_decision='ACCEPT'"
            ).fetchone()[0]
            chain = conn.execute("SELECT COUNT(*) FROM lifecycle_transitions").fetchone()[0]
            conn.close()
            if total >= 1193 and accepts >= 10:
                results.append(("DB row counts", PASS,
                                 f"{total} refs, {accepts} ACCEPT, {chain} transitions"))
            else:
                results.append(("DB row counts", WARN,
                                 f"expected ≥1193 refs / ≥10 ACCEPT; got {total}/{accepts}"))
        except Exception as exc:
            results.append(("DB row counts", FAIL, str(exc)[:80]))
    else:
        results.append(("task3_pipeline_lifecycle.db", FAIL, "committed evidence DB missing"))


# ---------------------------------------------------------------------------
# Tier 2 — full mode only
# ---------------------------------------------------------------------------

def _run_full_checks():
    def _check_pdfplumber():
        import pdfplumber
        return f"pdfplumber {pdfplumber.__version__}"
    check("pdfplumber", _check_pdfplumber)

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

    def _check_sentence_transformers():
        import sentence_transformers
        return f"sentence-transformers {sentence_transformers.__version__}"
    check("sentence-transformers", _check_sentence_transformers)

    def _check_ae_corpus_dedupe():
        if AF_ROOT is None:
            raise RuntimeError("Article_Finder sibling repository not found")
        sys.path.insert(0, str(AF_ROOT))
        from core.ae_corpus_dedupe import normalize_doi, normalize_title
        assert normalize_doi("https://doi.org/10.1000/xyz") == "10.1000/xyz"
        return "normalize_doi/normalize_title ok"
    check("Article_Finder core.ae_corpus_dedupe", _check_ae_corpus_dedupe)

    def _check_paper_fetcher():
        if AE_ROOT is None:
            raise RuntimeError("Article_Eater sibling repository not found")
        sys.path.insert(0, str(AE_ROOT))
        sys.path.insert(0, str(AE_ROOT / "src"))
        from services.paper_fetcher import (  # noqa
            SemanticScholarClient, CrossRefClient, PubMedClient, UnpaywallClient
        )
        return "S2/CrossRef/PubMed/Unpaywall clients ok"
    check("Article_Eater paper_fetcher clients", _check_paper_fetcher)

    def _check_voi_scoring():
        if AE_ROOT is None:
            raise RuntimeError("Article_Eater sibling repository not found")
        spec = importlib.util.spec_from_file_location(
            "voi_scoring",
            str(AE_ROOT / "src" / "cmr" / "voi_scoring.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sample = [{"gap_type": "DIRECTION", "confidence": 0.3,
                   "effect_size": 0.5, "maturity": "preliminary"}]
        result = mod.score_voi(sample)
        assert result[0]["voi_score"] == 0.4
        return f"score_voi ok (sample VOI={result[0]['voi_score']})"
    check("Article_Eater voi_scoring (direct load)", _check_voi_scoring)

    def _check_classifier():
        if AF_ROOT is None:
            raise RuntimeError("Article_Finder sibling repository not found")
        sys.path.insert(0, str(AF_ROOT))
        from triage.classifier import HierarchicalClassifier  # noqa
        return "HierarchicalClassifier ok"
    check("Article_Finder HierarchicalClassifier", _check_classifier)

    def _check_atlas_shared():
        import atlas_shared
        version = atlas_shared.__version__ if hasattr(atlas_shared, "__version__") else "ok"
        return f"atlas-shared {version}"
    check("atlas-shared", _check_atlas_shared)

    # API keys (WARN-only: absence blocks live runs but not grading)
    def _check_serpapi_key():
        key = os.environ.get("SERPAPI_KEY", "")
        if not key:
            raise RuntimeError("SERPAPI_KEY not set — export SERPAPI_KEY=<your-key>")
        return f"set ({len(key)} chars)"
    warn_check("SERPAPI_KEY env var", _check_serpapi_key)

    ncbi = os.environ.get("NCBI_API_KEY", "")
    results.append(("NCBI_API_KEY (optional)", WARN if not ncbi else PASS,
                     f"set ({len(ncbi)} chars)" if ncbi else "(not set — rate limit 3 req/s)"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Task 3 setup verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modes:\n"
            "  pr-only  Python, SQLite, pytest, dirs, and DB counts only.\n"
            "           Skips sibling repos, API keys, and live-capable packages.\n"
            "           Use in CI and for grader verification.\n"
            "  full     All of the above plus pdfplumber, sibling repos, packages, keys.\n"
            "           Use for local full-workspace pilot verification.\n"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["pr-only", "full"],
        default="full",
        help="Verification tier (default: full)",
    )
    args = parser.parse_args(argv)
    mode = args.mode

    _run_pr_only_checks()
    if mode == "full":
        _run_full_checks()

    print()
    print("=" * 70)
    print(f"  Track 2 Task 3 — Setup Verification  [{mode}]")
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
        return 1
    if warnings:
        print(f"  All checks pass. {len(warnings)} warning(s) — see above.")
    else:
        print("  All checks pass. Ready to build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
