"""Candidate PDF state machine.

Source authority:
    docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md §5

Six states (synthesis P28 / impl spec §10):
    metadata_only
        → abstract_only
        → candidate_pdf_unverified
        → pdf_verified
        → ocr_ready
        → extracted

Each candidate paper progresses forward through these states. The state is
recorded on the `article_finder_candidate` artefact's content; transitions
create related artefacts (abstract, pdf_artifact, ocr_artifact) and link
them via dependency_edges.

For Phase 2 MVP, only forward transitions are allowed. Backward transitions
(e.g., reverting from pdf_verified to candidate_pdf_unverified for
re-verification) are a Phase 4 or later concern.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from overseer.artefact_registry import Artefact, register
from overseer.dependency_edges import add_edge

STATES = (
    "metadata_only",
    "abstract_only",
    "candidate_pdf_unverified",
    "pdf_verified",
    "ocr_ready",
    "extracted",
)

ALLOWED_TRANSITIONS = {
    "metadata_only": ("abstract_only",),
    "abstract_only": ("candidate_pdf_unverified",),
    "candidate_pdf_unverified": ("pdf_verified",),
    "pdf_verified": ("ocr_ready",),
    "ocr_ready": ("extracted",),
    "extracted": (),
}

# Map each state to the artefact kind that records reaching that state.
STATE_TO_RELATED_KIND = {
    "abstract_only": "abstract",
    "candidate_pdf_unverified": "pdf_artifact",
    "pdf_verified": "pdf_artifact",
    "ocr_ready": "ocr_artifact",
    "extracted": "article_epistemic_record",
}


class InvalidTransitionError(ValueError):
    pass


@dataclass(frozen=True)
class TransitionResult:
    paper_id: str
    from_state: str
    to_state: str
    candidate_artefact_id: str
    related_artefact_id: str | None  # the new abstract/pdf/ocr/record artefact, if created


def ensure_candidate(conn: sqlite3.Connection, paper_id: str) -> Artefact:
    """Register an article_finder_candidate artefact for this paper_id.

    Idempotent: returns the existing active artefact if already registered.
    """
    return register(
        conn,
        kind="article_finder_candidate",
        entity_type="paper",
        entity_id=paper_id,
        field_path=None,
        schema_version="article_finder_candidate.v1",
    )


def transition(
    conn: sqlite3.Connection,
    *,
    paper_id: str,
    from_state: str,
    to_state: str,
) -> TransitionResult:
    """Advance a candidate paper from from_state to to_state.

    Side effects:
      * Ensures the article_finder_candidate artefact exists.
      * For state-mapped kinds, registers the related artefact (abstract /
        pdf_artifact / ocr_artifact / article_epistemic_record).
      * Adds a dependency_edges row of kind 'derived_from' linking the new
        artefact to the candidate.

    Raises:
      InvalidTransitionError if (from_state → to_state) is not in
        ALLOWED_TRANSITIONS or either state is unknown.
    """
    if from_state not in STATES:
        raise InvalidTransitionError(f"unknown from_state: {from_state!r}")
    if to_state not in STATES:
        raise InvalidTransitionError(f"unknown to_state: {to_state!r}")
    if to_state not in ALLOWED_TRANSITIONS[from_state]:
        raise InvalidTransitionError(
            f"transition {from_state} -> {to_state} not allowed; "
            f"allowed: {list(ALLOWED_TRANSITIONS[from_state])}"
        )

    candidate = ensure_candidate(conn, paper_id)
    related_id: str | None = None

    related_kind = STATE_TO_RELATED_KIND.get(to_state)
    if related_kind is not None:
        related = register(
            conn,
            kind=related_kind,
            entity_type="paper",
            entity_id=paper_id,
            field_path=to_state,  # state acts as the field_path for uniqueness
            schema_version=f"{related_kind}.v1",
        )
        related_id = related.artefact_id
        add_edge(
            conn,
            parent_artefact_id=candidate.artefact_id,
            child_artefact_id=related_id,
            edge_kind="derived_from",
        )

    return TransitionResult(
        paper_id=paper_id,
        from_state=from_state,
        to_state=to_state,
        candidate_artefact_id=candidate.artefact_id,
        related_artefact_id=related_id,
    )


def is_terminal(state: str) -> bool:
    return state == "extracted"


def successor_states(state: str) -> tuple[str, ...]:
    return ALLOWED_TRANSITIONS.get(state, ())
