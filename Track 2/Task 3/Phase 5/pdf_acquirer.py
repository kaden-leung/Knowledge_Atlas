"""Phase 5 — PDF Acquisition Cascade.

Reads v_acquisition_queue and walks each ACCEPT row through:
  1. Unpaywall
  2. OpenAlex OA URL
  3. scidownl (policy-gated — see PDF_ACQUISITION_CONTRACT.md §5)

See PDF_ACQUISITION_CONTRACT.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# SSL fix (same macOS cert issue as Phase 4)
try:
    import certifi as _certifi
    os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _certifi.where())
except ImportError:
    pass

_HERE = Path(__file__).resolve().parent
_COGS160 = _HERE.parents[2]
_PHASE4 = _HERE.parent / "Phase 4"

# Add paths for Article_Finder and Phase 4's openalex_client
for p in (
    str(_COGS160 / "Article_Finder"),
    str(_COGS160 / "Article_Finder" / "ingest"),
    str(_PHASE4),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from openalex_client import OpenAlexClient  # noqa: E402

DEFAULT_DB = _HERE.parent / "task3_pipeline_lifecycle.db"
DEFAULT_CONFIG = _HERE / "phase5_config.yaml"
DEFAULT_POLICY_CLEARANCE = _HERE / "policy_clearance.json"
DEFAULT_OUTPUT_DIR = _HERE / "acquired_pdfs"
DEFAULT_REPORT = _HERE / "acquisition_report.json"

_UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
_POLITE_EMAIL = "kaden-leung@users.noreply.github.com"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(path: Path | None) -> dict[str, Any]:
    """Load phase5_config.yaml; return {} if missing (all defaults apply)."""
    if not path or not path.exists():
        return {}
    try:
        import yaml  # optional; fallback to json-yaml-like manual parse
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # yaml not installed — hand-parse just the keys we need
        config: dict = {}
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "enable_paid_or_grey_sources" in line and ":" in line:
                val = line.split(":", 1)[1].strip().lower()
                config["enable_paid_or_grey_sources"] = val in ("true", "yes", "1")
        return config


# ---------------------------------------------------------------------------
# Unpaywall
# ---------------------------------------------------------------------------

def _unpaywall_get_pdf_url(doi: str, email: str, timeout: int = 30) -> str | None:
    """Query Unpaywall for the best OA PDF URL. Returns None if not found."""
    if not doi:
        return None
    url = f"{_UNPAYWALL_BASE}/{urllib.parse.quote(doi, safe='')}?email={email}"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"ATLAS-Phase5/1.0 (mailto:{email})"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        best = data.get("best_oa_location") or {}
        if best.get("url_for_pdf"):
            return best["url_for_pdf"]
        for loc in data.get("oa_locations", []):
            if loc.get("url_for_pdf"):
                return loc["url_for_pdf"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# PDF download + validation
# ---------------------------------------------------------------------------

def _download_pdf(url: str, dest: Path, email: str, timeout: int = 60) -> tuple[bool, str]:
    """Download URL to dest. Returns (success, error_or_empty)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": f"ATLAS-Phase5/1.0 (mailto:{email})",
        "Accept": "application/pdf,*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data.startswith(b"%PDF"):
            return False, "not_a_pdf:missing_%PDF_header"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True, ""
    except urllib.error.HTTPError as e:
        return False, f"http_{e.code}"
    except Exception as e:
        return False, str(e)


def _pdf_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Policy gate
# ---------------------------------------------------------------------------

def _scidownl_gate_passes(
    row: dict,
    config: dict,
    policy_clearance_path: Path,
    unpaywall_failed: bool,
    openalex_failed: bool,
) -> tuple[bool, str]:
    """Return (passes, reason). All 4 conditions must be True."""
    if not config.get("enable_paid_or_grey_sources", False):
        return False, "config:enable_paid_or_grey_sources is false"
    if not policy_clearance_path.exists():
        return False, "policy_clearance.json missing or not countersigned"
    if not (unpaywall_failed and openalex_failed):
        return False, "cascade not exhausted (free source succeeded or not tried)"
    if row.get("triage_decision") != "ACCEPT":
        return False, f"row is {row.get('triage_decision')}, not ACCEPT"
    return True, "all four conditions met"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AcquisitionResult:
    reference_id: str
    doi: str | None
    outcome: str          # see PDF_ACQUISITION_CONTRACT.md §6
    pdf_path: str | None = None
    pdf_sha256: str | None = None
    pdf_bytes: int | None = None
    error: str | None = None
    source_url: str | None = None


