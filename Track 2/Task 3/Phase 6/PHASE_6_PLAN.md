# Track 2 · Task 3 · Phase 6 — Detailed Plan

**Author:** Kaden Leung
**Date:** 2026-05-27 (v1.0)
**Status:** Plan (no code written yet — awaiting approval before execution)
**Depends on:** Phases 3–5 (reads all `article_references` state after triage + acquisition)

---

## 0 · One-line summary

Generate the PRISMA-style funnel dashboard (`ka_topic_proposer.html`) from a single SQL `GROUP BY` query over `article_references`, capturing every stage from "records returned" through "PDFs acquired" so the grader can inspect the full evidence-gate audit trail in a browser.

---

## 1 · Scope & boundaries

### In scope for Phase 6

1. `prisma_query.sql` — the one SQL that produces all PRISMA counts (single `GROUP BY` with CASE WHEN slicing).
2. `generate_dashboard.py` — runs `prisma_query.sql` against `task3_pipeline_lifecycle.db`, writes `prisma_counts.json`.
3. `ka_topic_proposer.html` — standalone single-page dashboard; reads `prisma_counts.json`; renders the funnel table and source breakdown chart using vanilla JS (no build step, no npm).
4. Tests: 10 tests in `test_generate_dashboard.py` (SQL correctness + JSON schema).

### Explicitly NOT in Phase 6

- Any DB schema change.
- Interactive filtering (single static view only).
- Network requests from the dashboard (all data baked into `prisma_counts.json`).
- PRISMA flow diagram SVG (Phase 6 renders a structured table; an SVG diagram would be Phase 7 optional polish).

---

## 2 · File tree

```
Track 2/Task 3/Phase 6/
├── PHASE_6_PLAN.md
├── prisma_query.sql             # the one GROUP BY SQL
├── generate_dashboard.py        # Python: runs SQL → writes prisma_counts.json
├── ka_topic_proposer.html       # standalone dashboard
├── prisma_counts.json           # written at runtime (gitignored after generation)
└── test_generate_dashboard.py
```

---

## 3 · `prisma_query.sql` design

The PRISMA funnel must be reconstructible from one SQL query. The entire query runs in ≤ 100ms on the expected dataset size (~100–200 rows).

```sql
-- prisma_query.sql
-- Produces all PRISMA slot counts in a single pass over article_references.
-- Join to lifecycle_transitions only for abstract_source breakdown.

SELECT
    COUNT(*)                                        AS total_records_returned,

    -- Dedup counts
    COUNT(*) FILTER (WHERE triage_stage = 'duplicate')  AS duplicates_removed,

    -- Stage 1
    COUNT(*) FILTER (WHERE triage_stage NOT IN ('duplicate', 'metadata_only'))
                                                    AS stage1_survivors,
    COUNT(*) FILTER (WHERE triage_stage = 'rejected_stage1')
                                                    AS rejected_stage1,

    -- Stage 2A abstract
    COUNT(*) FILTER (WHERE abstract_text IS NOT NULL)
                                                    AS abstracts_collected,
    COUNT(*) FILTER (WHERE abstract_source = 'MISSING_ABSTRACT'
                       OR triage_stage = 'abstract_missing')
                                                    AS missing_abstract,

    -- Stage 2B triage decisions
    COUNT(*) FILTER (WHERE triage_decision IS NOT NULL)
                                                    AS screened_by_classifier,
    COUNT(*) FILTER (WHERE triage_decision = 'ACCEPT')
                                                    AS triage_accept,
    COUNT(*) FILTER (WHERE triage_decision = 'EDGE_CASE')
                                                    AS triage_edge_case,
    COUNT(*) FILTER (WHERE triage_decision = 'REJECT')
                                                    AS triage_reject,
    COUNT(*) FILTER (WHERE triage_decision = 'MISSING_ABSTRACT')
                                                    AS triage_missing_abstract,

    -- Stage 3 acquisition
    COUNT(*) FILTER (WHERE acquired_paper_id IS NOT NULL)
                                                    AS pdfs_acquired,
    COUNT(*) FILTER (WHERE triage_decision = 'ACCEPT'
                       AND acquired_paper_id IS NULL)
                                                    AS pending_acquisition,

    -- Abstract source breakdown (denormalised here; detailed view below)
    COUNT(*) FILTER (WHERE abstract_source = 'semantic_scholar')
                                                    AS abs_semantic_scholar,
    COUNT(*) FILTER (WHERE abstract_source = 'crossref')
                                                    AS abs_crossref,
    COUNT(*) FILTER (WHERE abstract_source = 'pubmed')
                                                    AS abs_pubmed,
    COUNT(*) FILTER (WHERE abstract_source = 'openalex')
                                                    AS abs_openalex,

    -- Discovery source breakdown
    COUNT(*) FILTER (WHERE discovered_via LIKE '%serpapi%')
                                                    AS disc_serpapi,
    COUNT(*) FILTER (WHERE discovered_via LIKE '%scholarly%')
                                                    AS disc_scholarly,
    COUNT(*) FILTER (WHERE discovered_via LIKE '%paperscraper%')
                                                    AS disc_paperscraper,
    COUNT(*) FILTER (WHERE discovered_via LIKE '%review_pdf%')
                                                    AS disc_review_pdf_extract

FROM article_references;
```

