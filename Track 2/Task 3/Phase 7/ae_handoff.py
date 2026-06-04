#!/usr/bin/env python3
"""Create deterministic handoff artifacts from ACCEPT rows."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT.parent / "task3_pipeline_lifecycle.db"
DEFAULT_OUTDIR = ROOT / "handoff_outbox"

SQL = """
SELECT
    reference_id,
    doi,
    title_raw,
    abstract_text,
    abstract_source,
    venue,
    publication_year,
    discovered_via,
    discovery_run_id,
    triage_reason,
    voi_score
FROM article_references
WHERE triage_decision = 'ACCEPT'
ORDER BY voi_score DESC NULLS LAST, created_at ASC
"""


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    doi = value.strip().lower()
    prefixes = ("https://doi.org/", "http://doi.org/", "doi:")
    for prefix in prefixes:
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to task3_pipeline_lifecycle.db")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR, help="Directory for handoff artifacts")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of ACCEPT rows to export")
    return parser.parse_args()


def build_artifact(row: sqlite3.Row) -> tuple[dict | None, str | None]:
    abstract = (row["abstract_text"] or "").strip()
    if not abstract:
        return None, "missing_abstract"

    title = row["title_raw"].strip()
    if not title:
        return None, "missing_title"

    doi = normalize_doi(row["doi"])
    discovered_via = [part.strip() for part in (row["discovered_via"] or "").split(",") if part.strip()]

    artifact = {
        "handoff_version": "1.0",
        "reference_id": row["reference_id"],
        "doi": doi,
        "title": title,
        "abstract": abstract,
        "abstract_source": row["abstract_source"],
        "venue": row["venue"],
        "publication_year": row["publication_year"],
        "triage_decision": "ACCEPT",
        "triage_reason": row["triage_reason"],
        "voi_score": row["voi_score"],
        "discovered_via": discovered_via,
        "discovery_run_id": row["discovery_run_id"],
    }
    return artifact, None


def main() -> int:
    args = parse_args()
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(SQL).fetchall()

    if args.limit is not None:
        rows = rows[: args.limit]

    artifact_files: list[str] = []
    skipped: list[dict[str, str]] = []
    normalized_dois = 0

    for row in rows:
        artifact, skip_reason = build_artifact(row)
        if artifact is None:
            skipped.append({"reference_id": row["reference_id"], "reason": skip_reason or "invalid"})
            continue

        if artifact["doi"] is not None:
            normalized_dois += 1

        filename = f"{artifact['reference_id']}.json"
        path = outdir / filename
        path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
        artifact_files.append(filename)

    manifest = {
        "handoff_version": "1.0",
        "db_path": args.db.name,  # filename only — keep absolute/home paths out of committed evidence
        "selected_accept_rows": len(rows),
        "written_count": len(artifact_files),
        "normalized_doi_count": normalized_dois,
        "skipped": skipped,
        "artifact_files": artifact_files,
    }
    (outdir / "handoff_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"selected={len(rows)} written={len(artifact_files)} skipped={len(skipped)}")
    for item in skipped:
        print(f"skip {item['reference_id']}: {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
