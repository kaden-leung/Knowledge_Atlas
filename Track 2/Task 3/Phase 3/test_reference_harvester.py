"""Reference-harvester tests for Phase 3 (Pass 4).

Most tests exercise the pure parsing helpers — no pdfplumber needed. Integration
tests that actually call the live harvester are run end-to-end in Pass 5.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from migrate import apply_migrations
from reference_harvester import (
    detect_parse_style,
    extract_doi,
    extract_first_author_surname,
    extract_year,
    find_references_section,
    harvest_directories,
    parse_reference_line,
    sanitise_pdf_id,
    split_into_reference_lines,
)

_HERE = Path(__file__).resolve().parent
MIGRATIONS_DIR = _HERE / "migrations"


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "harvest.db"
    apply_migrations(db_path, MIGRATIONS_DIR)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    yield db_path, conn
    conn.close()


# ---------------------------------------------------------------------------
# SC-H1 — DOI extraction
# ---------------------------------------------------------------------------

def test_extracts_doi_from_reference_line():
    line = "1. Smith, J. (2024). Some title. Journal of Things 10(2). https://doi.org/10.1234/abcd.5678"
    assert extract_doi(line) == "10.1234/abcd.5678"


def test_extracts_doi_strips_trailing_punctuation():
    line = "See 10.1073/pnas.1912264116."
    assert extract_doi(line) == "10.1073/pnas.1912264116"


# ---------------------------------------------------------------------------
# SC-H2 — Year extraction
# ---------------------------------------------------------------------------

def test_extracts_year_from_parens():
    assert extract_year("Smith, J. (2024). Title.") == 2024


def test_extracts_year_bare():
    assert extract_year("Smith J 2019 Nature 567:42") == 2019


def test_extracts_year_none_when_missing():
    assert extract_year("No year here at all") is None


# ---------------------------------------------------------------------------
# SC-H3 — First-author surname
# ---------------------------------------------------------------------------

def test_extracts_first_author_surname():
    assert extract_first_author_surname("Smith, J., Doe, A. (2024). Title.") == "Smith"
    # Numbered marker stripped
    assert extract_first_author_surname("1. Smith, J. (2024). Title.") == "Smith"
    # Bracketed marker stripped
    assert extract_first_author_surname("[12] Djebbara, Z. (2019). Title.") == "Djebbara"


# ---------------------------------------------------------------------------
# SC-H4/H5/H6 — Three parse styles
# ---------------------------------------------------------------------------

def test_parses_numbered_style():
    line = "1. Smith, J. & Doe, A. (2024). A paper. Journal."
    parsed = parse_reference_line(line, "PDF-X", "/tmp/x.pdf")
    assert parsed.parse_style == "numbered"
    assert parsed.publication_year == 2024
    assert parsed.first_author_surname == "Smith"
    assert parsed.parse_confidence > 0.5


def test_parses_bracketed_style():
    line = "[1] Smith, J. (2024) Title. Conf."
    parsed = parse_reference_line(line, "PDF-X", "/tmp/x.pdf")
    assert parsed.parse_style == "bracketed"
    assert parsed.publication_year == 2024


def test_parses_name_year_style():
    line = "Smith, J. & Doe, A. (2024). Title. Venue."
    parsed = parse_reference_line(line, "PDF-X", "/tmp/x.pdf")
    assert parsed.parse_style == "name_year"
    assert parsed.first_author_surname == "Smith"


# ---------------------------------------------------------------------------
# SC-H7 — Unparseable falls through
# ---------------------------------------------------------------------------

def test_unparseable_falls_through_with_raw_only():
    line = "Cf. footnote 12 in §3.2 for further discussion"
    parsed = parse_reference_line(line, "PDF-X", "/tmp/x.pdf")
    assert parsed.parse_style == "unparseable"
    assert parsed.raw_citation == line
    assert parsed.first_author_surname is None
    assert parsed.publication_year is None


# ---------------------------------------------------------------------------
# SC-H8 — find_references_section returns None when no header present
# ---------------------------------------------------------------------------

def test_handles_pdf_with_no_references_section():
    full_text = "Introduction\nMethods\nResults\nDiscussion\nConclusion"
    assert find_references_section(full_text) is None


def test_find_references_section_locates_header():
    full_text = "Intro\n...\nDiscussion\n...\nReferences\n1. Smith J 2020"
    refs = find_references_section(full_text)
    assert refs is not None
    assert refs.lower().startswith("references")


# ---------------------------------------------------------------------------
# SC-H9 — Missing directory exits 0 with warning
# ---------------------------------------------------------------------------

def test_handles_missing_pdf_directory(tmp_path, capsys):
    nonexistent = tmp_path / "definitely_not_here"
    report = harvest_directories([nonexistent], db_path=tmp_path / "x.db", run_id="RUN-MISSING")
    assert report.pdfs_scanned == 0
    assert any("not found" in e.lower() for e in report.errors)


# ---------------------------------------------------------------------------
# SC-H10 — Harvester uses the dedupe path (linter test via AST scan)
# ---------------------------------------------------------------------------

def test_harvester_uses_dedupe_path():
    """AST-scan reference_harvester.py: no string literal contains a raw INSERT INTO article_references."""
    src = (_HERE / "reference_harvester.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "insert into article_references" in node.value.lower():
                bad.append(node.value[:80])
    assert not bad, f"Raw INSERT into article_references found in harvester: {bad}"


# ---------------------------------------------------------------------------
# SC-H11 + SC-H12 — discovered_via and discovered_from_paper_id set correctly
# ---------------------------------------------------------------------------

def test_discovered_via_set_to_review_pdf_extract(db, monkeypatch, tmp_path):
    """Inject a fake harvest_pdf returning a parsed line; assert DB row has correct provenance."""
    import reference_harvester as rh
    from reference_harvester import RawReferenceLine

    db_path, conn = db

    fake_line = RawReferenceLine(
        source_pdf_id="PDF-TestPaper",
        source_pdf_path="/tmp/test.pdf",
        raw_citation="Smith, J. (2024). A test paper. J. Tests.",
        doi="10.1000/test.x",
        title_raw="A test paper",
        first_author_surname="Smith",
        publication_year=2024,
        venue=None,
        parse_style="name_year",
        parse_confidence=0.8,
    )

    fake_pdf_dir = tmp_path / "fake_pdfs"
    fake_pdf_dir.mkdir()
    (fake_pdf_dir / "test.pdf").write_bytes(b"%PDF-1.4 fake")

    def fake_harvest_pdf(pdf_path):
        return [fake_line], True

    monkeypatch.setattr(rh, "harvest_pdf", fake_harvest_pdf)

    report = rh.harvest_directories([fake_pdf_dir], db_path=db_path, run_id="RUN-PROV")
    assert report.inserted_into_db == 1

    # Reconnect since harvest closed its connection
    conn2 = sqlite3.connect(str(db_path))
    try:
        row = conn2.execute(
            "SELECT discovered_via, discovered_from_paper_id FROM article_references"
        ).fetchone()
    finally:
        conn2.close()

    assert row[0] == "review_pdf_extract"
    assert row[1] == "PDF-TestPaper"


# ---------------------------------------------------------------------------
# sanitise_pdf_id helper
# ---------------------------------------------------------------------------

def test_sanitise_pdf_id():
    assert sanitise_pdf_id("Sense_of_Place_and_Belonging.pdf") == "PDF-Sense_of_Place_and_Belonging"
    assert sanitise_pdf_id("The Architecture of Belonging.pdf") == "PDF-The_Architecture_of_Belonging"
    assert sanitise_pdf_id("file with spaces & punct!.pdf") == "PDF-file_with_spaces_punct"
