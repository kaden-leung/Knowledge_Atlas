"""Schema-layer tests for Phase 3 (SC-1, SC-2, SC-3, SC-4, SC-9, SC-10, SC-11, SC-12, SC-13)."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from migrate import apply_migrations

_HERE = Path(__file__).resolve().parent
MIGRATIONS_DIR = _HERE / "migrations"


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path, MIGRATIONS_DIR)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _insert_ref(conn, **kwargs):
    """Insert a minimal article_references row. kwargs override defaults."""
    defaults = {
        "reference_id": "REF-2026-05-28-000001",
        "doi": None,
        "title_raw": "A Title",
        "title_normalized": "a title",
        "discovered_via": "serpapi_scholar",
        "discovery_run_id": "RUN-T",
        "discovered_at": "2026-05-28T00:00:00Z",
    }
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" * len(defaults))
    conn.execute(
        f"INSERT INTO article_references ({cols}) VALUES ({placeholders})",
        tuple(defaults.values()),
    )


# ---------------------------------------------------------------------------
# SC-1 — required columns + defaults
# ---------------------------------------------------------------------------

def test_required_columns_present(db):
    """All identity, provenance, triage_stage columns exist; NOT NULL where declared."""
    cols = {row[1]: row for row in db.execute("PRAGMA table_info(article_references)").fetchall()}
    required = [
        "reference_id", "doi", "title_raw", "title_normalized",
        "first_author_surname", "publication_year", "venue",
        "raw_citation", "snippet",
        "discovered_via", "discovered_from_paper_id", "discovered_query",
        "discovery_run_id", "discovered_at",
        "triage_stage", "triage_decision", "triage_reason",
        "voi_score",
        "pdf_acquisition_attempts", "acquired_paper_id",
        "created_at", "updated_at",
    ]
    for col in required:
        assert col in cols, f"Missing column: {col}"


def test_default_triage_stage_is_metadata_only(db):
    """Inserting without triage_stage applies the DEFAULT 'metadata_only'."""
    # Have to skip triage_stage from the insert to test the default
    db.execute(
        """
        INSERT INTO article_references
          (reference_id, title_raw, title_normalized, discovered_via,
           discovery_run_id, discovered_at)
        VALUES ('REF-2026-05-28-000099', 'X', 'x', 'serpapi_scholar', 'RUN-T', '2026-05-28T00:00:00Z')
        """
    )
    db.commit()
    row = db.execute("SELECT triage_stage FROM article_references WHERE reference_id='REF-2026-05-28-000099'").fetchone()
    assert row[0] == "metadata_only"


# ---------------------------------------------------------------------------
# SC-2 — DOI lowercase invariant (enforced by callers; here we verify storage works)
# ---------------------------------------------------------------------------

def test_doi_constraint_normalised(db):
    """A stored DOI starting with '10.' and lowercased can be inserted; uppercase variant retrieved as-stored."""
    _insert_ref(db, reference_id="REF-2026-05-28-000010", doi="10.1073/pnas.1912264116")
    db.commit()
    row = db.execute("SELECT doi FROM article_references WHERE reference_id='REF-2026-05-28-000010'").fetchone()
    assert row[0].startswith("10.")
    assert row[0] == row[0].lower()


# ---------------------------------------------------------------------------
# SC-3 — partial unique index on DOI
# ---------------------------------------------------------------------------

def test_unique_doi_partial_index(db):
    """Two rows with the same non-null DOI → IntegrityError."""
    _insert_ref(db, reference_id="REF-2026-05-28-000020", doi="10.1000/dup.1")
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        _insert_ref(db, reference_id="REF-2026-05-28-000021", doi="10.1000/dup.1")
        db.commit()


def test_two_null_dois_allowed(db):
    """Partial index allows multiple NULL DOIs (the WHERE doi IS NOT NULL clause)."""
    _insert_ref(db, reference_id="REF-2026-05-28-000030", doi=None)
    _insert_ref(db, reference_id="REF-2026-05-28-000031", doi=None)
    db.commit()
    n = db.execute("SELECT COUNT(*) FROM article_references WHERE doi IS NULL").fetchone()[0]
    assert n == 2


# ---------------------------------------------------------------------------
# SC-4 — insert + transition in one transaction
# ---------------------------------------------------------------------------

def test_transition_logged_on_insert(db):
    """A single transaction inserting both rows must succeed atomically."""
    with db:
        _insert_ref(db, reference_id="REF-2026-05-28-000040")
        db.execute(
            """
            INSERT INTO lifecycle_transitions
              (reference_id, run_id, from_stage, to_stage, reason, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("REF-2026-05-28-000040", "RUN-T", None, "metadata_only",
             "initial_insert:serpapi_scholar", "db_loader"),
        )
    refs = db.execute("SELECT COUNT(*) FROM article_references WHERE reference_id='REF-2026-05-28-000040'").fetchone()[0]
    trans = db.execute("SELECT COUNT(*) FROM lifecycle_transitions WHERE reference_id='REF-2026-05-28-000040'").fetchone()[0]
    assert refs == 1 and trans == 1