`FILTER (WHERE ...)` is SQLite-native syntax (SQLite ≥ 3.30.0, released 2019-10-04). No `CASE WHEN SUM(...)` workarounds needed.

---

## 4 · `generate_dashboard.py` contract

```python
def run_prisma_query(db_path: Path) -> dict:
    """Execute prisma_query.sql against db_path; return column→value dict."""

def write_prisma_counts(counts: dict, output_path: Path) -> None:
    """Write counts dict to output_path as indented JSON."""

def main(db_path: Path, output_path: Path) -> None:
    """Entry point: run query, write JSON, print summary to stdout."""
```

**CLI:**

```
python generate_dashboard.py \
  --db    ../../task3_pipeline_lifecycle.db \
  --out   prisma_counts.json
```

Exit 0 on success; prints human-readable summary table to stdout (e.g., "Records returned: 128, Duplicates: 12, ...").

---

## 5 · `prisma_counts.json` schema v1.0.0

```jsonc
{
  "schema_version": "1.0.0",
  "generated_at": "2026-05-27T20:00:00Z",
  "db_path": "...",
  "run_ids_included": ["RUN-2026-05-27-143022"],
  "prisma": {
    "gaps_targeted": 5,
    "queries_executed": 10,
    "total_records_returned": 128,
    "duplicates_removed": 12,
    "stage1_survivors": 116,
    "rejected_stage1": 3,
    "abstracts_collected": 95,
    "missing_abstract": 18,
    "screened_by_classifier": 113,
    "triage_accept": 34,
    "triage_edge_case": 28,
    "triage_reject": 51,
    "triage_missing_abstract": 18,
    "pdfs_acquired": 22,
    "pending_acquisition": 12
  },
  "breakdown": {
    "abstract_source": {
      "semantic_scholar": 52,
      "crossref": 21,
      "pubmed": 15,
      "openalex": 7,
      "MISSING_ABSTRACT": 18
    },
    "discovery_source": {
      "serpapi_scholar": 80,
      "scholarly_search": 30,
      "paperscraper_search": 10,
      "review_pdf_extract": 8
    }
  }
}
```

`run_ids_included` is populated by:
```sql
SELECT DISTINCT discovery_run_id FROM article_references;
```

`gaps_targeted` and `queries_executed` are hardcoded from Task 2 (5 priority gaps, 10 queries).

---

## 6 · `ka_topic_proposer.html` design

Single HTML file, no external CDN calls (all CSS and JS inline). Renders in any modern browser by opening the file locally.

### Layout (3 sections)

**Section 1 — PRISMA Funnel Table**

A bordered table with two columns: "PRISMA Stage" and "Count". Rows follow standard PRISMA 2020 order:
- Records returned from search
- Duplicates removed
- Records screened (Stage 1)
- Records excluded (Stage 1 reject)
- Abstracts sought
- Abstracts not retrieved (MISSING_ABSTRACT)
- Reports assessed for eligibility (Stage 2B)
- Reports classified ACCEPT
- Reports classified EDGE_CASE
- Reports classified REJECT
- PDFs acquired
- Pending acquisition

Each row has a left-border color bar: green for ACCEPT/acquired, yellow for EDGE_CASE/pending, red for excluded/rejected, grey for totals.

**Section 2 — Abstract Source Bar Chart**

Horizontal bar chart (inline SVG, no library). Five bars: Semantic Scholar, CrossRef, PubMed, OpenAlex, MISSING_ABSTRACT. Bars sized proportionally to count. Rendered with `<svg>` + `<rect>` elements via JS template literals.

