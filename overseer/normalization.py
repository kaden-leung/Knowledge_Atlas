"""Deterministic normalization for semantic hashing (rule v1).

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §6
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P27)

The contract:
  * raw_hash = SHA-256 over canonical JSON of the input content (sorted keys,
    compact separators, UTF-8).
  * semantic_hash = SHA-256 over canonical JSON of the *normalized* content,
    where normalization is governed by per-component-type hints loaded from
    contracts/schemas/dependency_overseer/component_types.json.

Only semantic_hash changes propagate cascade (synthesis P27). Raw-only changes
(whitespace, key ordering, documented case-insensitive reformatting, documented
order-insensitive list reordering, cosmetic-only timestamp drops) appear in
content_hashes history but do NOT enqueue rebuilds.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_TYPES_PATH = (
    REPO_ROOT
    / "contracts"
    / "schemas"
    / "dependency_overseer"
    / "component_types.json"
)

RULE_VERSION = "v1"

# Recognised hint flags. Any other key in a hint dict is ignored by rule v1.
HINT_FLAGS = {
    "whitespace_collapsible",
    "case_insensitive",
    "order_insensitive",
    "cosmetic_only",
}

_WHITESPACE_RE = re.compile(r"\s+")


class UnknownComponentTypeError(ValueError):
    """Raised when normalization is requested for a component type not in
    component_types.json. Phase 1 is strict: unknown component types must
    be registered in the contract file before they can be normalized."""


@lru_cache(maxsize=1)
def _load_component_types() -> dict[str, Any]:
    return json.loads(COMPONENT_TYPES_PATH.read_text(encoding="utf-8"))


def _hints_for(component_type: str, hints_override: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if hints_override is not None:
        return hints_override
    spec = _load_component_types()
    component_types = spec.get("component_types", {})
    if component_type not in component_types:
        raise UnknownComponentTypeError(
            f"component_type '{component_type}' is not registered in {COMPONENT_TYPES_PATH}; "
            f"register it before normalizing."
        )
    return component_types[component_type].get("normalization_hints", {})


def _path_hint(path: str, hints: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return the hint dict for a JSON path, or empty dict if none."""
    if path in hints:
        return hints[path]
    # Match list-element paths: e.g., a current path of 'rows[0].canonical_claim_text'
    # should match a hint key of 'rows[].canonical_claim_text'.
    list_normalized = re.sub(r"\[\d+\]", "[]", path)
    if list_normalized != path and list_normalized in hints:
        return hints[list_normalized]
    return {}


def _normalize_value(value: Any, path: str, hints: dict[str, dict[str, Any]]) -> Any:
    hint = _path_hint(path, hints)

    if hint.get("cosmetic_only"):
        # Sentinel value indicating the caller should drop this key entirely.
        return _DROP

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k in sorted(value.keys()):
            child_path = f"{path}.{k}" if path else k
            v = _normalize_value(value[k], child_path, hints)
            if v is _DROP:
                continue
            result[k] = v
        return result

    if isinstance(value, list):
        items = []
        for i, item in enumerate(value):
            child_path = f"{path}[{i}]"
            v = _normalize_value(item, child_path, hints)
            if v is _DROP:
                continue
            items.append(v)
        if hint.get("order_insensitive"):
            # Sort by canonical JSON of the item for a deterministic order.
            items.sort(key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        return items

    if isinstance(value, str):
        s = value
        if hint.get("whitespace_collapsible"):
            s = _WHITESPACE_RE.sub(" ", s.strip())
        if hint.get("case_insensitive"):
            s = s.lower()
        return s

    # int / float / bool / None pass through unchanged.
    return value


class _DropSentinel:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return "<DROP>"


_DROP = _DropSentinel()


def normalize_for_semantic_hash(
    content: Any,
    component_type: str,
    rule_version: str = RULE_VERSION,
    *,
    hints_override: dict[str, dict[str, Any]] | None = None,
) -> bytes:
    """Return the canonical normalized byte string for the given content.

    SHA-256 over the return value is the semantic_hash (per synthesis P27).

    The default behaviour loads per-field hints from component_types.json keyed
    by component_type. Tests may inject custom hints via hints_override.

    Raises:
        UnknownComponentTypeError if component_type is not in component_types.json
            and hints_override is not provided.
        ValueError if rule_version != 'v1' (this module implements rule v1 only).
    """
    if rule_version != RULE_VERSION:
        raise ValueError(
            f"normalization rule '{rule_version}' is not implemented by this module "
            f"(only '{RULE_VERSION}' is supported in Phase 1)."
        )
    hints = _hints_for(component_type, hints_override)
    normalized = _normalize_value(content, path="", hints=hints)
    return json.dumps(
        normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def canonical_raw_bytes(content: Any) -> bytes:
    """Return canonical JSON bytes of content with no normalization.

    SHA-256 over the return value is the raw_hash.
    """
    return json.dumps(
        content, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
