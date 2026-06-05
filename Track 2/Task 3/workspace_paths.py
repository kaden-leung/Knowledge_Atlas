"""Portable discovery of the COGS 160 workspace and sibling repositories."""
from __future__ import annotations

from pathlib import Path


class WorkspaceNotFoundError(RuntimeError):
    """Raised when the checkout is not inside a recognizable COGS workspace."""


def _search_candidates(start: Path) -> list[Path]:
    resolved = start.resolve()
    if resolved.is_file():
        resolved = resolved.parent
    return [resolved, *resolved.parents]


def find_workspace_root(start: Path | str | None = None) -> Path:
    """Return the directory containing the Knowledge_Atlas checkout.

    The resolver works from the Task 3 root, any nested phase directory, or a
    sibling repository. A standalone Knowledge_Atlas clone is also recognized
    by its repository directory name.
    """
    origin = Path(start) if start is not None else Path(__file__)
    for candidate in _search_candidates(origin):
        if (candidate / "Knowledge_Atlas").is_dir():
            return candidate
        if candidate.name == "Knowledge_Atlas":
            return candidate.parent
    raise WorkspaceNotFoundError(
        f"could not locate a workspace containing Knowledge_Atlas from {origin}"
    )


def find_repository(name: str, start: Path | str | None = None) -> Path | None:
    """Return a sibling repository path when present, otherwise ``None``."""
    try:
        path = find_workspace_root(start) / name
    except WorkspaceNotFoundError:
        return None
    return path if path.is_dir() else None


def require_repository(name: str, start: Path | str | None = None) -> Path:
    """Return a sibling repository or raise a setup-oriented error."""
    path = find_repository(name, start)
    if path is None:
        raise WorkspaceNotFoundError(
            f"{name} was not found beside Knowledge_Atlas in the COGS workspace"
        )
    return path
