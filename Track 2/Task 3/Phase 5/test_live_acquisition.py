"""Phase 5 — OPT-IN live PDF acquisition proof.

Skipped by default (keeps the standard suite fully offline and deterministic).
Run with T2_LIVE=1 to perform a REAL Unpaywall->PLOS download and assert the
cascade validates the %PDF magic header and computes a SHA-256:

    T2_LIVE=1 python3 -m pytest "Phase 5/test_live_acquisition.py" -q

This proves the acquisition machinery end-to-end on a known open-access
gold-standard DOI WITHOUT touching the evaluated 10-ACCEPT DB (no DB writes,
scidownl never used). On success it also (re)writes the committed evidence
artifact `Phase 5/live_acquisition_proof.json`.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent

# Known open-access gold-standard DOIs (PLOS = reliably OA via Unpaywall):
#   Tschacher et al. 2012 — PLOS ONE      — #25 in CNFA_GOLD_STANDARD.md (core_CNFA)
#   Spiers & Maguire 2007 — PLOS Biology  — #23 (fallback)
TSCHACHER_DOI = "10.1371/journal.pone.0049236"
SPIERS_DOI = "10.1371/journal.pbio.0050048"

_LIVE = os.environ.get("T2_LIVE") == "1"


@pytest.mark.skipif(not _LIVE, reason="live network test; set T2_LIVE=1 to run")
def test_live_pdf_acquisition_proof(tmp_path):
    # Import inside the test so module collection never needs siblings or network.
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    from pdf_acquirer import acquire_by_doi  # noqa: E402

    result = acquire_by_doi(TSCHACHER_DOI, output_dir=tmp_path)
    if not result.outcome.startswith("acquired_"):
        # fall back to a second known-OA gold-standard DOI before failing
        result = acquire_by_doi(SPIERS_DOI, output_dir=tmp_path)

    assert result.outcome.startswith("acquired_"), f"acquisition failed: {result.error}"
    assert result.pdf_path and Path(result.pdf_path).exists()
    # real PDF: %PDF magic header
    assert Path(result.pdf_path).read_bytes()[:4] == b"%PDF"
    # SHA-256 shape + non-trivial size
    assert result.pdf_sha256 and re.fullmatch(r"[0-9a-f]{64}", result.pdf_sha256)
    assert result.pdf_bytes and result.pdf_bytes > 10_000

    proof = {
        "doi": result.doi,
        "source": result.outcome.replace("acquired_", ""),
        "source_url": result.source_url,
        "pdf_bytes": result.pdf_bytes,
        "sha256": result.pdf_sha256,
        "validated_pdf_header": True,
        "run_id": f"RUN-P5-PROOF-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": (
            "Capability proof on a known open-access gold-standard DOI. No DB "
            "writes; scidownl (grey source) not used. The evaluated 10-ACCEPT "
            "set yields 0 OA PDFs because those DOIs are paywalled/absent — a "
            "property of the retrieved corpus, not the acquisition code."
        ),
    }
    (_HERE / "live_acquisition_proof.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )
