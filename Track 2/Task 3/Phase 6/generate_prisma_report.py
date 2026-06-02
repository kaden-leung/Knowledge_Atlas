"""Phase 6 — PRISMA Dashboard generator.

Reads from the live DB and Phase 2-5 JSON files and produces:
  1. prisma_dashboard_data.json  — machine-readable snapshot (committed to git)
  2. prisma_dashboard.html       — self-contained dashboard page (data embedded in <script>)

Usage:
    python3 generate_prisma_report.py
    open prisma_dashboard.html

The HTML opens directly from the filesystem (file://) with no server needed.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TASK3 = _HERE.parent
_TRACK2 = _TASK3.parent

# Default paths (all relative to Track 2/Task 3/)
DEFAULT_DB = _TASK3 / "task3_pipeline_lifecycle.db"
DEFAULT_SEARCH_RESULTS = _TASK3 / "Phase 2" / "search_results.json"
DEFAULT_QUERY_RESULTS = _TRACK2 / "Task 2" / "Phase 3" / "query_results.json"
DEFAULT_STAGE1_REPORT = _TASK3 / "Phase 4" / "stage1_triage_report.json"
DEFAULT_ABSTRACT_REPORT = _TASK3 / "Phase 4" / "abstract_collection_report.json"
DEFAULT_HARVEST_REPORT = _TASK3 / "Phase 3" / "reference_harvest_results.json"

SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Data builder
# ---------------------------------------------------------------------------

def build_prisma_data(
    db_path: Path = DEFAULT_DB,
    search_results_json: Path = DEFAULT_SEARCH_RESULTS,
    query_results_json: Path = DEFAULT_QUERY_RESULTS,
    stage1_report_json: Path | None = DEFAULT_STAGE1_REPORT,
    abstract_report_json: Path | None = DEFAULT_ABSTRACT_REPORT,
    harvest_report_json: Path | None = DEFAULT_HARVEST_REPORT,
) -> dict:
    """Build the full dashboard data dict from all sources. Pure function; no side effects."""

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- Load JSON sources (with graceful fallback on missing files) ---
    sr = _load_json(search_results_json) or {}
    qr = _load_json(query_results_json) or {}
    s1 = _load_json(stage1_report_json) if stage1_report_json else {}
    abr = _load_json(abstract_report_json) if abstract_report_json else {}
    hr = _load_json(harvest_report_json) if harvest_report_json else {}

    # --- DB queries ---
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    db = _DbHelper(conn)

    # Triage stage counts
    total_refs = db.scalar("SELECT COUNT(*) FROM article_references")
    rejected_metadata = db.scalar(
        "SELECT COUNT(*) FROM article_references WHERE triage_stage='rejected_at_metadata'"
    )
    abstract_missing = db.scalar(
        "SELECT COUNT(*) FROM article_references WHERE triage_decision='MISSING_ABSTRACT'"
    )
    triage_complete = db.scalar(
        "SELECT COUNT(*) FROM article_references WHERE triage_stage='triage_complete'"
    )
    accept = db.scalar(
        "SELECT COUNT(*) FROM article_references WHERE triage_decision='ACCEPT'"
    )
    edge_case = db.scalar(
        "SELECT COUNT(*) FROM article_references WHERE triage_decision='EDGE_CASE'"
    )
    reject_stage2 = db.scalar(
        "SELECT COUNT(*) FROM article_references WHERE triage_decision='REJECT' AND triage_stage='triage_complete'"
    )
    in_queue = db.scalar("SELECT COUNT(*) FROM v_acquisition_queue")
    acquired = db.scalar(
        "SELECT COUNT(*) FROM article_references WHERE acquired_paper_id IS NOT NULL"
    )

    # Noise vs classifier breakdown from lifecycle_transitions
    noise_rejects = db.scalar(
        "SELECT COUNT(*) FROM lifecycle_transitions WHERE reason LIKE 'noise:%'"
    )
    clf_rejects = db.scalar(
        "SELECT COUNT(*) FROM lifecycle_transitions WHERE reason LIKE 'classifier_below_threshold%'"
    )
    passed_stage1 = db.scalar(
        "SELECT COUNT(*) FROM lifecycle_transitions WHERE reason LIKE 'stage1_passed%'"
    )

    # Abstract source breakdown from DB
    abstract_by_source = {}
    for src in ("semantic_scholar", "crossref", "pubmed", "openalex"):
        n = db.scalar(
            "SELECT COUNT(*) FROM article_references WHERE abstract_source=?", (src,)
        )
        if n:
            abstract_by_source[src] = n

    # discovered_via breakdown
    by_source = {}
    for src in ("serpapi_scholar", "scholarly_search", "paperscraper_search", "review_pdf_extract"):
        n = db.scalar(
            "SELECT COUNT(*) FROM article_references WHERE discovered_via LIKE ?",
            (f"%{src}%",)
        )
        by_source[src] = n

    conn.close()

    # --- Search results metadata ---
    sr_meta = sr.get("metadata") or {}
    raw_records = sr_meta.get("candidates_total_raw", 0)
    after_dedupe = sr_meta.get("candidates_after_dedupe", 0)
    duplicates_removed = raw_records - after_dedupe
    null_results_list = sr.get("null_results") or []
    queries_processed = sr_meta.get("queries_processed", 0)
    credits_used = sr_meta.get("credits_used", 0)
    per_source_raw = sr_meta.get("per_source_stats") or {}

    # --- Query VOI ---
    queries = qr.get("queries") or []
    top_voi = sorted(
        [{"display_id": q.get("display_id", "?"),
          "step_number": q.get("step_number"),
          "voi_score": float(q.get("voi_score") or 0),
          "boolean_query": q.get("boolean_query", "")}
         for q in queries if q.get("voi_score") is not None],
        key=lambda x: x["voi_score"],
        reverse=True,
    )[:5]

    # --- Abstract stats ---
    abstracts_found = sum(abstract_by_source.values())
    candidates_entering_stage2a = passed_stage1  # == 209

    # --- Harvest stats ---
    hr_meta = hr.get("metadata") or {}
    pdfs_scanned = hr_meta.get("pdfs_scanned", 0)
    raw_lines = hr_meta.get("raw_reference_lines", 0)

    # --- PRISMA funnel rows ---
    total_raw_all_sources = raw_records + by_source.get("review_pdf_extract", 0)
    prisma_funnel = [
        {"stage": "Gaps targeted (Task 2)", "count": len(queries), "indent": False},
        {"stage": "Queries executed (SerpAPI)", "count": queries_processed, "indent": False},
        {"stage": "Raw records returned (all sources)", "count": total_raw_all_sources, "indent": False},
        {"stage": "Duplicates removed (search layer)", "count": duplicates_removed, "indent": True},
        {"stage": "Records after search dedupe", "count": after_dedupe, "indent": False},
        {"stage": "PDF-reference harvest records", "count": by_source.get("review_pdf_extract", 0), "indent": False},
        {"stage": "Total in candidate buffer", "count": total_refs, "indent": False},
        {"stage": "Rejected at metadata (Stage 1)", "count": rejected_metadata, "indent": False, "highlight": "red-light"},
        {"stage": "→ Noise rules", "count": noise_rejects, "indent": True},
        {"stage": "→ Classifier < 0.20", "count": clf_rejects, "indent": True},
        {"stage": "Abstracts collected (Stage 2A)", "count": abstracts_found, "indent": False},
        {"stage": "MISSING_ABSTRACT (no abstract found)", "count": abstract_missing, "indent": False, "highlight": "grey"},
        {"stage": "Screened by classifier (Stage 2B)", "count": triage_complete, "indent": False},
        {"stage": "→ ACCEPT (on-topic, threshold VOI)", "count": accept, "indent": True, "highlight": "green"},
        {"stage": "→ EDGE_CASE (borderline)", "count": edge_case, "indent": True, "highlight": "yellow"},
        {"stage": "→ REJECT (off-topic)", "count": reject_stage2, "indent": True, "highlight": "red"},
    ]

    return {
        "generated_at": now,
        "schema_version": SCHEMA_VERSION,
        "execution_gaps": {
            "paperscraper_operational": False,
            "paperscraper_note": "Internal .jsonl extension bug; 0 results on all 10 live queries",
            "hierarchical_classifier": False,
            "hierarchical_classifier_note": "No .centroids.pkl file; keyword fallback used (coarser signal)",
            "pdf_acquisition_live": False,
            "pdf_acquisition_note": "Dry-run only; Unpaywall live run not executed",
            "query_failure_rate": 0.20,
            "failed_queries": ["SC3-step3", "L4-step3"],
        },
        "human_validation": {
            "accept_precision": 0.50,
            "true_positives": 3,
            "false_positives": 2,
            "borderline": 1,
            "note": "Manual review by pipeline author (conflict of interest; instructor review recommended)",
        },
        "gap_summary": {
            "total_gaps": len(queries),
            "top_voi": top_voi,
        },
        "search_summary": {
            "queries_run": queries_processed,
            "credits_used": credits_used,
            "raw_records": raw_records,
            "after_dedupe": after_dedupe,
            "duplicates_removed": duplicates_removed,
            "null_result_count": len(null_results_list),
            "null_results": [
                {"display_id": n.get("discovered_query_display_id"),
                 "reason": n.get("reason")}
                for n in null_results_list
            ],
            "per_source": {
                src: {
                    "queries_run": stats.get("queries_run", 0),
                    "results_raw": stats.get("results_raw", 0),
                    "errors": stats.get("errors", 0),
                }
                for src, stats in per_source_raw.items()
            },
        },
        "harvest_summary": {
            "pdfs_scanned": pdfs_scanned,
            "reference_lines_extracted": raw_lines,
            "harvested_rows": by_source.get("review_pdf_extract", 0),
        },
        "abstract_summary": {
            "candidates_entering": candidates_entering_stage2a,
            "abstracts_found": abstracts_found,
            "missing_abstract": abstract_missing,
            "hit_rate": round(abstracts_found / candidates_entering_stage2a, 4) if candidates_entering_stage2a else 0,
            "by_source": abstract_by_source,
        },
        "triage_summary": {
            "stage1_processed": total_refs,
            "rejected_at_metadata": rejected_metadata,
            "noise_rejects": noise_rejects,
            "classifier_rejects": clf_rejects,
            "passed_stage1": passed_stage1,
            "stage2b_processed": triage_complete,
            "accept": accept,
            "edge_case": edge_case,
            "reject_stage2b": reject_stage2,
            "missing_abstract_terminal": abstract_missing,
        },
        "prisma_funnel": prisma_funnel,
        "acquisition_summary": {
            "in_queue": in_queue,
            "acquired": acquired,
            "failed": 0,
            "gate_blocked": 0,
        },
    }


# ---------------------------------------------------------------------------
# HTML generator
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PRISMA-Inspired Dashboard — Track 2 Task 3</title>
<style>
:root {
  --green: #2e7d32; --green-bg: #e8f5e9;
  --red: #c62828;   --red-bg: #ffebee;
  --yellow: #f57f17; --yellow-bg: #fffde7;
  --grey: #546e7a;  --grey-bg: #eceff1;
  --blue: #0d47a1;  --blue-bg: #e3f2fd;
  --text: #212121;  --border: #dee2e6;
  --bg: #f5f7fa;    --card: #ffffff;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: var(--bg); color: var(--text); font-size: 14px; }
header { background: #1a237e; color: #fff; padding: 20px 32px; }
header h1 { font-size: 22px; font-weight: 600; }
header p  { opacity: .75; font-size: 13px; margin-top: 4px; }
.sections { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
.card { background: var(--card); border: 1px solid var(--border);
        border-radius: 8px; padding: 20px 24px; margin-bottom: 20px; }
.card h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px;
           border-bottom: 2px solid var(--blue); padding-bottom: 8px; color: var(--blue); }
.stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.stat-tile { background: var(--blue-bg); border-radius: 6px; padding: 12px 18px;
             min-width: 130px; flex: 1; }
.stat-tile.green { background: var(--green-bg); }
.stat-tile.red   { background: var(--red-bg); }
.stat-tile.grey  { background: var(--grey-bg); }
.stat-tile .label { font-size: 11px; text-transform: uppercase; opacity: .65; margin-bottom: 4px; }
.stat-tile .value { font-size: 28px; font-weight: 700; color: var(--blue); }
.stat-tile.green .value { color: var(--green); }
.stat-tile.red   .value { color: var(--red); }
.stat-tile.grey  .value { color: var(--grey); }
table { width: 100%; border-collapse: collapse; }
th,td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }
th { font-weight: 600; background: var(--bg); font-size: 12px; text-transform: uppercase; }
tr:hover td { background: #f8f9ff; }
.bar-container { height: 8px; background: var(--border); border-radius: 4px;
                 min-width: 80px; display: inline-block; vertical-align: middle; }
.bar-fill { height: 100%; border-radius: 4px; background: var(--blue); }
.bar-fill.green  { background: var(--green); }
.bar-fill.red    { background: var(--red); }
.bar-fill.yellow { background: var(--yellow); }
.bar-fill.grey   { background: var(--grey); }
.indent { padding-left: 24px !important; color: #555; }
.funnel-highlight-green { background: var(--green-bg) !important; }
.funnel-highlight-red   { background: var(--red-bg) !important; }
.funnel-highlight-yellow{ background: var(--yellow-bg) !important; }
.funnel-highlight-grey  { background: var(--grey-bg) !important; }
.funnel-highlight-red-light { background: #fff3f3 !important; }
.voi-bar-row { display: flex; align-items: center; gap: 10px; margin: 6px 0; font-size: 13px; }
.voi-bar-label { width: 80px; font-weight: 600; color: var(--blue); flex-shrink: 0; }
.voi-bar-track { flex: 1; height: 18px; background: var(--border); border-radius: 4px; overflow: hidden; }
.voi-bar-fill  { height: 100%; background: var(--blue); border-radius: 4px; display: flex; align-items: center;
                 padding-left: 6px; color: #fff; font-size: 11px; font-weight: 600; min-width: 40px; }
.source-badge { display: inline-block; padding: 2px 8px; border-radius: 12px;
                font-size: 11px; font-weight: 600; background: var(--blue-bg); color: var(--blue); }
.note { font-size: 12px; color: #777; margin-top: 8px; font-style: italic; }
</style>
</head>
<body>
<header>
  <h1>PRISMA-Inspired Dashboard — Track 2 · Task 3</h1>
  <p>UCSD COGS 160 &nbsp;|&nbsp; Author: Kaden Leung &nbsp;|&nbsp; Generated: <span id="gen-at"></span></p>
  <p style="opacity:.6;font-size:11px;margin-top:4px">Note: PRISMA-inspired funnel structure; not a formally PRISMA-compliant systematic review. See MANIFEST.md for full execution matrix and human validation.</p>
</header>
<div class="sections">

<!-- 0. EXECUTION STATUS / WARNINGS -->
<div class="card" style="border-color:#e53935">
  <h2 style="color:#c62828">⚠ Execution Status — Demonstrated vs. Designed</h2>
  <table>
    <thead><tr><th>Component</th><th>Designed</th><th>Demonstrated</th><th>Impact</th></tr></thead>
    <tbody>
      <tr><td>SerpAPI retrieval</td><td>✅ Yes</td><td>✅ Yes</td><td>10 queries, 2 returned zero results (20% failure)</td></tr>
      <tr><td>scholarly retrieval</td><td>✅ Yes</td><td>✅ Yes</td><td>80 results, clean</td></tr>
      <tr><td>paperscraper retrieval</td><td>✅ Yes</td><td style="color:var(--red)">❌ Not operational</td><td>0 results — internal .jsonl bug; counts as 0 contribution</td></tr>
      <tr><td>Reference harvester (PDF)</td><td>✅ Yes</td><td>✅ Yes</td><td>1,103 rows from 20 PDFs</td></tr>
      <tr><td>HierarchicalClassifier</td><td>✅ Yes</td><td style="color:var(--red)">❌ Not available</td><td>Keyword fallback used; coarser signal</td></tr>
      <tr><td>PDF acquisition</td><td>✅ Yes</td><td style="color:var(--yellow)">⚠ Dry-run only</td><td>Gate open; Unpaywall live run not executed</td></tr>
    </tbody>
  </table>
  <p style="margin-top:12px;font-size:12px;color:#666">ACCEPT precision (manual review): <strong>3/6 true positives (50%)</strong>. See HUMAN_VALIDATION.md for full assessment. Threshold was recalibrated from voi_medium=0.50 → 0.40 after observing 0 ACCEPTs; see sensitivity table in HUMAN_VALIDATION.md §2.</p>
</div>

<!-- 1. GAP SUMMARY -->
<div class="card">
  <h2>1. Gap Summary</h2>
  <div class="stat-row">
    <div class="stat-tile"><div class="label">Gaps Targeted</div><div class="value" id="total-gaps"></div></div>
    <div class="stat-tile"><div class="label">Top VOI Score</div><div class="value" id="top-voi-score"></div></div>
    <div class="stat-tile grey"><div class="label">Null Results</div><div class="value" id="null-count"></div></div>
  </div>
  <p style="font-weight:600; font-size:12px; text-transform:uppercase; opacity:.6; margin-bottom:8px;">Top 5 Gaps by VOI Score</p>
  <div id="voi-bars"></div>
</div>

<!-- 2. SEARCH SUMMARY -->
<div class="card">
  <h2>2. Search Summary</h2>
  <div class="stat-row">
    <div class="stat-tile"><div class="label">Queries Run</div><div class="value" id="queries-run"></div></div>
    <div class="stat-tile"><div class="label">Credits Used</div><div class="value" id="credits-used"></div></div>
    <div class="stat-tile"><div class="label">Raw Records</div><div class="value" id="raw-records"></div></div>
    <div class="stat-tile"><div class="label">After Dedupe</div><div class="value" id="after-dedupe"></div></div>
  </div>
  <table>
    <thead><tr><th>Source</th><th>Queries Run</th><th>Results</th><th>Errors</th></tr></thead>
    <tbody id="source-table"></tbody>
  </table>
  <div id="null-results-section"></div>
</div>

<!-- 3. ABSTRACT COLLECTION -->
<div class="card">
  <h2>3. Abstract Collection (Stage 2A)</h2>
  <div class="stat-row">
    <div class="stat-tile"><div class="label">Candidates In</div><div class="value" id="abs-in"></div></div>
    <div class="stat-tile green"><div class="label">Abstracts Found</div><div class="value" id="abs-found"></div></div>
    <div class="stat-tile grey"><div class="label">Missing Abstract</div><div class="value" id="abs-missing"></div></div>
    <div class="stat-tile"><div class="label">Hit Rate</div><div class="value" id="abs-rate"></div></div>
  </div>
  <table>
    <thead><tr><th>Source</th><th>Abstracts</th><th>Share</th></tr></thead>
    <tbody id="abstract-source-table"></tbody>
  </table>
</div>

<!-- 4. TRIAGE RESULTS -->
<div class="card">
  <h2>4. Triage Results</h2>
  <div class="stat-row">
    <div class="stat-tile green"><div class="label">ACCEPT</div><div class="value" id="t-accept"></div></div>
    <div class="stat-tile" style="background:var(--yellow-bg)"><div class="label">EDGE_CASE</div><div class="value" style="color:var(--yellow)" id="t-edge"></div></div>
    <div class="stat-tile red"><div class="label">REJECT (all stages)</div><div class="value" id="t-reject-all"></div></div>
    <div class="stat-tile grey"><div class="label">MISSING_ABSTRACT</div><div class="value" id="t-missing"></div></div>
  </div>
  <table>
    <thead><tr><th>Stage</th><th>Count</th></tr></thead>
    <tbody id="triage-breakdown"></tbody>
  </table>
</div>

<!-- 5. PRISMA FUNNEL -->
<div class="card">
  <h2>5. PRISMA Funnel</h2>
  <table>
    <thead><tr><th>Funnel Stage</th><th>Count</th><th style="min-width:120px">Proportion</th></tr></thead>
    <tbody id="prisma-table"></tbody>
  </table>
  <p class="note">Proportion bars relative to total candidate buffer (1193).</p>
</div>

<!-- 6. NULL RESULTS -->
<div class="card">
  <h2>6. Null Results — Gaps With Zero Papers Found</h2>
  <p id="null-results-intro"></p>
  <table id="null-results-table" style="margin-top:12px">
    <thead><tr><th>Query ID</th><th>Boolean Query</th><th>Reason</th></tr></thead>
    <tbody id="null-results-body"></tbody>
  </table>
</div>

</div><!-- /sections -->

<script>
// Data is embedded below by the Python generator
const DATA = __DATA_PLACEHOLDER__;

// Render helpers
const el = id => document.getElementById(id);
const fmt = n => n === null || n === undefined ? '—' : n.toLocaleString();

function pct(n, total) {
  if (!total) return 0;
  return Math.round((n / total) * 100);
}

function barHtml(n, total, cls='') {
  const p = Math.min(pct(n, total), 100);
  return `<span class="bar-container" style="width:100px"><span class="bar-fill ${cls}" style="width:${p}%"></span></span>`;
}

// Header
el('gen-at').textContent = DATA.generated_at;

// 1. Gap Summary
el('total-gaps').textContent = fmt(DATA.gap_summary.total_gaps);
el('top-voi-score').textContent = DATA.gap_summary.top_voi[0]?.voi_score?.toFixed(3) ?? '—';
el('null-count').textContent = fmt(DATA.search_summary.null_result_count);

const voiBarsEl = el('voi-bars');
const maxVoi = Math.max(...DATA.gap_summary.top_voi.map(g => g.voi_score));
DATA.gap_summary.top_voi.forEach(g => {
  const pct = Math.round((g.voi_score / 1.0) * 100);
  const label = g.step_number != null ? `${g.display_id}-step${g.step_number}` : g.display_id;
  voiBarsEl.innerHTML += `
    <div class="voi-bar-row">
      <div class="voi-bar-label">${label}</div>
      <div class="voi-bar-track">
        <div class="voi-bar-fill" style="width:${pct}%">${g.voi_score.toFixed(3)}</div>
      </div>
    </div>`;
});

// 2. Search Summary
el('queries-run').textContent = fmt(DATA.search_summary.queries_run);
el('credits-used').textContent = fmt(DATA.search_summary.credits_used);
el('raw-records').textContent = fmt(DATA.search_summary.raw_records);
el('after-dedupe').textContent = fmt(DATA.search_summary.after_dedupe);

const srcTbody = el('source-table');
Object.entries(DATA.search_summary.per_source).forEach(([src, s]) => {
  const name = src.replace('_', ' ');
  srcTbody.innerHTML += `<tr>
    <td><span class="source-badge">${name}</span></td>
    <td>${fmt(s.queries_run)}</td>
    <td>${fmt(s.results_raw)}</td>
    <td>${s.errors > 0 ? `<span style="color:var(--red)">${s.errors}</span>` : '0'}</td>
  </tr>`;
});

// 3. Abstract Collection
const abs = DATA.abstract_summary;
el('abs-in').textContent = fmt(abs.candidates_entering);
el('abs-found').textContent = fmt(abs.abstracts_found);
el('abs-missing').textContent = fmt(abs.missing_abstract);
el('abs-rate').textContent = (abs.hit_rate * 100).toFixed(1) + '%';

const absSrcTbody = el('abstract-source-table');
const totalAbs = abs.abstracts_found || 1;
Object.entries(abs.by_source).forEach(([src, n]) => {
  absSrcTbody.innerHTML += `<tr>
    <td><span class="source-badge">${src.replace('_', ' ')}</span></td>
    <td>${fmt(n)}</td>
    <td>${barHtml(n, totalAbs)}</td>
  </tr>`;
});

// 4. Triage Results
const tr = DATA.triage_summary;
el('t-accept').textContent  = fmt(tr.accept);
el('t-edge').textContent    = fmt(tr.edge_case);
el('t-reject-all').textContent = fmt(tr.rejected_at_metadata + tr.reject_stage2b);
el('t-missing').textContent = fmt(tr.missing_abstract_terminal);

const triageBreakdownEl = el('triage-breakdown');
[
  ['Total in candidate buffer', tr.stage1_processed],
  ['Rejected at metadata (Stage 1)', tr.rejected_at_metadata],
  ['  → Noise rules', tr.noise_rejects],
  ['  → Classifier < 0.20', tr.classifier_rejects],
  ['Passed Stage 1 → abstract pending', tr.passed_stage1],
  ['Abstracts collected (Stage 2A)', tr.stage2b_processed - tr.edge_case],
  ['MISSING_ABSTRACT (no abstract)', tr.missing_abstract_terminal],
  ['Triaged by Stage 2B', tr.stage2b_processed],
  ['  → ACCEPT', tr.accept],
  ['  → EDGE_CASE', tr.edge_case],
  ['  → REJECT', tr.reject_stage2b],
].forEach(([label, count]) => {
  const indent = label.startsWith('  ');
  triageBreakdownEl.innerHTML += `<tr>
    <td class="${indent ? 'indent' : ''}">${label.trim()}</td>
    <td><strong>${fmt(count)}</strong></td>
  </tr>`;
});

// 5. PRISMA Funnel
const totalForBar = DATA.triage_summary.stage1_processed;
const prismaTbody = el('prisma-table');
DATA.prisma_funnel.forEach(row => {
  const hlClass = row.highlight ? `funnel-highlight-${row.highlight}` : '';
  const indentClass = row.indent ? 'indent' : '';
  const barCls = row.highlight === 'green' ? 'green'
               : row.highlight === 'red' || row.highlight === 'red-light' ? 'red'
               : row.highlight === 'yellow' ? 'yellow'
               : row.highlight === 'grey' ? 'grey' : '';
  prismaTbody.innerHTML += `<tr class="${hlClass}">
    <td class="${indentClass}">${row.indent ? '→ ' : ''}${row.stage}</td>
    <td><strong>${fmt(row.count)}</strong></td>
    <td>${barHtml(row.count, totalForBar, barCls)}</td>
  </tr>`;
});

// 6. Null Results
const nr = DATA.search_summary.null_results;
el('null-results-intro').textContent = nr.length === 0
  ? 'All queries returned at least one result.'
  : `${nr.length} quer${nr.length === 1 ? 'y' : 'ies'} returned zero papers across all sources:`;

const nrBody = el('null-results-body');
if (nr.length === 0) {
  nrBody.innerHTML = '<tr><td colspan="3" style="color:#888">None</td></tr>';
} else {
  nr.forEach(n => {
    // Find the original boolean query from gap_summary
    const gap = DATA.gap_summary.top_voi.find(g => {
      const label = g.step_number != null ? `${g.display_id}-step${g.step_number}` : g.display_id;
      return label === n.display_id;
    });
    nrBody.innerHTML += `<tr>
      <td><strong>${n.display_id}</strong></td>
      <td style="font-family:monospace;font-size:11px">${gap ? gap.boolean_query.substring(0, 80) + '…' : '(query text unavailable)'}</td>
      <td>${n.reason}</td>
    </tr>`;
  });
}

// Also show null results from search_results.json in Section 2
const nullSecEl = el('null-results-section');
if (nr.length > 0) {
  nullSecEl.innerHTML = `<p style="margin-top:12px;color:var(--red);font-size:13px">⚠ ${nr.length} null-result quer${nr.length===1?'y':'ies'}: ${nr.map(n=>n.display_id).join(', ')}</p>`;
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTML injection
# ---------------------------------------------------------------------------

def build_html(data: dict) -> str:
    """Inject the data JSON into the HTML template's placeholder."""
    json_str = json.dumps(data, ensure_ascii=False, indent=None)
    return _HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", json_str)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path | None) -> dict | None:
    if path and Path(path).exists():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


