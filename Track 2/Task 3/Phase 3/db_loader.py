"""Phase 3 — DB loader. Reads Phase 2 search_results.json and inserts into article_references.

CLI:
    python3 db_loader.py \
        --search-results "../Phase 2/search_results.json" \
        --db task3_pipeline_lifecycle.db \
        --shared-snapshot ../../../../Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db \
        [--dry-run] [--run-id RUN-...] [--corpus-csv pdf_identity_inventory_local.csv]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dedupe import (
    Candidate,
    CorpusSnapshot,
    DedupeOutcome,
    insert_or_dedupe_reference,
    load_corpus_snapshot,
    utc_now_iso,
)
from migrate import apply_migrations

_HERE = Path(__file__).resolve().parent
DEFAULT_DB_PATH = _HERE.parent / "task3_pipeline_lifecycle.db"
DEFAULT_SHARED_SNAPSHOT = (
    _HERE.parents[3] / "Knowledge_Atlas" / "data" / "ka_payloads" / "pipeline_lifecycle_full.db"
)
DEFAULT_CORPUS_CSV = _HERE / "pdf_identity_inventory_local.csv"
DEFAULT_SEARCH_RESULTS = _HERE.parent / "Phase 2" / "search_results.json"
PHASE2_SCHEMA_PATH = _HERE.parent / "Phase 2" / "schema" / "search_results.schema.json"


@dataclass
class LoadReport:
    run_id: str
    search_results_input: str
    db_path: str
    dry_run: bool
    started_at: str
    finished_at: str
    input_candidate_count: int
    inserted_count: int = 0
    merged_doi_count: int = 0
    merged_title_count: int = 0
    enriched_doi_count: int = 0
    marked_duplicate_count: int = 0
    transitions_logged_count: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# JSON → Candidate mapping
# ---------------------------------------------------------------------------

def _result_to_candidate(result: dict) -> Candidate:
    """Map one Phase 2 results[] entry to a dedupe.Candidate."""
    # merged_from_sources is a list; we join into the comma-form discovered_via
    sources = result.get("merged_from_sources") or [result.get("discovered_via", "")]
    sources = [s for s in sources if s]
    discovered_via = ", ".join(sorted(set(sources)))

    return Candidate(
        title_raw=result.get("title_raw") or "",
        discovered_via=discovered_via,
        doi=result.get("doi"),
        first_author_surname=result.get("first_author_surname"),
        publication_year=result.get("publication_year"),
        venue=result.get("venue"),
        snippet=result.get("snippet"),
        discovered_query=result.get("discovered_query"),
        voi_score=result.get("source_voi_score"),
        # raw_citation / discovered_from_paper_id stay None for search-runner candidates
    )


# ---------------------------------------------------------------------------
# Optional JSON-Schema validation
# ---------------------------------------------------------------------------

def _validate_input(data: dict, schema_path: Path) -> None:
    try:
        import jsonschema
    except ImportError:
        return  # Best-effort; jsonschema is optional at runtime
    if not schema_path.exists():
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def load_search_results(
    *,
    search_results_path: Path,
    db_path: Path,
    shared_snapshot_path: Path | None = None,
    corpus_csv: Path | None = None,
    run_id: str | None = None,
    dry_run: bool = False,
    validate_schema: bool = True,
) -> LoadReport:
    """Read search_results.json, dedupe-insert each candidate into the DB, optionally snapshot."""
    started_at = utc_now_iso()

    payload = json.loads(Path(search_results_path).read_text(encoding="utf-8"))
    if validate_schema:
        _validate_input(payload, PHASE2_SCHEMA_PATH)

    results = payload.get("results", [])
    input_run_id = (payload.get("metadata") or {}).get("run_id")
    effective_run_id = run_id or input_run_id or f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    corpus = load_corpus_snapshot(corpus_csv) if corpus_csv and Path(corpus_csv).exists() else CorpusSnapshot()

    # Choose target DB: real file in normal mode, in-memory copy for dry-run
    if dry_run:
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        # Apply migrations into the in-memory DB
        for sql_file in sorted((_HERE / "migrations").glob("*.sql")):
            conn.executescript(sql_file.read_text(encoding="utf-8"))
    else:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        apply_migrations(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

    report = LoadReport(
        run_id=effective_run_id,
        search_results_input=str(search_results_path),
        db_path=str(db_path),
        dry_run=dry_run,
        started_at=started_at,
        finished_at="",
        input_candidate_count=len(results),
    )

    try:
        with conn:
            for result in results:
                candidate = _result_to_candidate(result)
                if not candidate.title_raw and not candidate.doi:
                    report.errors.append(f"Skipping candidate with no title and no DOI: {result.get('candidate_id', '?')}")
                    continue
                try:
                    outcome = insert_or_dedupe_reference(
                        candidate, conn,
                        run_id=effective_run_id,
                        created_by="db_loader",
                        corpus_snapshot=corpus,
                    )
                except Exception as exc:
                    report.errors.append(f"Insert error for {result.get('candidate_id', '?')}: {exc}")
                    continue
                _bump_counter(report, outcome)
                report.transitions_logged_count += 1
    finally:
        if dry_run:
            conn.close()
        else:
            conn.close()

    # Materialize the shared snapshot (only in non-dry-run mode)
    if not dry_run and shared_snapshot_path is not None:
        try:
            _materialize_snapshot(db_path, shared_snapshot_path)
        except Exception as exc:
            report.errors.append(f"Shared-snapshot write failed (non-fatal): {exc}")

    report.finished_at = utc_now_iso()
    return report


def _bump_counter(report: LoadReport, outcome: DedupeOutcome) -> None:
    action = outcome.action
    if action == "inserted":
        report.inserted_count += 1
    elif action == "merged_doi":
        report.merged_doi_count += 1
    elif action == "merged_title":
        report.merged_title_count += 1
    elif action == "enriched_doi":
        report.enriched_doi_count += 1
    elif action == "corpus_duplicate":
        report.marked_duplicate_count += 1


def _materialize_snapshot(source_db: Path, target_path: Path) -> None:
    """Use VACUUM INTO to write a byte-identical copy of source_db at target_path.

    If target_path already exists, it's overwritten. Parent directory is created
    if missing. The shared path is gitignored — we control whether it exists.
    """
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    # VACUUM INTO refuses to overwrite, so delete first
    if target_path.exists():
        target_path.unlink()
    src = sqlite3.connect(str(source_db))
    try:
        src.execute("VACUUM INTO ?", (str(target_path),))
        src.commit()
    finally:
        src.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3 DB loader")
    parser.add_argument("--search-results", default=str(DEFAULT_SEARCH_RESULTS))
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--shared-snapshot", default=str(DEFAULT_SHARED_SNAPSHOT))
    parser.add_argument("--corpus-csv", default=str(DEFAULT_CORPUS_CSV))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default=str(_HERE / "db_load_report.json"))
    parser.add_argument("--no-validate-schema", action="store_true",
                        help="Skip JSON-Schema validation of the input file")
    parser.add_argument("--no-snapshot", action="store_true",
                        help="Don't write the shared snapshot (local DB only)")
    args = parser.parse_args(argv)

    report = load_search_results(
        search_results_path=Path(args.search_results),
        db_path=Path(args.db),
        shared_snapshot_path=None if args.no_snapshot else Path(args.shared_snapshot),
        corpus_csv=Path(args.corpus_csv) if args.corpus_csv else None,
        run_id=args.run_id,
        dry_run=args.dry_run,
        validate_schema=not args.no_validate_schema,
    )

    # Write report
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(
        f"[db_loader] run_id={report.run_id} "
        f"input={report.input_candidate_count} "
        f"inserted={report.inserted_count} "
        f"merged_doi={report.merged_doi_count} "
        f"merged_title={report.merged_title_count} "
        f"enriched_doi={report.enriched_doi_count} "
        f"duplicate={report.marked_duplicate_count} "
        f"errors={len(report.errors)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
