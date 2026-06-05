"""Phase 3 — Reference harvester.

Walks PDF directories, extracts reference-list lines with pdfplumber,
parses each line into a Candidate, and inserts via the shared dedupe path.

See REFERENCE_HARVESTER_CONTRACT.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dedupe import (
    Candidate,
    CorpusSnapshot,
    insert_or_dedupe_reference,
    load_corpus_snapshot,
    utc_now_iso,
)
from migrate import apply_migrations

_HERE = Path(__file__).resolve().parent
DEFAULT_DB_PATH = _HERE.parent / "task3_pipeline_lifecycle.db"
_TASK3 = _HERE.parent
if str(_TASK3) not in sys.path:
    sys.path.insert(0, str(_TASK3))

from workspace_paths import find_workspace_root  # noqa: E402

_COGS160 = find_workspace_root(_HERE)
DEFAULT_PDF_DIRS = [
    _COGS160 / "Part 2 Pdfs",
    _COGS160 / "Part_One_10pdfs",
]
DEFAULT_OUTPUT = _HERE / "reference_harvest_results.json"
DEFAULT_CORPUS_CSV = _HERE / "pdf_identity_inventory_local.csv"
UNPARSEABLE_SAMPLE_CAP = 20

# Regex patterns
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
_YEAR_PARENS_RE = re.compile(r"\((\d{4})\)")
_YEAR_BARE_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_REF_HEADERS = (
    "references and notes",
    "references",
    "bibliography",
    "works cited",
    "literature cited",
)

_NUMBERED_RE = re.compile(r"^\s*(\d{1,3})\s*[.)]\s+")
_BRACKETED_RE = re.compile(r"^\s*\[(\d{1,3})\]\s*")
_NAME_YEAR_RE = re.compile(r"^[A-Z][a-z]+,\s+[A-Z]\.\s*(?:[A-Z]\.\s*)?(?:&|,)")

_PDF_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RawReferenceLine:
    source_pdf_id: str
    source_pdf_path: str
    raw_citation: str
    doi: str | None
    title_raw: str | None
    first_author_surname: str | None
    publication_year: int | None
    venue: str | None
    parse_style: str
    parse_confidence: float


@dataclass
class PerPdfReport:
    pdf_path: str
    pdf_id: str
    references_section_found: bool
    raw_lines: int
    parsed_lines: int
    unparseable_lines: int
    inserted: int = 0
    merged: int = 0
    duplicated: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class HarvestReport:
    run_id: str
    started_at: str
    finished_at: str
    pdf_dirs: list[str]
    pdfs_scanned: int = 0
    pdfs_with_references_section: int = 0
    raw_reference_lines: int = 0
    parsed_lines: dict = field(default_factory=lambda: {
        "numbered": 0, "bracketed": 0, "name_year": 0, "unparseable": 0,
    })
    inserted_into_db: int = 0
    merged_count: int = 0
    marked_duplicate_count: int = 0
    per_pdf: list[PerPdfReport] = field(default_factory=list)
    unparseable_lines_sample: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metadata": {
                "schema_version": "1.0.0",
                "run_id": self.run_id,
                "generated_at": self.finished_at,
                "started_at": self.started_at,
                "pdf_dirs": self.pdf_dirs,
                "pdfs_scanned": self.pdfs_scanned,
                "pdfs_with_references_section": self.pdfs_with_references_section,
                "raw_reference_lines": self.raw_reference_lines,
                "parsed_lines": self.parsed_lines,
                "inserted_into_db": self.inserted_into_db,
                "merged_count": self.merged_count,
                "marked_duplicate_count": self.marked_duplicate_count,
            },
            "per_pdf": [asdict(p) for p in self.per_pdf],
            "unparseable_lines_sample": self.unparseable_lines_sample,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Pure parsing helpers (testable without pdfplumber)
# ---------------------------------------------------------------------------

def sanitise_pdf_id(filename: str) -> str:
    """Convert a filename into a PDF-<safe> identifier."""
    stem = Path(filename).stem
    safe = _PDF_ID_SAFE_RE.sub("_", stem)
    safe = safe.strip("_")
    return f"PDF-{safe}"


def extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    if not m:
        return None
    raw = m.group(0)
    # Strip trailing punctuation that's commonly captured but not part of the DOI
    return raw.rstrip(").,;]")


def extract_year(text: str) -> int | None:
    m = _YEAR_PARENS_RE.search(text)
    if m:
        return int(m.group(1))
    m = _YEAR_BARE_RE.search(text)
    return int(m.group(1)) if m else None


def extract_first_author_surname(text: str) -> str | None:
    """Heuristic: first comma-separated chunk; last whitespace token is surname.

    Only fires when the chunk looks plausibly name-shaped: there must be a
    comma in the input (the canonical `Surname, X.` form) AND the surname
    token must start with an uppercase letter followed by lowercase letters.

    Anglocentric: Asian name order (`Wang Wei`) returns the given name.
    Documented in §10.3 of the Phase 2 contract; same limitation applies.
    """
    if not text:
        return None
    # Strip leading reference marker (e.g. "1.", "[12]")
    cleaned = re.sub(r"^\s*\[?\d{1,3}\]?\.?\)?\s*", "", text)
    # Require a comma — that's the strongest signal this looks like an author block
    if "," not in cleaned:
        return None
    first_block = cleaned.split(",")[0].strip()
    if not first_block:
        return None
    tokens = first_block.split()
    if not tokens:
        return None
    candidate = tokens[-1]
    # Surname must look like a proper name: starts with uppercase, alphabetic
    if not re.match(r"^[A-Z][a-zA-Z'\-]+$", candidate):
        return None
    return candidate


def detect_parse_style(line: str) -> str:
    if _NUMBERED_RE.match(line):
        return "numbered"
    if _BRACKETED_RE.match(line):
        return "bracketed"
    if _NAME_YEAR_RE.match(line):
        return "name_year"
    return "unparseable"


def parse_reference_line(line: str, source_pdf_id: str, source_pdf_path: str) -> RawReferenceLine:
    """Best-effort parse of one reference line into a RawReferenceLine."""
    style = detect_parse_style(line)
    doi = extract_doi(line)
    year = extract_year(line)
    surname = extract_first_author_surname(line)
    # Title heuristic: text between first year and next period or comma
    title = _extract_title_heuristic(line, year)

    fields_extracted = sum([
        1 if doi else 0,
        1 if year else 0,
        1 if surname else 0,
        1 if title else 0,
    ])
    confidence = 0.0 if style == "unparseable" else 0.25 + 0.1875 * fields_extracted

    return RawReferenceLine(
        source_pdf_id=source_pdf_id,
        source_pdf_path=source_pdf_path,
        raw_citation=line,
        doi=doi,
        title_raw=title,
        first_author_surname=surname,
        publication_year=year,
        venue=None,  # venue is too noisy to extract reliably
        parse_style=style,
        parse_confidence=min(1.0, confidence),
    )


def _extract_title_heuristic(line: str, year: int | None) -> str | None:
    """Try to find the title between the year token and the next venue-ish marker."""
    if year is None:
        return None
    year_str = str(year)
    idx = line.find(year_str)
    if idx == -1:
        return None
    after_year = line[idx + len(year_str):]
    # Strip leading punctuation
    after_year = re.sub(r"^[\s).,]+", "", after_year)
    # Title ends at first period (followed by space + capital) or first comma
    m = re.search(r"\.\s+[A-Z]|\.\s*$|,\s+[A-Z][a-z]+\s+(?:Journal|Conference|Proceedings)", after_year)
    if m:
        title = after_year[: m.start()].strip()
    else:
        # Fall back: take first 120 chars
        title = after_year[:120].strip()
    return title if title else None


# ---------------------------------------------------------------------------
# PDF I/O (the only impure part)
# ---------------------------------------------------------------------------

def find_references_section(full_text: str) -> str | None:
    """Locate the references section by scanning the end of the document backward.

    Returns the substring from the references header to the end, or None.
    """
    lower = full_text.lower()
    # Scan from the end backwards through the last ~30% of the document
    cut = int(len(lower) * 0.5)
    best_pos = -1
    for header in _REF_HEADERS:
        pos = lower.rfind(header, cut)
        if pos > best_pos:
            best_pos = pos
    if best_pos == -1:
        return None
    return full_text[best_pos:]


def split_into_reference_lines(references_text: str) -> list[str]:
    """Split a references-section blob into individual entry strings.

    Strategy: walk line by line. A new entry starts when the line matches
    numbered/bracketed/name_year markers. Continuation lines are appended
    to the current entry.
    """
    lines = references_text.splitlines()
    # Skip the header line itself
    if lines and any(h in lines[0].lower() for h in _REF_HEADERS):
        lines = lines[1:]

    entries: list[str] = []
    current: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue
        style = detect_parse_style(line)
        if style != "unparseable" and current:
            entries.append(" ".join(current).strip())
            current = [line]
        elif style != "unparseable":
            current = [line]
        else:
            if current:
                current.append(line)
            else:
                # Orphan line before any marker — treat as standalone unparseable
                entries.append(line)
    if current:
        entries.append(" ".join(current).strip())
    return [e for e in entries if e]


def harvest_pdf(pdf_path: Path) -> tuple[list[RawReferenceLine], bool]:
    """Extract all reference lines from one PDF. Returns (lines, references_section_found)."""
    import pdfplumber  # lazy import so tests of pure helpers don't need it
    pdf_id = sanitise_pdf_id(pdf_path.name)
    with pdfplumber.open(str(pdf_path)) as pdf:
        full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    refs_text = find_references_section(full_text)
    if refs_text is None:
        return [], False

    raw_lines = split_into_reference_lines(refs_text)
    parsed = [parse_reference_line(line, pdf_id, str(pdf_path)) for line in raw_lines]
    return parsed, True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def harvest_directories(
    pdf_dirs: list[Path],
    *,
    db_path: Path,
    run_id: str,
    corpus_csv: Path | None = None,
    dry_run: bool = False,
) -> HarvestReport:
    started_at = utc_now_iso()
    corpus = load_corpus_snapshot(corpus_csv) if corpus_csv and Path(corpus_csv).exists() else CorpusSnapshot()

    report = HarvestReport(
        run_id=run_id,
        started_at=started_at,
        finished_at="",
        pdf_dirs=[str(p) for p in pdf_dirs],
    )

    # Gather PDFs
    pdfs: list[Path] = []
    for d in pdf_dirs:
        if not d.exists():
            report.errors.append(f"PDF directory not found: {d}")
            print(f"[WARN] PDF directory not found: {d}", file=sys.stderr)
            continue
        pdfs.extend(sorted(d.glob("*.pdf")))

    if not pdfs:
        report.finished_at = utc_now_iso()
        return report

    # Connect DB
    if dry_run:
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        for sql_file in sorted((_HERE / "migrations").glob("*.sql")):
            conn.executescript(sql_file.read_text(encoding="utf-8"))
    else:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        apply_migrations(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

    try:
        for pdf_path in pdfs:
            report.pdfs_scanned += 1
            per_pdf = PerPdfReport(
                pdf_path=str(pdf_path),
                pdf_id=sanitise_pdf_id(pdf_path.name),
                references_section_found=False,
                raw_lines=0,
                parsed_lines=0,
                unparseable_lines=0,
            )
            try:
                lines, found = harvest_pdf(pdf_path)
            except Exception as exc:
                per_pdf.errors.append(f"pdfplumber error: {exc}")
                report.per_pdf.append(per_pdf)
                continue

            per_pdf.references_section_found = found
            if not found:
                report.per_pdf.append(per_pdf)
                continue
            report.pdfs_with_references_section += 1

            per_pdf.raw_lines = len(lines)
            report.raw_reference_lines += len(lines)

            with conn:
                for ref in lines:
                    report.parsed_lines[ref.parse_style] += 1
                    if ref.parse_style == "unparseable":
                        per_pdf.unparseable_lines += 1
                        if len(report.unparseable_lines_sample) < UNPARSEABLE_SAMPLE_CAP:
                            report.unparseable_lines_sample.append({
                                "pdf_id": ref.source_pdf_id,
                                "raw_citation": ref.raw_citation[:200],
                                "reason": "no_reference_marker",
                            })
                    else:
                        per_pdf.parsed_lines += 1

                    title = ref.title_raw or (ref.raw_citation[:80] if ref.raw_citation else "")
                    if not title:
                        per_pdf.errors.append("skipped: no title and no raw_citation")
                        continue

                    candidate = Candidate(
                        title_raw=title,
                        discovered_via="review_pdf_extract",
                        doi=ref.doi,
                        first_author_surname=ref.first_author_surname,
                        publication_year=ref.publication_year,
                        venue=ref.venue,
                        raw_citation=ref.raw_citation,
                        discovered_from_paper_id=ref.source_pdf_id,
                    )
                    try:
                        outcome = insert_or_dedupe_reference(
                            candidate, conn,
                            run_id=run_id,
                            created_by="reference_harvester",
                            corpus_snapshot=corpus,
                        )
                    except Exception as exc:
                        per_pdf.errors.append(f"insert error: {exc}")
                        continue

                    if outcome.action == "inserted":
                        per_pdf.inserted += 1
                        report.inserted_into_db += 1
                    elif outcome.action == "corpus_duplicate":
                        per_pdf.duplicated += 1
                        report.marked_duplicate_count += 1
                    else:
                        per_pdf.merged += 1
                        report.merged_count += 1

            report.per_pdf.append(per_pdf)
    finally:
        conn.close()

    report.finished_at = utc_now_iso()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3 PDF reference harvester")
    parser.add_argument(
        "--pdf-dir", action="append",
        help="PDF directory (repeatable). Default: Part 2 Pdfs + Part_One_10pdfs",
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--corpus-csv", default=str(DEFAULT_CORPUS_CSV))
    parser.add_argument("--run-id", required=False, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    pdf_dirs = [Path(d) for d in args.pdf_dir] if args.pdf_dir else DEFAULT_PDF_DIRS
    from datetime import datetime, timezone as _tz
    run_id = args.run_id or f"RUN-{datetime.now(_tz.utc).strftime('%Y%m%d-%H%M%S')}"

    report = harvest_directories(
        pdf_dirs,
        db_path=Path(args.db),
        run_id=run_id,
        corpus_csv=Path(args.corpus_csv) if args.corpus_csv else None,
        dry_run=args.dry_run,
    )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(
        f"[ref_harvester] run_id={report.run_id} "
        f"pdfs={report.pdfs_scanned} "
        f"with_refs={report.pdfs_with_references_section} "
        f"raw_lines={report.raw_reference_lines} "
        f"inserted={report.inserted_into_db} "
        f"merged={report.merged_count} "
        f"duplicated={report.marked_duplicate_count}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
