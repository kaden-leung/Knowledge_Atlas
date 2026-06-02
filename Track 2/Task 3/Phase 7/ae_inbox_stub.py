#!/usr/bin/env python3
"""Validate handoff artifacts as a downstream inbox stub."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTDIR = ROOT / "handoff_outbox"

REQUIRED_FIELDS = (
    "handoff_version",
    "reference_id",
    "title",
    "abstract",
    "triage_decision",
    "voi_score",
    "discovered_via",
    "discovery_run_id",
)


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
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR, help="Directory containing handoff artifacts")
    return parser.parse_args()


def validate_artifact(path: Path) -> list[str]:
    data = json.loads(path.read_text())
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing_field:{field}")

    abstract = str(data.get("abstract", "")).strip()
    if not abstract:
        errors.append("empty_abstract")

    if data.get("triage_decision") != "ACCEPT":
        errors.append("invalid_decision")

    doi = data.get("doi")
    if doi is not None and doi != normalize_doi(doi):
        errors.append("non_normalized_doi")

    discovered_via = data.get("discovered_via")
    if not isinstance(discovered_via, list) or not discovered_via:
        errors.append("invalid_discovered_via")

    return errors


def main() -> int:
    args = parse_args()
    outdir = args.outdir.resolve()
    manifest_path = outdir / "handoff_manifest.json"
    manifest = json.loads(manifest_path.read_text())

    valid = []
    invalid = []
    for filename in manifest.get("artifact_files", []):
        path = outdir / filename
        errors = validate_artifact(path)
        if errors:
            invalid.append({"file": filename, "errors": errors})
        else:
            valid.append(filename)

    report = {
        "inbox_version": "1.0",
        "artifacts_seen": len(manifest.get("artifact_files", [])),
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "valid_files": valid,
        "invalid_files": invalid,
    }
    (outdir / "inbox_validation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(f"artifacts={report['artifacts_seen']} valid={report['valid_count']} invalid={report['invalid_count']}")
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
