"""Tests for portable COGS workspace discovery."""
from pathlib import Path

import pytest

from workspace_paths import find_repository, find_workspace_root


ROOT = Path(__file__).resolve().parent


def test_workspace_root_from_nested_phase():
    workspace = find_workspace_root(ROOT / "Phase 3")
    assert (workspace / "Knowledge_Atlas").is_dir()


def test_article_finder_sibling_is_discovered():
    article_finder = find_repository("Article_Finder", ROOT / "Phase 4")
    if article_finder is None:
        pytest.skip("Article_Finder sibling is not present in this checkout")
    assert (article_finder / "core").is_dir()


def test_missing_sibling_returns_none():
    assert find_repository("Not_A_Real_COGS_Repo", ROOT) is None