@dataclass
class AcquisitionReport:
    schema_version: str = "1.0.0"
    run_id: str = ""
    started_at: str = ""
    ended_at: str = ""
    rows_processed: int = 0
    acquired: dict[str, int] = field(default_factory=lambda: {
        "unpaywall": 0, "openalex": 0, "scidownl": 0
    })
    failed_all_sources: int = 0
    scidownl_gate_blocked: int = 0
    no_doi: int = 0
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "rows_processed": self.rows_processed,
            "acquired": dict(self.acquired),
            "failed_all_sources": self.failed_all_sources,
            "scidownl_gate_blocked": self.scidownl_gate_blocked,
            "no_doi": self.no_doi,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _log_attempt(conn: sqlite3.Connection, reference_id: str, run_id: str,
                 reason: str) -> None:
    conn.execute(
        """
        INSERT INTO lifecycle_transitions
          (reference_id, run_id, from_stage, to_stage, reason, created_by)
        VALUES (?, ?, 'triage_complete', 'triage_complete', ?, 'pdf_acquirer')
        """,
        (reference_id, run_id, reason),
    )


def _mark_acquired(conn: sqlite3.Connection, reference_id: str,
                   pdf_path: str, last_source: str) -> None:
    acquired_paper_id = f"{reference_id}-PDF"
    conn.execute(
        """
        UPDATE article_references
           SET acquired_paper_id = ?,
               pdf_acquisition_last_source = ?,
               updated_at = ?
         WHERE reference_id = ?
        """,
        (acquired_paper_id, last_source, utc_now_iso(), reference_id),
    )