class _DbHelper:
    def __init__(self, conn: sqlite3.Connection):
        self._c = conn

    def scalar(self, sql: str, params: tuple = ()) -> int:
        row = self._c.execute(sql, params).fetchone()
        return row[0] if row else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Phase 6 PRISMA dashboard generator")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--search-results", default=str(DEFAULT_SEARCH_RESULTS))
    parser.add_argument("--query-results", default=str(DEFAULT_QUERY_RESULTS))
    parser.add_argument("--output-json", default=str(_HERE / "prisma_dashboard_data.json"))
    parser.add_argument("--output-html", default=str(_HERE / "prisma_dashboard.html"))
    args = parser.parse_args(argv)

    data = build_prisma_data(
        db_path=Path(args.db),
        search_results_json=Path(args.search_results),
        query_results_json=Path(args.query_results),
    )

    json_path = Path(args.output_json)
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {json_path}", file=sys.stderr)

    html_path = Path(args.output_html)
    html_path.write_text(build_html(data), encoding="utf-8")
    print(f"Written: {html_path}", file=sys.stderr)
    print(f"Open in browser: open {html_path}", file=sys.stderr)

    # Print summary
    t = data["triage_summary"]
    print(f"\nPRISMA summary: {t['stage1_processed']} total → "
          f"{t['rejected_at_metadata']} rejected Stage1 → "
          f"{t['accept']} ACCEPT | {t['edge_case']} EDGE | {t['reject_stage2b']} REJECT",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