**Section 3 — Discovery Source Pie / Donut**

Inline SVG donut chart of `discovery_source` counts (SerpAPI, scholarly, paperscraper, review_pdf_extract). Four segments, each labelled with source name and count. Computed entirely in vanilla JS using trigonometry (`Math.sin`, `Math.cos`).

### Data loading

```javascript
// inline in <script> tag at bottom of HTML
const PRISMA_DATA = /* INJECTED BY generate_dashboard.py */;
```

`generate_dashboard.py` injects `prisma_counts.json` content as a JS variable at HTML generation time, so the HTML is fully self-contained (no second file needed). The HTML template uses a `{{PRISMA_DATA}}` placeholder that the Python script replaces.

Alternatively, if the user opens the HTML directly alongside `prisma_counts.json`, the JS falls back to:
```javascript
fetch("prisma_counts.json").then(r => r.json()).then(render);
```

The inline injection approach is preferred (grader can open a single file).

---

## 7 · Success conditions (SC-1 through SC-10)

| # | Condition | Verified by |
|---|---|---|
| SC-1 | `prisma_query.sql` executes on `article_references` without error | `test_generate_dashboard.py::test_sql_executes_clean` |
| SC-2 | All 18 PRISMA-slot columns present in query result | `test_generate_dashboard.py::test_all_prisma_columns_present` |
| SC-3 | `duplicates_removed + stage1_survivors == total_records_returned` (or ≈ accounting for metadata_only rows still in pipeline) | `test_generate_dashboard.py::test_funnel_counts_coherent` |
| SC-4 | `triage_accept + triage_edge_case + triage_reject + triage_missing_abstract == screened_by_classifier` | `test_generate_dashboard.py::test_triage_decisions_sum_correctly` |
| SC-5 | `prisma_counts.json` schema-valid after `generate_dashboard.py` | `test_generate_dashboard.py::test_json_schema_valid` |
| SC-6 | `ka_topic_proposer.html` renders without JS errors (checked by opening in headless browser or static analysis) | `test_generate_dashboard.py::test_html_no_syntax_errors` |
| SC-7 | PRISMA funnel table rows appear in correct order | `test_generate_dashboard.py::test_html_funnel_row_order` |
| SC-8 | HTML is self-contained (no external URLs) | `test_generate_dashboard.py::test_html_no_external_urls` |
| SC-9 | `gaps_targeted = 5` and `queries_executed = 10` hardcoded from Task 2 | `test_generate_dashboard.py::test_task2_constants_present` |
| SC-10 | Dashboard reflects real DB state (no hardcoded counts; all values from SQL) | `test_generate_dashboard.py::test_counts_match_db_state` |

---

## 8 · Test plan (10 tests)

### `test_generate_dashboard.py` (10 tests)

| Test | What it verifies |
|---|---|
| `test_sql_executes_clean` | `prisma_query.sql` runs on a seeded in-memory SQLite DB without error |
| `test_all_prisma_columns_present` | Result dict has all 18+ expected keys |
| `test_funnel_counts_coherent` | `duplicates + survivors ≤ total` (allows metadata_only still in progress) |
| `test_triage_decisions_sum_correctly` | Four triage decisions sum to `screened_by_classifier` |
| `test_json_schema_valid` | Output JSON parses and has `schema_version`, `prisma`, `breakdown` keys |
| `test_html_no_syntax_errors` | `ka_topic_proposer.html` is valid HTML (check for unclosed tags via regex) |
| `test_html_funnel_row_order` | "Records returned" appears before "Duplicates removed" in HTML source |
| `test_html_no_external_urls` | No `http://` or `https://` URLs in `src=` or `href=` attributes |
| `test_task2_constants_present` | `prisma_counts.json` has `gaps_targeted = 5` and `queries_executed = 10` |
| `test_counts_match_db_state` | After seeding DB with known rows, JSON counts match expected values exactly |

---

## 9 · Effort estimate

| Sub-task | Hours |
|---|---|
| `prisma_query.sql` + verify on sample DB | 1.0 |
| `generate_dashboard.py` (SQL runner + JSON writer + CLI) | 1.5 |
| `ka_topic_proposer.html` (table + two charts, inline JS/CSS) | 3.0 |
| `test_generate_dashboard.py` (10 tests) | 1.5 |
| End-to-end smoke test (open HTML in browser) | 0.5 |
| **Total** | **~7.5 hr** |