def _bump_attempts(conn: sqlite3.Connection, reference_id: str,
                   last_source: str) -> None:
    conn.execute(
        """
        UPDATE article_references
           SET pdf_acquisition_attempts = pdf_acquisition_attempts + 1,
               pdf_acquisition_last_source = ?,
               updated_at = ?
         WHERE reference_id = ?
        """,
        (last_source, utc_now_iso(), reference_id),
    )


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _acquire_one(
    row: dict,
    *,
    run_id: str,
    conn: sqlite3.Connection,
    config: dict,
    policy_clearance_path: Path,
    output_dir: Path,
    email: str,
    timeout: int,
    oa_client: OpenAlexClient,
    mock: bool = False,
    mock_unpaywall_url: str | None = None,
    mock_openalex_url: str | None = None,
    mock_scidownl_success: bool = False,
    dry_run: bool = False,
) -> AcquisitionResult:
    """Walk the cascade for a single row. Returns the result."""
    ref_id = row["reference_id"]
    doi = row["doi"]

    if not doi:
        _bump_attempts(conn, ref_id, "none_no_doi")
        _log_attempt(conn, ref_id, run_id, "acquisition_failed_no_doi")
        return AcquisitionResult(ref_id, doi, "no_doi",
                                 error="no_doi_for_unpaywall_or_openalex")

    dest = output_dir / f"{ref_id}.pdf"

    # Step 1: Unpaywall
    unpaywall_pdf_url = (
        mock_unpaywall_url if mock else _unpaywall_get_pdf_url(doi, email, timeout)
    )
    _bump_attempts(conn, ref_id, "unpaywall")
    if unpaywall_pdf_url:
        if dry_run:
            ok, err = True, ""   # pretend success; no disk write
        elif mock:
            ok, err = True, ""
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-1.4 mock-unpaywall")
        else:
            ok, err = _download_pdf(unpaywall_pdf_url, dest, email, timeout)
        if ok:
            _mark_acquired(conn, ref_id, str(dest), "unpaywall")
            _log_attempt(conn, ref_id, run_id, "acquisition_unpaywall:success")
            sha = _pdf_hash(dest) if dest.exists() else None
            size = dest.stat().st_size if dest.exists() else 0
            return AcquisitionResult(
                ref_id, doi, "acquired_unpaywall", str(dest), sha, size
            )
        else:
            _log_attempt(conn, ref_id, run_id, f"acquisition_unpaywall:fail_{err}")
    else:
        _log_attempt(conn, ref_id, run_id, "acquisition_unpaywall:fail_no_oa_url")

    # Step 2: OpenAlex OA URL
    openalex_pdf_url = (
        mock_openalex_url if mock else oa_client.get_oa_pdf_url(doi)
    )
    _bump_attempts(conn, ref_id, "openalex")
    if openalex_pdf_url:
        if dry_run:
            ok, err = True, ""
        elif mock:
            ok, err = True, ""
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-1.4 mock-openalex")
        else:
            ok, err = _download_pdf(openalex_pdf_url, dest, email, timeout)
        if ok:
            _mark_acquired(conn, ref_id, str(dest), "openalex")
            _log_attempt(conn, ref_id, run_id, "acquisition_openalex:success")
            sha = _pdf_hash(dest) if dest.exists() else None
            size = dest.stat().st_size if dest.exists() else 0
            return AcquisitionResult(
                ref_id, doi, "acquired_openalex", str(dest), sha, size
            )
        else:
            _log_attempt(conn, ref_id, run_id, f"acquisition_openalex:fail_{err}")
    else:
        _log_attempt(conn, ref_id, run_id, "acquisition_openalex:fail_no_oa_url")

    # Step 3: scidownl (policy-gated)
    gate_passes, gate_reason = _scidownl_gate_passes(
        row, config, policy_clearance_path,
        unpaywall_failed=True, openalex_failed=True
    )
    if not gate_passes:
        _bump_attempts(conn, ref_id, "scidownl_blocked")
        _log_attempt(conn, ref_id, run_id,
                     f"acquisition_scidownl:blocked_policy_gate:{gate_reason}")
        _log_attempt(conn, ref_id, run_id, "acquisition_failed_all_sources")
        return AcquisitionResult(
            ref_id, doi, "skipped_policy_gate",
            error=f"scidownl gate blocked: {gate_reason}"
        )

    # Gate passes — attempt scidownl
    _bump_attempts(conn, ref_id, "scidownl")
    scidownl_ok = False
    scidownl_err = ""
    if mock:
        scidownl_ok = mock_scidownl_success
        if scidownl_ok:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-1.4 mock-scidownl")
    else:
        try:
            from scidownl import scihub_download
            scihub_download(doi, paper_type="doi", out=str(dest.parent))
            # scidownl doesn't tell us the filename; scan for any new PDF
            found_pdf = None
            for f in dest.parent.glob("*.pdf"):
                if f != dest:
                    f.rename(dest)
                    found_pdf = dest
                    break
            if found_pdf and dest.exists() and dest.read_bytes()[:4] == b"%PDF":
                scidownl_ok = True
            else:
                scidownl_err = "no_valid_pdf_written"
        except Exception as exc:
            scidownl_err = str(exc)[:80]

    if scidownl_ok:
        _mark_acquired(conn, ref_id, str(dest), "scidownl")
        _log_attempt(conn, ref_id, run_id, "acquisition_scidownl:success")
        return AcquisitionResult(
            ref_id, doi, "acquired_scidownl", str(dest),
            _pdf_hash(dest), dest.stat().st_size
        )
    else:
        _log_attempt(conn, ref_id, run_id,
                     f"acquisition_scidownl:fail_{scidownl_err or 'unknown'}")
        _log_attempt(conn, ref_id, run_id, "acquisition_failed_all_sources")
        return AcquisitionResult(ref_id, doi, "failed_all_sources",
                                 error=f"scidownl failed: {scidownl_err}")


def acquire_by_doi(
    doi: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    email: str = _POLITE_EMAIL,
    timeout: int = 60,
) -> AcquisitionResult:
    """Capability proof for the free OA cascade on a single DOI.

    Runs Unpaywall -> OpenAlex, downloads the OA PDF, validates the %PDF magic
    header, and computes a SHA-256 — reusing the exact functions the production
    cascade uses (`_unpaywall_get_pdf_url`, `OpenAlexClient.get_oa_pdf_url`,
    `_download_pdf`, `_pdf_hash`). It performs NO DB writes and never touches the
    policy-gated scidownl source, so it demonstrates that the acquisition
    machinery works end-to-end on a known open-access paper WITHOUT mutating the
    evaluated pipeline or its ACCEPT set. Returns an AcquisitionResult.
    """
    if not doi:
        return AcquisitionResult("(by-doi)", doi, "no_doi", error="no_doi_provided")

    dest = output_dir / f"{doi.replace('/', '_')}.pdf"

    # Step 1: Unpaywall
    url = _unpaywall_get_pdf_url(doi, email, timeout)
    source = "unpaywall"

    # Step 2: OpenAlex OA fallback
    if not url:
        try:
            url = OpenAlexClient(min_delay=0.12).get_oa_pdf_url(doi)
            source = "openalex"
        except Exception:
            url = None

    if not url:
        return AcquisitionResult(
            "(by-doi)", doi, "failed_all_sources",
            error="no_oa_url_from_unpaywall_or_openalex",
        )

    ok, err = _download_pdf(url, dest, email, timeout)
    if not ok:
        return AcquisitionResult(
            "(by-doi)", doi, "failed_all_sources", error=err, source_url=url
        )

    return AcquisitionResult(
        "(by-doi)", doi, f"acquired_{source}",
        pdf_path=str(dest), pdf_sha256=_pdf_hash(dest),
        pdf_bytes=dest.stat().st_size, source_url=url,
    )


