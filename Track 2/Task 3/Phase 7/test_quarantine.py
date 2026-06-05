"""Tests for Phase 7 quarantine / restore utilities."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_TASK3 = _HERE.parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_TASK3 / "Phase 3"))

from quarantine import QuarantineError, quarantine, restore_from_quarantine  # noqa: E402
from migrate import apply_migrations  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "qtest.db"
    apply_migrations(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        INSERT INTO article_references (
            reference_id, title_raw, title_normalized, discovered_via,
            discovery_run_id, discovered_at, triage_stage, triage_decision
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("REF-TEST-000001", "Test Paper", "test paper",
         "serpapi_scholar", "RUN-TEST", "2026-01-01T00:00:00Z",
         "triage_complete", "ACCEPT"),
    )
    conn.commit()
    conn.close()
    return db


def _make_artifact(outbox: Path, ref_id: str) -> Path:
    outbox.mkdir(parents=True, exist_ok=True)
    p = outbox / f"{ref_id}.json"
    p.write_text(json.dumps({"reference_id": ref_id}), encoding="utf-8")
    return p


def _artifact_sha256_for_test(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decision(db: Path, ref_id: str) -> str:
    conn = sqlite3.connect(str(db))
    val = conn.execute(
        "SELECT triage_decision FROM article_references WHERE reference_id=?",
        (ref_id,),
    ).fetchone()[0]
    conn.close()
    return val


def _transition_count(db: Path, ref_id: str) -> int:
    conn = sqlite3.connect(str(db))
    n = conn.execute(
        "SELECT COUNT(*) FROM lifecycle_transitions WHERE reference_id=?",
        (ref_id,),
    ).fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------------------
# quarantine()
# ---------------------------------------------------------------------------

def test_quarantine_sets_decision(tmp_path):
    db = _make_db(tmp_path)
    quarantine("REF-TEST-000001", "false positive confirmed",
               db_path=db, outbox_dir=tmp_path / "out")
    assert _decision(db, "REF-TEST-000001") == "QUARANTINED"


def test_quarantine_logs_transition(tmp_path):
    db = _make_db(tmp_path)
    quarantine("REF-TEST-000001", "false positive",
               db_path=db, outbox_dir=tmp_path / "out")
    assert _transition_count(db, "REF-TEST-000001") == 1


def test_quarantine_moves_artifact(tmp_path):
    db = _make_db(tmp_path)
    outbox = tmp_path / "out"
    _make_artifact(outbox, "REF-TEST-000001")
    quarantine("REF-TEST-000001", "test", db_path=db, outbox_dir=outbox)
    assert not (outbox / "REF-TEST-000001.json").exists()
    assert (outbox / "quarantined" / "REF-TEST-000001.json").exists()


def test_quarantine_missing_ref_raises(tmp_path):
    db = _make_db(tmp_path)
    with pytest.raises(QuarantineError, match="not found"):
        quarantine("REF-NONEXISTENT", "reason", db_path=db, outbox_dir=tmp_path)


def test_quarantine_empty_reason_raises(tmp_path):
    db = _make_db(tmp_path)
    with pytest.raises(QuarantineError):
        quarantine("REF-TEST-000001", "", db_path=db, outbox_dir=tmp_path)


def test_quarantine_already_quarantined_raises(tmp_path):
    db = _make_db(tmp_path)
    quarantine("REF-TEST-000001", "first", db_path=db, outbox_dir=tmp_path / "out")
    with pytest.raises(QuarantineError, match="must be ACCEPT"):
        quarantine("REF-TEST-000001", "second", db_path=db, outbox_dir=tmp_path / "out")


def test_quarantine_rejects_non_accept_state(tmp_path):
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE article_references SET triage_decision='EDGE_CASE' "
        "WHERE reference_id='REF-TEST-000001'"
    )
    conn.commit()
    conn.close()
    with pytest.raises(QuarantineError, match="must be ACCEPT"):
        quarantine("REF-TEST-000001", "not eligible", db_path=db, outbox_dir=tmp_path)


def test_quarantine_records_artifact_hash(tmp_path):
    db = _make_db(tmp_path)
    outbox = tmp_path / "out"
    artifact = _make_artifact(outbox, "REF-TEST-000001")
    expected = _artifact_sha256_for_test(artifact)
    quarantine("REF-TEST-000001", "false positive", db_path=db, outbox_dir=outbox)
    conn = sqlite3.connect(str(db))
    reason = conn.execute(
        "SELECT reason FROM lifecycle_transitions WHERE reference_id='REF-TEST-000001'"
    ).fetchone()[0]
    conn.close()
    assert json.loads(reason)["artifact_sha256"] == expected


# ---------------------------------------------------------------------------
# restore_from_quarantine()
# ---------------------------------------------------------------------------

def test_restore_sets_accept(tmp_path):
    db = _make_db(tmp_path)
    outbox = tmp_path / "out"
    quarantine("REF-TEST-000001", "reason", db_path=db, outbox_dir=outbox)
    restore_from_quarantine("REF-TEST-000001", "verified OK after second look",
                            db_path=db, outbox_dir=outbox)
    assert _decision(db, "REF-TEST-000001") == "ACCEPT"


def test_restore_logs_transition(tmp_path):
    db = _make_db(tmp_path)
    outbox = tmp_path / "out"
    quarantine("REF-TEST-000001", "reason", db_path=db, outbox_dir=outbox)
    restore_from_quarantine("REF-TEST-000001", "OK", db_path=db, outbox_dir=outbox)
    assert _transition_count(db, "REF-TEST-000001") == 2


def test_restore_moves_artifact_back(tmp_path):
    db = _make_db(tmp_path)
    outbox = tmp_path / "out"
    _make_artifact(outbox, "REF-TEST-000001")
    quarantine("REF-TEST-000001", "test", db_path=db, outbox_dir=outbox)
    restore_from_quarantine("REF-TEST-000001", "OK", db_path=db, outbox_dir=outbox)
    assert (outbox / "REF-TEST-000001.json").exists()
    assert not (outbox / "quarantined" / "REF-TEST-000001.json").exists()


def test_restore_not_quarantined_raises(tmp_path):
    db = _make_db(tmp_path)
    with pytest.raises(QuarantineError, match="not QUARANTINED"):
        restore_from_quarantine("REF-TEST-000001", "note",
                                db_path=db, outbox_dir=tmp_path)


def test_restore_empty_note_raises(tmp_path):
    db = _make_db(tmp_path)
    outbox = tmp_path / "out"
    quarantine("REF-TEST-000001", "reason", db_path=db, outbox_dir=outbox)
    with pytest.raises(QuarantineError):
        restore_from_quarantine("REF-TEST-000001", "  ", db_path=db, outbox_dir=outbox)