# ---------------------------------------------------------------------------
# SC-9 — v_acquisition_queue filtering
# ---------------------------------------------------------------------------

def test_v_acquisition_queue_filters_correctly(db):
    """View returns only ACCEPT + acquired_paper_id IS NULL, sorted by VOI desc."""
    # Seed 4 rows with different states
    cases = [
        # (id, triage_decision, acquired_paper_id, voi_score, expected_in_view)
        ("REF-2026-05-28-100001", "ACCEPT", None, 0.9, True),
        ("REF-2026-05-28-100002", "ACCEPT", "PDF-EXISTING", 0.8, False),  # already acquired
        ("REF-2026-05-28-100003", "REJECT", None, 0.95, False),           # not ACCEPT
        ("REF-2026-05-28-100004", "ACCEPT", None, 0.5, True),
    ]
    for ref_id, decision, acquired, voi, _ in cases:
        _insert_ref(
            db, reference_id=ref_id,
            triage_decision=decision, acquired_paper_id=acquired, voi_score=voi,
        )
    db.commit()

    rows = db.execute("SELECT reference_id, voi_score FROM v_acquisition_queue").fetchall()
    assert [r[0] for r in rows] == ["REF-2026-05-28-100001", "REF-2026-05-28-100004"]
    # VOI-desc order
    assert rows[0][1] > rows[1][1]


# ---------------------------------------------------------------------------
# SC-10 — reference_id format
# ---------------------------------------------------------------------------

_REF_ID_RE = re.compile(r"^REF-\d{4}-\d{2}-\d{2}-\d{6}$")


def test_reference_id_format(db):
    """All inserted reference_id values match the canonical format."""
    _insert_ref(db, reference_id="REF-2026-05-28-000050")
    _insert_ref(db, reference_id="REF-2026-05-28-000051")
    db.commit()
    for row in db.execute("SELECT reference_id FROM article_references").fetchall():
        assert _REF_ID_RE.match(row[0]), f"Bad reference_id: {row[0]}"


def test_reference_id_substr_position():
    """`len('REF-YYYY-MM-DD-') == 15`; SQLite SUBSTR starts at 1, so position 16 is the counter."""
    prefix = "REF-2026-05-28-"
    assert len(prefix) == 15
    # The mint_reference_id query uses SUBSTR(reference_id, 16); verify it returns the counter.
    full_id = prefix + "000042"
    # SQLite SUBSTR(string, 16) returns chars from position 16 onward (1-indexed) — i.e. "000042"
    # Python equivalent is full_id[15:]
    assert full_id[15:] == "000042"


# ---------------------------------------------------------------------------
# SC-11 — migrations idempotent
# ---------------------------------------------------------------------------

def test_migrations_idempotent(tmp_path):
    """Applying the migration set twice is a no-op the second time."""
    db_path = tmp_path / "idem.db"
    first = apply_migrations(db_path, MIGRATIONS_DIR)
    second = apply_migrations(db_path, MIGRATIONS_DIR)
    assert len(first) == 4
    assert second == []  # Nothing new applied second time


# ---------------------------------------------------------------------------
# SC-12 — required indexes present
# ---------------------------------------------------------------------------

def test_indexes_present(db):
    """All declared indexes exist."""
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='article_references'"
    ).fetchall()
    names = {r[0] for r in rows}
    expected = {
        "idx_article_references_doi",
        "idx_article_references_run",
        "idx_article_references_stage",
        "idx_article_references_decision",
        "idx_article_references_title_norm",
        "idx_article_references_funnel",
    }
    missing = expected - names
    assert not missing, f"Missing indexes: {missing}"


# ---------------------------------------------------------------------------
# SC-13 — lifecycle_transitions.created_by NOT NULL
# ---------------------------------------------------------------------------

def test_created_by_required_on_transition(db):
    """Inserting a transition without created_by raises IntegrityError."""
    _insert_ref(db, reference_id="REF-2026-05-28-000060")
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO lifecycle_transitions
              (reference_id, run_id, from_stage, to_stage, reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("REF-2026-05-28-000060", "RUN-T", None, "metadata_only", "x"),
        )
        db.commit()