def run_acquisition(
    *,
    db_path: Path,
    run_id: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    config_path: Path | None = DEFAULT_CONFIG,
    policy_clearance_path: Path = DEFAULT_POLICY_CLEARANCE,
    max_rows: int | None = None,
    mock: bool = False,
    mock_unpaywall_url: str | None = None,
    mock_openalex_url: str | None = None,
    mock_scidownl_success: bool = False,
    dry_run: bool = False,
) -> AcquisitionReport:
    config = load_config(config_path)
    email = config.get("acquisition", {}).get("email", _POLITE_EMAIL)
    timeout = config.get("acquisition", {}).get("timeout_seconds", 60)

    report = AcquisitionReport(run_id=run_id, started_at=utc_now_iso())

    if dry_run:
        src = sqlite3.connect(str(db_path))
        conn = sqlite3.connect(":memory:")
        src.backup(conn)
        src.close()
    else:
        conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    # Load OpenAlex client (no network in mock/dry-run)
    oa_client = OpenAlexClient(min_delay=0.12)

    try:
        # v_acquisition_queue filters to ACCEPT+unacquired but doesn't expose
        # triage_decision as a column (it's in the WHERE clause). Query
        # article_references directly with the same conditions to get all fields.
        rows = conn.execute(
            "SELECT reference_id, doi, voi_score, triage_decision "
            "FROM article_references "
            "WHERE triage_decision = 'ACCEPT' AND acquired_paper_id IS NULL "
            "ORDER BY voi_score DESC NULLS LAST, rowid ASC"
        ).fetchall()
        if max_rows is not None:
            rows = rows[:max_rows]

        total = len(rows)
        for i, row_raw in enumerate(rows, start=1):
            row = dict(row_raw)
            report.rows_processed += 1
            print(
                f"[{i}/{total}] {row['reference_id']} doi={row['doi']} voi={row['voi_score']}",
                file=sys.stderr, flush=True,
            )

            try:
                result = _acquire_one(
                    row, run_id=run_id, conn=conn, config=config,
                    policy_clearance_path=policy_clearance_path,
                    output_dir=output_dir, email=email, timeout=timeout,
                    oa_client=oa_client, mock=mock,
                    mock_unpaywall_url=mock_unpaywall_url,
                    mock_openalex_url=mock_openalex_url,
                    mock_scidownl_success=mock_scidownl_success,
                    dry_run=dry_run,
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                report.errors.append({"reference_id": row["reference_id"], "error": str(exc)})
                continue

            outcome = result.outcome
            if outcome.startswith("acquired_"):
                source = outcome.split("_", 1)[1]
                report.acquired[source] = report.acquired.get(source, 0) + 1
            elif outcome == "failed_all_sources":
                report.failed_all_sources += 1
            elif outcome == "skipped_policy_gate":
                report.scidownl_gate_blocked += 1
            elif outcome == "no_doi":
                report.no_doi += 1

            print(
                f"  → {outcome}"
                + (f" | {result.error}" if result.error else ""),
                file=sys.stderr, flush=True,
            )

    finally:
        conn.close()

    report.ended_at = utc_now_iso()
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5 PDF acquisition cascade")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--policy-clearance", default=str(DEFAULT_POLICY_CLEARANCE))
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args(argv)

    run_id = args.run_id or f"RUN-P5-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    report = run_acquisition(
        db_path=Path(args.db),
        run_id=run_id,
        output_dir=Path(args.output_dir),
        config_path=Path(args.config),
        policy_clearance_path=Path(args.policy_clearance),
        max_rows=args.max_rows,
        dry_run=args.dry_run,
    )

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    total_acquired = sum(report.acquired.values())
    print(
        f"[pdf_acquirer] processed={report.rows_processed} "
        f"acquired={total_acquired} "
        f"failed={report.failed_all_sources} "
        f"gate_blocked={report.scidownl_gate_blocked} "
        f"no_doi={report.no_doi}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
