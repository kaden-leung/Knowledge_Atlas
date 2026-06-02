#!/usr/bin/env python3
"""Evidence-first verifier for the Track 2 workflow."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
# Task 2 query output lives one level up, in the sibling Task 2 directory.
# This sibling path resolves correctly from both the author working tree and a
# fresh Knowledge_Atlas checkout (where Task 2 and Task 3 sit side by side).
TASK2_QUERY = ROOT.parent / "Task 2" / "Phase 3" / "query_results.json"
SEARCH_RESULTS = ROOT / "Phase 2" / "search_results.json"
DB_PATH = ROOT / "task3_pipeline_lifecycle.db"
ACQUISITION_REPORT = ROOT / "Phase 5" / "acquisition_report.json"
HANDOFF_MANIFEST = ROOT / "Phase 7" / "handoff_outbox" / "handoff_manifest.json"
INBOX_REPORT = ROOT / "Phase 7" / "handoff_outbox" / "inbox_validation_report.json"
PROVEIT = ROOT / "PROVEIT_WORKS.md"
BENCHMARK = ROOT / "TRACK2_EVALUATION_REPORT.md"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"required evidence file missing: {path}")
    return json.loads(path.read_text())


def check_task2_queries() -> str:
    data = load_json(TASK2_QUERY)
    count = len(data.get("queries", []))
    if count != 10:
        raise RuntimeError(f"expected 10 Task 2 queries, got {count}")
    return f"Task 2 queries present ({count} queries)"


def check_search_results() -> str:
    data = load_json(SEARCH_RESULTS)
    meta = data.get("metadata", {})
    processed = meta.get("queries_processed")
    candidates = meta.get("candidates_after_dedupe")
    if processed != 10:
        raise RuntimeError(f"expected 10 processed queries, got {processed}")
    if not isinstance(candidates, int) or candidates < 80:
        raise RuntimeError(f"expected >=80 deduped candidates, got {candidates}")
    return f"search runner ok ({processed} queries, {candidates} candidates after dedupe)"


def check_db_population(cur: sqlite3.Cursor) -> str:
    count = cur.execute("SELECT COUNT(*) FROM article_references").fetchone()[0]
    if count < 1000:
        raise RuntimeError(f"expected >=1000 article_references rows, got {count}")
    return f"DB buffer ok ({count} article_references rows)"


def check_stage1(cur: sqlite3.Cursor) -> str:
    count = cur.execute(
        "SELECT COUNT(*) FROM lifecycle_transitions WHERE created_by='abstract_triage'"
    ).fetchone()[0]
    if count < 1000:
        raise RuntimeError(f"expected >=1000 abstract_triage transitions, got {count}")
    return f"Stage 1/2B transition logging ok ({count} abstract_triage transitions)"


def check_stage2a(cur: sqlite3.Cursor) -> str:
    count = cur.execute(
        "SELECT COUNT(*) FROM lifecycle_transitions WHERE created_by='abstract_collector'"
    ).fetchone()[0]
    if count < 200:
        raise RuntimeError(f"expected >=200 abstract_collector transitions, got {count}")
    return f"Stage 2A collection logging ok ({count} abstract_collector transitions)"


def check_accept_queue(cur: sqlite3.Cursor) -> str:
    accepts = cur.execute(
        "SELECT COUNT(*) FROM article_references WHERE triage_decision='ACCEPT'"
    ).fetchone()[0]
    queue = cur.execute("SELECT COUNT(*) FROM v_acquisition_queue").fetchone()[0]
    if accepts < 1:
        raise RuntimeError("expected at least one ACCEPT row")
    if queue < 1:
        raise RuntimeError("expected at least one row in v_acquisition_queue")
    return f"ACCEPT queue ok ({accepts} ACCEPT rows, {queue} queued for acquisition)"


def check_acquisition_evidence(cur: sqlite3.Cursor) -> str:
    report = load_json(ACQUISITION_REPORT)
    processed = report.get("rows_processed", 0)
    transitions = cur.execute(
        "SELECT COUNT(*) FROM lifecycle_transitions WHERE reason LIKE 'acquisition_%' OR reason LIKE 'policy_gate_blocked%'"
    ).fetchone()[0]
    if processed < 1:
        raise RuntimeError("expected Phase 5 dry-run evidence with processed rows")
    if transitions == 0:
        return f"Phase 5 dry-run evidence ok ({processed} rows processed; no live acquisition transitions recorded)"
    return f"Phase 5 live evidence ok ({processed} rows processed; {transitions} acquisition transitions)"


def check_trace_and_benchmark() -> str:
    if not PROVEIT.exists():
        raise RuntimeError("missing PROVEIT_WORKS.md")
    if not BENCHMARK.exists():
        raise RuntimeError("missing TRACK2_EVALUATION_REPORT.md")
    return "trace + benchmark docs present"


def check_handoff_artifacts() -> str:
    if not HANDOFF_MANIFEST.exists():
        raise RuntimeError("missing Phase 7 handoff_manifest.json")
    if not INBOX_REPORT.exists():
        raise RuntimeError("missing Phase 7 inbox_validation_report.json")

    manifest = load_json(HANDOFF_MANIFEST)
    report = load_json(INBOX_REPORT)
    written = manifest.get("written_count", 0)
    valid = report.get("valid_count", 0)
    invalid = report.get("invalid_count", 0)
    if written < 1:
        raise RuntimeError("expected at least one handoff artifact")
    if valid != written:
        raise RuntimeError(f"expected inbox valid_count {written}, got {valid}")
    if invalid != 0:
        raise RuntimeError(f"expected zero invalid handoff artifacts, got {invalid}")
    return f"handoff ok ({written} artifacts exported, {valid} validated)"


def main() -> int:
    checks = []
    checks.append(("Task 2 query mirror", check_task2_queries()))
    checks.append(("Search results", check_search_results()))

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        checks.append(("DB population", check_db_population(cur)))
        checks.append(("Stage 1/2B transitions", check_stage1(cur)))
        checks.append(("Stage 2A collection", check_stage2a(cur)))
        checks.append(("ACCEPT queue", check_accept_queue(cur)))
        checks.append(("Acquisition evidence", check_acquisition_evidence(cur)))

    checks.append(("Phase 7 handoff", check_handoff_artifacts()))
    checks.append(("Trace + benchmark docs", check_trace_and_benchmark()))

    print("Track 2 workflow verification")
    print("=" * 32)
    for name, detail in checks:
        print(f"PASS  {name}: {detail}")
    print("=" * 32)
    print(f"CHAIN: {len(checks)}/{len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
