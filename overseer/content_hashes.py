"""Hash computation for the dependency-overseer.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §7
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P27)

Every active derived artefact carries:
  * raw_hash      — SHA-256 over canonical JSON of the whole content.
  * semantic_hash — SHA-256 over the normalized form (rule v1).

Every captured support set carries:
  * input_fingerprint — SHA-256 over a sorted (artefact_id, member_hash) list.

All hashes are returned as 'sha256:<hex>' for consistency with existing repo
conventions (see content_hashes table schema; build_run_id may also be hashed
in the same style by callers).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from overseer.normalization import (
    RULE_VERSION,
    canonical_raw_bytes,
    normalize_for_semantic_hash,
)


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compute_raw_hash(content: Any) -> str:
    """Return 'sha256:<hex>' over canonical JSON of content (no normalization)."""
    return _sha256_prefixed(canonical_raw_bytes(content))


def compute_semantic_hash(
    content: Any,
    component_type: str,
    rule_version: str = RULE_VERSION,
    *,
    hints_override: dict | None = None,
) -> str:
    """Return 'sha256:<hex>' over the normalized form (rule v1).

    Only changes to this hash propagate cascade (synthesis P27).
    """
    return _sha256_prefixed(
        normalize_for_semantic_hash(
            content,
            component_type,
            rule_version=rule_version,
            hints_override=hints_override,
        )
    )


def compute_input_fingerprint(support_set: Iterable[tuple[str, str]]) -> str:
    """Return 'sha256:<hex>' over a sorted list of (artefact_id, member_hash).

    support_set is an iterable of pairs (member_artefact_id, member_hash_at_capture).
    The pairs are sorted before hashing so two captures of the same support set
    produce the same fingerprint regardless of insertion order.
    """
    sorted_pairs = sorted(
        (str(aid), str(h)) for aid, h in support_set
    )
    canonical = json.dumps(
        sorted_pairs, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_prefixed(canonical)
