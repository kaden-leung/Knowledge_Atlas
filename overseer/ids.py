"""ID generation for the dependency overseer.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §14 OIQ #1

Recommendation from §14: deterministic IDs for artefact_id (human-readable,
collision-free under uniqueness constraints), UUID4 for everything else
(build_run_id, queue_id, event_id, invocation_id).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """UTC timestamp in ISO 8601 with second precision and Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def artefact_id(
    kind: str,
    entity_id: str,
    field_path: str | None,
    schema_version: str,
) -> str:
    """Deterministic artefact_id: '{kind}:{entity_id}:{field_path or ""}:{schema_version}'.

    Empty field_path serializes as the empty segment.
    """
    fp = field_path if field_path is not None else ""
    return f"{kind}:{entity_id}:{fp}:{schema_version}"


def build_run_id(builder_name: str | None = None) -> str:
    """Random build_run_id with optional builder prefix."""
    u = uuid.uuid4().hex
    if builder_name:
        return f"br:{builder_name}:{u}"
    return f"br:{u}"


def queue_id() -> str:
    return f"q:{uuid.uuid4().hex}"


def event_id() -> str:
    return f"ev:{uuid.uuid4().hex}"


def completion_queue_id() -> str:
    return f"cq:{uuid.uuid4().hex}"


def check_id() -> str:
    return f"chk:{uuid.uuid4().hex}"


def support_set_id_for(members: list[tuple[str, str]]) -> str:
    """Deterministic support_set_id derived from sorted (artefact_id, hash) members."""
    sorted_pairs = sorted((str(a), str(h)) for a, h in members)
    h = hashlib.sha256(
        "|".join(f"{a}\x1f{h}" for a, h in sorted_pairs).encode("utf-8")
    ).hexdigest()[:32]
    return f"ss:{h}"


def vocab_value_id(kind: str, value: str) -> str:
    """Deterministic value_id matching scripts/dependency_overseer_seed.py."""
    h = hashlib.sha256(f"{kind}\x1f{value}".encode("utf-8")).hexdigest()[:16]
    return f"vocab:{kind}:{h}"
