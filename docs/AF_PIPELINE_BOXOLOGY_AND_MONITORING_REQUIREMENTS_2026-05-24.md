# Article Finder Pipeline Boxology + Monitoring Requirements

**Date:** 2026-05-24
**Driving documents:**
- `docs/DEPENDENCY_OVERSEER_RUTHLESS_PANEL_REVIEW_2026-05-24.md` (panel review, Majors's observability gate)
- `docs/DEPENDENCY_OVERSEER_POST_PANEL_PAUSE_PLAN_2026-05-24.md` (pause plan §3 observability + §4 simulation)
- `docs/AF_PIPELINE_RECON_2026-04-27.md` (the existing AF reconnaissance)
- AF repo at `/Users/davidusa/REPOS/Article_Finder_v3_2_3/`

This document does two things. First, it diagrams Article Finder as a single pipeline with multiple entry points and a single Article-Eater handoff exit (the "boxology" DK asked for). Second, it traces what each of the six real-AF-activity tasks (A–F from the pause plan) would need a monitoring page to show, and converges those needs into one or two pages we can actually build.

The result is a requirements specification that gates the OVERSEER-OBSERVABILITY-LAYER work: the data the monitoring pages need to display IS the data the observability layer has to record.

---

## §1 — AF Today (admin surfaces that already exist)

AF already has a working Streamlit UI at `/Users/davidusa/REPOS/Article_Finder_v3_2_3/ui/`. The seven pages are:

| Page | Purpose | What it shows |
|------|---------|---------------|
| 1_dashboard | Corpus overview | Total / DOI / abstract / PDF / processed counts; 24-h efficiency (papers/hour, citations/hour, PDFs/hour); API health (OpenAlex, Crossref error rate + latency); status distribution |
| 2_search | Query the corpus | Search box, hit list |
| 3_triage | Triage queue | Pending-scorer items + manual triage actions |
| 4_paper | Per-paper detail | One row in depth (metadata, abstract, citations, AE handoff status) |
| 5_citations | Citation graph | Forward/backward citation view |
| 6_import | Import refs | CSV / RIS / Excel upload |
| 7_discovery | Discovery view | Bibliographer + OpenAlex/Crossref/SemScholar search status |

There is also a `stats` CLI subcommand. Running it 2026-05-24 returns: 10,000 search-paper sample (within a 16,257-paper corpus), 9,716 with DOI, 8,568 with abstract, 309 with PDF; status distribution candidate=16196 / pending_scorer=40 / processed_partial=3 / rejected=18.

**What AF's admin surface does NOT show, relative to the overseer's needs:**

- No view of `atlas_intake_decision` (the 754 papers that have been Atlas-decided are invisible on the dashboard — only `status` and DOI/abstract/PDF counts are surfaced).
- No view of `ae_corpus_match_status` (the 438 matched papers don't appear).
- No view of per-paper pipeline-stage trajectory (the dashboard is aggregate; there's no "show me where paper X is in the pipeline").
- No KA-side data at all (the overseer's article_finder_candidate artefacts, cross_db_sync_events, completion_queue items are unknown to AF's UI by design — AF is a peer system, not a subordinate).
- No reconciler activity stream (when did the overseer last sync; what did it do; what's pending).

The asymmetry is intentional: AF's UI shows what AF knows. The overseer's needs include AF state PLUS KA-side state PLUS the boundary between them.

---

## §2 — AF Pipeline Boxology

Multiple entry points feed a single pipeline. Once a reference or PDF is in `AF.papers`, the pipeline carries it through enrichment, triage, Atlas intake decision, PDF acquisition (if not already present), citation expansion, AE job build, AE handoff. AE processing happens outside AF. AE results flow back into AF, and a corpus-matching step writes the final state.

```
ENTRY POINTS                            STAGE 0
─────────────                           ──────────
  CSV/RIS/Excel  ─┐                  ┌──────────────┐
  reference list  │                  │              │
                  │                  │  AF.papers   │
  PDF directory  ─┼──── ingest ───►  │  row exists  │
  catalog         │                  │              │
                  │                  │  paper_id    │
  PDF inbox      ─┤                  │  doi/title   │
  watcher         │                  │  authors     │
                  │                  └──────┬───────┘
  Search          │                         │
  discovery       │                         │
  (OpenAlex,     ─┤                         │
  Crossref,       │                         ▼
  SemScholar)     │                  STAGE 1: METADATA ENRICHMENT
                  │                  ──────────────────────────
  Citation       ─┤                  enricher.py
  expansion       │                  ─ resolve DOI ↔ OpenAlex ID
                  │                  ─ fill venue, year, publisher
  Bibliographer  ─┤                  ─ retrieved_at, ingest_method
  (taxonomy)      │                         │
                  │                         ▼
  Zotero bridge  ─┘                  STAGE 2: ABSTRACT FETCH
                                     ────────────────────
                                     abstract_fetcher.py
                                     ─ try Crossref → OpenAlex → SemScholar → PubMed
                                     ─ abstract text + source recorded
                                            │
                                            ▼
                                     STAGE 3: TRIAGE SCORING
                                     ──────────────────────
                                     triage/classifier.py
                                     ─ triage_score (0..1)
                                     ─ triage_decision (accept/edge/reject)
                                     ─ triage_reasons (json)
                                     ─ off_topic_flag, off_topic_score
                                     ─ topic_score, topic_decision
                                            │
                                            ▼
                                     STAGE 4: ATLAS INTAKE DECISION
                                     ──────────────────────────────
                                     atlas_intake_decision is one of:
                                     ─ accept_candidate ─┐  PIPELINE CONTINUES
                                     ─ needs_pdf_text   ─┤  (gate: needs PDF, loops to Stage 5)
                                     ─ edge_case        ─┤  PARKED (manual review queue)
                                     ─ manual_review    ─┤  PARKED
                                     ─ reject_clear_*   ─┘  TERMINAL (excluded)
                                            │
                                            ▼  (accept_candidate path)
                                     STAGE 5: PDF ACQUIRED
                                     ─────────────────────
                                     pdf_downloader.py (Unpaywall) OR
                                     pdf_path already set from entry
                                     ─ pdf_path, pdf_sha256, pdf_bytes
                                            │
                                            ▼
                                     STAGE 6: CITATION EXPANSION
                                     ──────────────────────────
                                     citation_network.py
                                     ─ forward + backward via OpenAlex
                                     ─ writes citations table
                                            │
                                            ▼
                                     STAGE 7: AE JOB BUILD
                                     ─────────────────────
                                     eater_interface/job_bundle.py
                                     ─ ae_job_path set
                                     ─ ae_profile set
                                            │
                                            ▼
                                     STAGE 8: AE HANDOFF (EXIT FROM AF)
                                     ──────────────────────────────────
                                     eater_interface/invoker.py
                                     ─ ae_run_id set
                                     ─ ae_status = 'in_progress'
                                     ─ -- AF pipeline ends here --
                                            │
                                            ▼
                                     [ EXTERNAL: AE processing in
                                       Article_Eater_PostQuinean_v1_recovery ]
                                            │
                                            ▼
                                     STAGE 9: AE RESULT PARSED (re-enters AF)
                                     ─────────────────────────────────────
                                     eater_interface/output_parser.py
                                     ─ ae_n_claims, ae_n_rules, ae_confidence
                                     ─ ae_warnings
                                            │
                                            ▼
                                     STAGE 10: CORPUS MATCHING
                                     ─────────────────────────
                                     deduplicator.py / PDFMatcher
                                     ─ ae_corpus_match_status:
                                       matched / unmatched / ambiguous
                                     ─ ae_corpus_match_paper_id (KA paper_id)
                                            │
                                            ▼
                                     STAGE 11: FINAL STATUS
                                     ──────────────────────
                                     status = 'processed_partial' or terminal


OVERSEER RECONCILER (KA-side, async — runs against AF read-only)
────────────────────────────────────────────────────────────────
  Tick reads AF.papers WHERE atlas_intake_decision='accept_candidate'
    [754 papers as of 2026-05-24]
  ├─ For each: register article_finder_candidate artefact in KA
  ├─ Insert cross_db_sync_events row with status='pending'
  ├─ If a paired KA article_epistemic_record exists → upgrade to 'matched'
  └─ If AF signature drifts vs prior tick → status='unresolved'
                                          + blocking completion_queue row
```

**Entry point uniqueness.** Even though there are seven entry paths, every entry produces an AF.papers row, and from there the pipeline is single-track until Stage 8 (AE handoff). Stage 4's branch into edge_case / manual_review / reject is the only place a paper can leave the main track without reaching AE. The user's intuition is correct: once a reference exists, the pipeline is supposed to drive it forward.

**Where the gates actually are.** Three places where a paper can stall:

1. After Stage 1 (no abstract retrievable) → stuck at Stage 2 indefinitely
2. After Stage 4 (atlas_intake_decision = edge_case or manual_review) → parked for human attention
3. After Stage 5 (PDF not retrievable) → atlas_intake_decision was `needs_pdf_text`, loops here

**Where AF's existing dashboard sees vs. doesn't see**:

- Stages 0–3: visible (status distribution, abstract counts, triage state).
- Stage 4: invisible to AF's dashboard (the `atlas_intake_decision` field is not surfaced).
- Stages 5–8: PDF counts visible, AE handoff visible per-paper but not in aggregate.
- Stages 9–11: AE-side state visible per-paper, corpus-match status not aggregated.

The overseer's view is orthogonal to AF's: AF sees its own internal pipeline; the overseer sees the cross-boundary state between AF and KA.

---

## §3 — Per-Task Monitoring Requirements

Each of the six tasks from the pause plan §4.6 generates an observable state change that a monitoring page would have to surface. Working backward from each task gives the page requirements.

### Task A — Flip 5–10 papers to `atlas_intake_decision='accept_candidate'`

What the page must show:

1. **Stage 4 distribution histogram**: count of papers per atlas_intake_decision value. After Task A, this count goes up by 5–10. Without this widget Task A is invisible.
2. **Recent intake decisions (last 24h, last 7d)**: which papers had atlas_intake_decision set or changed.
3. **For each accept_candidate paper, reconciler status**: did the overseer pick it up (Y/N)? Time since AF write → KA sync? If pending > N seconds, alert.
4. **Funnel from Stage 4 → reconciler → KA-side article_finder_candidate**: count at each step. If 754 accept_candidate exist but only 3 article_finder_candidate artefacts exist in KA, that's a 751-paper backlog. Currently invisible.

### Task B — Re-run AF's corpus matcher

What the page must show:

1. **Stage 10 distribution histogram**: matched / unmatched / ambiguous counts. After Task B, the matched count grows.
2. **Recent matcher activity**: count of papers whose ae_corpus_match_status changed in the last 24h.
3. **Ambiguous papers list**: these are the human-attention items — table with paper_id, ae_corpus_match_status, ae_corpus_match_candidates_json (multiple candidate KA paper_ids).
4. **Per-source matching evidence**: ae_corpus_match_basis distribution (DOI match / title match / hash match / etc.) — surfaces the empirical quality of the matcher.

### Task C — Run AF's discovery_orchestrator on a fresh topic

What the page must show:

1. **Entry-point activity stream**: papers ingested per hour, broken down by ingest_method (search, citation_expansion, manual_import). After Task C, search-driven entries spike.
2. **New-candidate rate over time**: a sparkline of last-N-hours candidate-arrival count.
3. **Source attribution**: how many papers came from OpenAlex vs. Crossref vs. SemScholar (data in `source` column of AF.papers).
4. **New candidates' Stage 4 trajectory**: of the new candidates from Task C, how many reached accept_candidate? edge_case? reject?

### Task D — Drop PDFs into AF's inbox

What the page must show:

1. **Stage 5 count + recent rate**: papers with pdf_path set, papers acquiring PDFs per hour.
2. **PDF inbox queue depth**: how many PDFs in the watched folder are unprocessed (requires reading the inbox folder, not just AF.papers).
3. **OCR queue depth**: papers at atlas_intake_decision='needs_pdf_text' waiting for OCR/text extraction.

### Task E — Run AF's discovery_orchestrator end-to-end on a research question

What the page must show:

1. **Per-topic pipeline funnel**: for a given topic (atlas_primary_topic), how many papers at each Stage (0–11). A research question producing 200 candidates flowing to 80 accept_candidate flowing to 40 PDF-retrieved flowing to 30 AE-handed-off flowing to 20 corpus-matched is the kind of view that tells you whether the topic is healthy.
2. **Topic candidate list with current stage**: sortable / filterable.
3. **Topic-vs-rest comparison**: rate this topic processes vs. the corpus average.

### Task F — Drift a title in AF.papers on an already-synced paper

What the page must show:

1. **Recent signature-drift events**: from reconciler_event_log, papers whose AF signature changed and the overseer flagged as unresolved. Each row: paper_id, prior_signature, new_signature, age of unresolved status, severity of the resulting completion_queue row.
2. **Unresolved sync events list**: count + list (sortable by age).
3. **Blocking completion_queue items**: count + list. Task F should produce exactly one new blocking item; the monitoring page should make that visible.

### Common requirements across A–F

Every task needs the page to support:

- **Drill-down from aggregate to per-paper**: clicking a count opens the list; clicking a paper opens its per-paper trajectory.
- **Time windows**: last hour / last 24h / last 7d / last 30d — most rate widgets need these.
- **Refresh latency disclosure**: "as of HH:MM:SS, N seconds ago." Without this, the operator doesn't know whether the dashboard is stale.
- **Auto-refresh**: every 30s or 60s. Manual refresh button as fallback.

---

## §4 — Two Monitoring Pages

The requirements consolidate cleanly into two pages.

### Page 1 — AF→KA Pipeline Flow

A single-page funnel/sankey view of the boxology in §2, with live counts at each stage and rate widgets where appropriate. Drill-down on every count.

**Layout (top to bottom):**

1. **Header strip** with refresh-latency disclosure ("as of 14:23:45 PT, 12 seconds ago"), auto-refresh toggle, time-window selector (last 24h / 7d / 30d / all-time).
2. **Boxology with live counts**, rendered as a vertical funnel. Each box: stage name + total count + recent rate (e.g., `Stage 4 — Atlas intake decided: 17,255 papers • +12 in last 24h`). The Stage 4 box opens to show the 5-way atlas_intake_decision distribution.
3. **Reconciler bridge widget** between Stage 4 and Stage 9: count of accept_candidate papers (AF-side), count of article_finder_candidate artefacts (KA-side), the gap (how many AF papers are reconcilable but not yet reconciled), oldest unreconciled (with age).
4. **Stage 10 sub-widget**: matched / unmatched / ambiguous breakdown with click-to-list.
5. **Source attribution sub-widget**: where did the new papers in the last window come from (OpenAlex / Crossref / SemScholar / manual / Zotero / citation_expansion).
6. **Stuck-paper detector**: papers parked at edge_case / manual_review / needs_pdf_text for > N days. List sortable by age.

**Tasks this page supports:**

- A (Stage 4 histogram, reconciler bridge widget shows the gap close)
- B (Stage 10 sub-widget)
- C (entry-point activity, source attribution, new-candidate rate)
- D (Stage 5 count + recent rate; OCR queue depth)
- E (per-topic funnel — filter by atlas_primary_topic; pipeline funnel scoped to that topic)

### Page 2 — Overseer Health & Activity

A monitoring view of overseer state (KA-side). Reconciler ticks, verifier runs, drift events, completion queue.

**Layout (top to bottom):**

1. **Header strip** identical to Page 1 (refresh disclosure, auto-refresh, time window).
2. **Verifier health**: pass/fail status of each of the 17 strict-verifier checks; "last passed at" timestamp per check; spark line showing pass/fail over the time window. Requires `verifier_run_history` table.
3. **Reconciler activity**: tick count over time window; per-action breakdown (inserted_pending, upgraded_to_matched, flagged_unresolved, skipped_already_matched); oldest pending sync event (with age). Requires `reconciler_event_log` table.
4. **Signature drift events**: list of cross_db_sync_events with status='unresolved'; per-row: paper_id, when_flagged, age, severity of paired completion_queue item.
5. **Completion queue triage**: open items by severity; oldest item per severity; growth-rate sparkline (depth over time). Requires querying `completion_queue` directly.
6. **Stale artefacts**: count and list of active artefacts with freshness_status='stale'.
7. **Quarantined queue items**: rebuild_queue rows at state='quarantine' — count + list.

**Tasks this page supports:**

- A (reconciler activity shows the new pending events; signature drift list is empty initially)
- F (signature drift events list grows by 1; blocking completion_queue widget reflects the new item)
- All operational tasks (verifier health, completion queue triage)

### Optional Page 3 — Per-Paper Trajectory (drill-down)

When the operator clicks a paper_id on Page 1 or Page 2, this is the detail view: every stage's data for that paper, plus its KA-side state.

- AF.papers full row (collapsed JSON with expand-on-click).
- Pipeline trajectory: each of Stages 0–11 with timestamp + relevant field values.
- KA-side state: registered as article_finder_candidate? Has article_epistemic_record? cross_db_sync_events history? completion_queue history?
- Reconciler events for this paper (from reconciler_event_log).

This page is built only after Pages 1 and 2 are useful enough to demand drill-down.

---

## §5 — Data Sources the Pages Need

This is the requirements specification for the OVERSEER-OBSERVABILITY-LAYER work.

### From AF.papers (read-only)

The overseer's connector already reads AF.papers. Additional columns to expose via `iter_papers()` for the monitoring pages:

- `atlas_intake_decision` (currently not in `ArticleFinderPaper` dataclass; add)
- `atlas_primary_topic` (for per-topic filtering)
- `ae_corpus_match_status`, `ae_corpus_match_paper_id`, `ae_corpus_match_basis` (for Stage 10 widgets)
- `pdf_path`, `pdf_sha256` (Stage 5 sub-widget)
- `ae_run_id`, `ae_status` (Stage 8 widget)
- `source`, `ingest_method`, `created_at`, `updated_at` (entry-point attribution; rate widgets)

A single `paper_stage_view(af_paper) -> dict` function computes which stage each paper is at (0–11) based on the columns above. This is the join key between AF data and pipeline-stage widgets.

### From overseer lifecycle DB (read-write)

- `cross_db_sync_events` — Page 2 widgets 3 + 4 (already exists, populated).
- `artefact_registry` (kind='article_finder_candidate') — Page 1 reconciler bridge widget (already exists, populated).
- `completion_queue` — Page 2 widget 5 (already exists, populated).
- `rebuild_queue` (state='quarantine') — Page 2 widget 7 (already exists, populated).
- `verifier_run_history` — **NEW table required**. Page 2 widget 2 needs this. Records each verify_strict() run timestamp + per-check status + failure JSON.
- `reconciler_event_log` — **NEW table required**. Page 2 widget 3, Page 1 reconciler bridge widget need this. Records each reconciler tick's actions per paper.

### Compute-on-demand (no storage needed)

- Stage 4 atlas_intake_decision histogram (group-by query against AF.papers each refresh).
- Stage 10 ae_corpus_match_status histogram (same).
- Source attribution (same).
- Stuck-paper detector (group-by atlas_intake_decision + date arithmetic).

Computing on demand is fine at AF's 16,257-row scale; precomputed aggregation tables aren't needed yet.

### Net new infrastructure for the monitoring pages

Just two tables (`verifier_run_history`, `reconciler_event_log`) and the recording-at-call-sites code that populates them. Everything else is queryable from existing tables.

This is the OVERSEER-OBSERVABILITY-LAYER scope, now justified by what Pages 1 and 2 require rather than by abstract observability principles.

---

## §6 — Implementation: Tech Choice

Three options:

**Option A — Streamlit app at the KA repo level.** Reads AF DB read-only via the existing `connect_readonly()`, reads KA lifecycle DB read-write via the existing `connect()`. New file `ka_overseer_dashboard.py` (Streamlit). Pros: matches AF's existing UI tech; multipage support is native to Streamlit. Cons: requires `streamlit run` to serve.

**Option B — Static HTML pages backed by JSON snapshots.** A periodic script writes a JSON file (`data/ka_payloads/overseer_dashboard.json`) and a static HTML at `160sp/ka_overseer_dashboard.html` renders it. Pros: no server needed; can be served from the same static infrastructure as existing 160sp pages. Cons: more JS to write; no auto-refresh without polling.

**Option C — CLI tool.** `python3 scripts/dependency_overseer_dashboard_report.py` prints a text/markdown report. Pros: trivial to write; no UI. Cons: not a page, doesn't drill down, no auto-refresh.

**Recommendation: Option A (Streamlit).** AF is already using it; the team already knows it; multipage + auto-refresh + drill-down come essentially for free. The build cost is ~400 lines of Python + the two new observability tables. Option B becomes interesting if you want the pages publicly viewable; for an admin-only surface, Streamlit is right.

---

## §7 — What This Lets You Actually Do

Once Pages 1 + 2 ship:

- **Task A becomes verifiable.** You flip 5–10 papers' atlas_intake_decision in AF; you watch Page 1's Stage 4 histogram grow; you wait one reconciler tick (≤60s); you watch the reconciler bridge widget close the gap; you watch Page 2's reconciler-activity widget log 5–10 inserted_pending events. End-to-end visible in 90 seconds.
- **Task F becomes verifiable.** You manually edit a title in AF.papers on an already-synced paper; one reconciler tick later, Page 2's signature-drift widget shows a new unresolved event and Page 2's completion-queue widget shows a new blocking row. Two minutes total.
- **Tasks B/C/D/E become observable as ongoing activity.** Whatever you do in AF — re-running the matcher, running discovery, dropping PDFs in the inbox — surfaces in the rate widgets and source-attribution widget on Page 1.
- **The 90-day operational window becomes meaningful.** Pages 1 + 2 produce data the panel asked for (Majors's observability gate, Akidau's late-data visibility, Fournier's operational signal).
- **Phase 3's case is empirical, not speculative.** When the 90 days are up, you can show graphs of AF-pipeline rate vs. overseer-reconciler lag vs. completion_queue depth, and make a data-grounded decision about whether to resume Phase 3 or kill it.

---

## §8 — Build Order (the new immediate plan)

1. **Land `verifier_run_history` + `reconciler_event_log` migration + recording code** (1 commit, ~300 lines). This unblocks Page 2.
2. **Switch reconciler criterion** from `processed_partial` to `atlas_intake_decision='accept_candidate'` (OVERSEER-AF-CRITERION-SWITCH; 1 commit, ~50 lines). Lets Page 1 reconciler-bridge widget show real movement.
3. **Build Page 1 (AF→KA Pipeline Flow) as Streamlit** (1 commit, ~300 lines). Includes boxology funnel, reconciler bridge, source attribution, stuck-paper detector.
4. **Build Page 2 (Overseer Health & Activity) as Streamlit** (1 commit, ~250 lines). Includes verifier health, reconciler activity, drift events, completion-queue triage.
5. **Smoke test against live data**: run reconciler tick, watch Pages 1 and 2 reflect the result.
6. **Write the runbook** (`docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md`) anchored on what Pages 1+2 show (1 commit, ~200 lines).
7. **Operate for ≥30 days** before any Phase 3 conversation.

This replaces the prior "build the observability tables" plan with a "build the pages that need the tables" plan — same destination, but the pages drive the schema rather than the schema driving the imaginary pages.

---

## §9 — Open questions for DK

1. **Streamlit or static HTML?** I recommend Streamlit; you may prefer static for deployability reasons.
2. **Where should the pages live in the repo?** Options: top-level `ka_overseer_dashboard.py` (matches existing `ka_*.py` flat-module convention) or `admin_ui/dashboard.py` (a new subdirectory). Recommend the flat-module convention.
3. **What's an acceptable refresh cadence?** Recommend 30s default with manual refresh button. Real cost is the AF read (≤1s on 16,257 rows) plus the KA reads (≤1s on the lifecycle DB).
4. **For the boxology funnel specifically — sankey/proper-funnel/plain-vertical?** Plotly's sankey is rich but heavier; a plain vertical funnel with counts is honest and fast. Recommend the plain vertical funnel; sankey later if you want the cross-flow detail.

Decide on these and I'll proceed with the build order in §8.
