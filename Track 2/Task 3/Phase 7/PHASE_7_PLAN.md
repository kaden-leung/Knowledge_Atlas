# Track 2 · Task 3 · Phase 7 — Robust Submission Plan

**Author:** Kaden Leung  
**Updated:** 2026-06-02  
**Status:** Evidence-first execution plan  
**Purpose:** Maximize submission quality, rigor, visibility, and grader comprehension without inventing metrics or documenting unverified functionality.

---

## 0. One-line summary

Transform the submission from a strong but fragmented pipeline into a grader-visible, evidence-backed system story:

**gap-driven query generation -> retrieval -> triage -> acquisition readiness -> downstream handoff -> benchmarked evaluation -> honest limitations**

The central thesis every major artifact should support is:

> Evaluation showed that retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature.

This finding should be stated consistently across:

- `AUDIT_SUMMARY.md`
- `GRADER_GUIDE.md`
- `BENCHMARK_EVALUATION.md`
- `LESSONS_LEARNED.md`

---

## 1. Repository state verified on 2026-06-02

This plan is based on repository inspection, not assumptions.

### 1.0 Review context to preserve

- Task 2 is the strongest single contribution inside Knowledge Atlas, but it is still harder for a grader to discover and run than it should be.
- Task 3 is the strongest end-to-end pipeline story because it has the clearest evaluation, failure analysis, and traceability trail.
- The right move is not to invent more pipeline claims. The right move is to make the existing evidence easier to see, easier to run, and harder to misread.
- Task 2 is the source of search intent that drives the retrieval pipeline, so its value is architectural, not just procedural.

### 1.1 Verified strengths already present

- Task 2's query output is vendored into Task 3 at `inputs/query_results.json` (Task 2 ships as a separate submission, branch `track2/kaden-leung-task2`).
- Task 3 Phases 2-6 code exists, including search, DB loading, reference harvesting, Stage 1 triage, abstract collection, Stage 2B triage, PDF acquisition logic, and Phase 6 reporting.
- Evaluation artifacts already exist:
  - `Track 2/Task 3/TRACK2_EVALUATION_REPORT.md`
  - `Track 2/Task 3/EVALUATION_REPORT.md`
  - `Track 2/Task 3/CNFA_GOLD_STANDARD.md`
  - `Track 2/Task 3/HUMAN_VALIDATION.md`
  - `Track 2/Task 3/PIPELINE_ANALYSIS.md`
  - `Track 2/Task 3/PROVEIT_WORKS.md`
- Phase 5 dry-run evidence exists in `Track 2/Task 3/Phase 5/acquisition_report.json`.
- Setup validation already exists in `Track 2/Task 3/setup_verify.py`.
- `Track 2/Task 3/PROVEIT_WORKS.md` already proves one paper can be traced from gap source to ACCEPT.

### 1.2 Verified remaining gaps after current build

- No major Phase 7 grader-visibility artifact remains missing.

### 1.3 Phase 7 artifacts already completed

- `Track 2/Task 3/AUDIT_SUMMARY.md`
- `Track 2/Task 3/GRADER_GUIDE.md`
- `Track 2/Task 3/TRACK2_ARCHITECTURE.md`
- `Track 2/Task 3/RUBRIC_TRACEABILITY.md`
- `Track 2/Task 3/STAGE3_EVIDENCE_AUDIT.md`
- `Track 2/Task 3/FAILURE_ANALYSIS.md`
- `Track 2/Task 3/verify_track2_workflow.py`
- `Track 2/Task 3/Phase 7/ae_handoff.py`
- `Track 2/Task 3/Phase 7/ae_inbox_stub.py`
- `Track 2/Task 3/run_pipeline.py`
- `Track 2/Task 3/BENCHMARK_EVALUATION.md`
- `Track 2/Task 3/LESSONS_LEARNED.md`
- `Track 2/Task 3/inputs/query_results.json` (vendored Task 2 query output; Task 2 run guide ships with the Task 2 submission)

### 1.4 Important nuance

Task 2 visibility is **partially solved already** because the mirrored Phase 3 files exist in `Knowledge_Atlas`. The remaining visibility problem is not "copy more code"; it is "make the grader understand where to start and how Task 2 connects to Task 3 and evaluation."

---

## 2. Non-negotiable operating rules

1. Do not fabricate metrics, counts, recalls, precisions, or execution outcomes.
2. Do not document live Stage 3 or AE handoff behavior unless execution evidence exists.
3. Prefer improving discoverability of verified work before adding new infrastructure.
4. Use one authoritative benchmark document to avoid metric drift.
5. Any new document must cite its source artifacts by file path.
6. If a feature is only a stub or local validation layer, label it as a stub.

---

## 3. Phase 7 success definition

Phase 7 succeeds when a grader can do all of the following in under five minutes:

1. Understand the architecture and central finding.
2. See where Task 2 feeds Task 3.
3. Find the benchmark evidence and failure analysis.
4. Run one documented command for setup verification.
5. Run or inspect one end-to-end validation path.
6. See honest evidence for what is implemented, what is dry-run only, and what remains limited.
7. Find a rubric traceability matrix without hunting through multiple reports.

---

## 4. Execution order

This order is optimized for grading impact and dependency safety.

### Step 1 — Audit and freeze the source of truth

**Status:** Completed

**Goal:** Create a short audit artifact before any new claims are added.

**Deliverable:** `Track 2/Task 3/AUDIT_SUMMARY.md`

**Must include:**

- Existing strengths
- Existing evidence
- Missing rubric-critical pieces
- Missing visibility
- Recommended execution order

**Why first:** The repo already contains more functionality than the grader can easily see. The plan should branch from verified state, not memory.

**Exit criteria:**

- Every major claim is tied to an existing file, script, report, DB artifact, or output file.
- Missing items are explicitly labeled "not found" or "not yet measured."

---

### Step 2 — Submission navigation and reproducibility

**Status:** Completed

**Goal:** Make the existing work easy to discover and easy to run before adding new code.

**Deliverables:**

- `Track 2/Task 3/GRADER_GUIDE.md`
- `Track 2/Task 3/TRACK2_ARCHITECTURE.md`
- `Track 2/Task 3/RUBRIC_TRACEABILITY.md`
- `Track 2/Task 3/inputs/QUERY_PROVENANCE.md` (vendored Task 2 query output; Task 2 run guide ships with the Task 2 submission)
- If needed, one small Knowledge Atlas index file linking Task 2 -> Task 3 -> Evaluation

**What this step should do:**

- Point the grader to the best starting files.
- Explain the submission flow in one page.
- Explicitly say that Task 2's query output is vendored at `Track 2/Task 3/inputs/query_results.json` and Task 2 ships as a separate submission.
- Point to the benchmark authority, human validation, and end-to-end trace.
- Provide one documented command for Task 2 setup and execution.
- Provide one canonical validation command for Task 3 evidence checks.
- Include a demonstrated vs implemented matrix so overclaiming is hard.
- Include a rubric traceability matrix so graders can map requirements to evidence quickly.
- Include an ASCII architecture diagram so the Task 2 -> Task 3 flow is obvious at a glance.
- State explicitly why Task 2 matters: it supplies the search intent that shapes the retrieval pipeline.

**Important constraint:** Do not mirror more files into `Knowledge_Atlas` unless the audit shows a real discoverability gap. The mirror already exists; the next win is navigation plus one clean runnable path.

**Exit criteria:**

- A grader can open one guide and know exactly where to click next.
- The architecture file is flow-only, not discussion-heavy.
- The Task 2 command is documented in one place.
- The script sets the minimal required paths for the existing environment.
- If full portability is still not possible, the limitation is stated plainly.
- The canonical validation command exists and checks real evidence, not just syntax.
- The architecture document contains a readable diagram, not just prose.

---

### Step 4 — Stage 3 evidence decision gate

**Status:** Completed for documentation; live acquisition remains unverified

**Goal:** Separate what is already proven from what still needs live demonstration.

**Current evidence already present:**

- Phase 5 code exists.
- Phase 5 tests exist.
- `Phase 5/acquisition_report.json` shows dry-run acquisition outcomes.

**Open question:** Are there live lifecycle transitions for acquisition in the working DB state?

**Action sequence:**

1. Query the DB and lifecycle logs for real acquisition transitions.
2. If live Stage 3 evidence exists, document it.
3. If live Stage 3 evidence does not exist, perform a tightly bounded live demonstration on a very small sample.

**If a live mini-run is needed:**

- Use at most 1-2 ACCEPT rows.
- Log outcomes honestly, including failure outcomes.
- Treat a logged acquisition attempt as evidence of Stage 3 execution even if no PDF is successfully acquired.

**Deliverables:**

- Updated or new verification note for Stage 3 evidence
- Updated `PROVEIT_WORKS.md` if the traced paper advances into acquisition

**Exit criteria:**

- The submission can show either:
  - verified live acquisition transitions, or
  - an explicit statement that only dry-run evidence exists

---

### Step 5 — End-to-end downstream validation layer

**Status:** Completed for local validation

**Goal:** Close the system story from ACCEPT to downstream consumer readiness.

**Only implement these if still absent after the audit:**

- `Track 2/Task 3/Phase 7/ae_handoff.py`
- `Track 2/Task 3/Phase 7/ae_inbox_stub.py`
- `Track 2/Task 3/run_pipeline.py`
- `Track 2/Task 3/verify_track2_workflow.py`

**Implementation order within this step:**

1. `ae_handoff.py`
2. `ae_inbox_stub.py`
3. `verify_track2_workflow.py`
4. `run_pipeline.py`

**Why this order:** The verification story is stronger if the handoff and inbox validation exist before the one-command wrapper.

**Minimum requirements for `ae_handoff.py`:**

- Read only `ACCEPT` rows
- Validate required metadata
- Normalize DOI consistently with existing dedupe conventions
- Refuse rows missing required fields
- Write handoff artifacts deterministically
- Print a summary of written, skipped, and invalid rows

**Minimum requirements for `ae_inbox_stub.py`:**

- Read handoff artifacts
- Validate schema and required fields
- Validate DOI normalization
- Validate non-empty abstract
- Report valid vs invalid artifact counts

**Minimum requirements for `verify_track2_workflow.py`:**

- Base all checks on actual repo artifacts and DB state
- Output `CHAIN: X/X checks passed`
- Fail loudly on missing evidence

**Minimum requirements for `run_pipeline.py`:**

- Call real project components
- Support existing mock and live modes where already supported
- Do not hide step failures
- Serve as a wrapper, not a new pipeline implementation

**Exit criteria:**

- ACCEPT rows can be transformed into handoff artifacts
- Handoff artifacts can be validated by the inbox stub
- The chain verifier can prove end-to-end evidence using existing artifacts
- The validation command is a single obvious entry point for graders.

---

### Step 6 — Consolidate the evidence package

**Goal:** Replace scattered evidence with a coherent, non-duplicative documentation set.

**Authoritative benchmark source:**

- Make `TRACK2_EVALUATION_REPORT.md` the authoritative benchmark document by adding a hard declaration at the top and, if helpful, creating `BENCHMARK_EVALUATION.md` as a thin alias that points to it.

**Why:** A second independently maintained metric document creates drift risk.

**Required evidence-package docs:**

- `BENCHMARK_EVALUATION.md` or a clearly designated equivalent benchmark authority
- `FAILURE_ANALYSIS.md`
- `LESSONS_LEARNED.md`

**Recommended rule** *(superseded 2026-06-02 — see note below):*

- `TRACK2_EVALUATION_REPORT.md` is the single source of truth for recall, precision, ablation, and baseline comparisons.
- `BENCHMARK_EVALUATION.md` is a navigation alias that points to the authoritative report without duplicating metrics.
- Other docs may interpret those numbers, but not restate different versions.

> **Superseded:** authority was later split for clarity — `BENCHMARK_EVALUATION.md` is the authoritative source for metric **values** (it holds the metric table), and `TRACK2_EVALUATION_REPORT.md` is authoritative for **methodology**. They are complementary, not competing.

**What `FAILURE_ANALYSIS.md` should focus on:**

- Retrieval failures
- Query failures
- Classifier failures
- Abstract failures
- Metadata/data-quality failures
- What was fixed vs what remains limited

**What `LESSONS_LEARNED.md` should focus on:**

- What the pipeline taught about retrieval vs triage
- What changed after bug discovery
- Why evaluation changed the project story
- What would be improved next with more time

**Add a dedicated section called `What Changed Because of Evaluation`:**

This section should make the causal chain explicit:

| Discovery | Evidence | Action Taken |
|---|---|---|
| Retrieval recall lower than expected | Benchmark evaluation | Retrieval identified as the bottleneck |
| Architecture/architectural mismatch | Ablation study | Classifier keywords expanded |
| Corrupted abstract returned | Metadata audit | Plausibility checks added |
| Query failures observed | Search diagnostics | Query reformulation planned |

This is important because it shows measurement leading to system change, not just measurement leading to documentation.

**Add a dedicated section called `What Was Removed`:**

This should make explicit which assumptions the evaluation weakened or disproved.

Example:

- Retrieval was assumed to be strong; evaluation showed it was the main bottleneck.
- Classifier weakness was assumed to dominate; evaluation showed it was not the main source of misses.
- Query generation was assumed to be the key differentiator; evaluation showed query coverage mattered more than ranking fidelity.

**Exit criteria:**

- There is one obvious evaluation authority.
- The central thesis is visible without overclaiming.
- The evaluation story shows what changed and what was ruled out.

---

### Step 7 — Final alignment pass

**Goal:** Ensure the main documents agree and the grader sees one story.

**Files to reconcile:**

- `MANIFEST.md`
- `GRADER_GUIDE.md`
- `TRACK2_ARCHITECTURE.md`
- benchmark authority doc
- `FAILURE_ANALYSIS.md`
- `PROVEIT_WORKS.md`
- `HUMAN_VALIDATION.md`

**Checks:**

- No contradictory counts across docs
- Dry-run vs live execution clearly labeled
- Stub vs real integration clearly labeled
- Retrieval bottleneck claim supported consistently
- Benchmark authority is unambiguous and easy to identify quickly.

**Exit criteria:**

- The submission reads like one project, not several disconnected artifacts.

---

## 8. Required artifacts to build first

If we are actually moving forward, these are the highest-value files to create first:

1. `GRADER_GUIDE.md`
2. `TRACK2_ARCHITECTURE.md`
3. `RUBRIC_TRACEABILITY.md`
4. `AUDIT_SUMMARY.md`
5. `HOW_TO_RUN.md`
6. `run_gap_extraction.sh`
7. `verify_track2_workflow.py`

Reason:

- These artifacts reduce grader friction immediately.
- They make the already-implemented pipeline easier to verify.
- They prevent accidental overclaiming by forcing evidence mapping before new code.

---

## 9. Recommended verifier checks

If `verify_track2_workflow.py` is built, use only checks supported by actual evidence. A strong 8-check version would be:

1. Task 2 query output exists in both Track 2 and Knowledge Atlas mirrors
2. Search results artifact exists and is populated
3. `article_references` contains loaded candidates
4. Stage 1 lifecycle transitions exist
5. Stage 2A abstract collection evidence exists
6. `triage_decision='ACCEPT'` rows exist or are explicitly absent with explanation
7. Phase 5 evidence exists, either dry-run or live, and is labeled correctly
8. Handoff artifacts exist and pass inbox validation, if Phase 7 handoff is implemented

Do not hardcode counts unless those counts are re-derived from current artifacts at runtime.

---

## 10. Risks and controls

### Risk 1 — Writing too many new docs

**Control:** Prefer fewer documents with stronger authority. Reuse the strongest existing evaluation report instead of cloning its numbers.

### Risk 2 — Overclaiming Stage 3 or AE integration

**Control:** Label dry-run, stub, local validation, and live evidence separately.

### Risk 3 — Spending time on solved visibility problems

**Control:** Task 2 mirror already exists. Improve navigation, not duplication.

### Risk 4 — Wrapper scripts drift from real components

**Control:** `run_pipeline.py` should be a thin orchestrator over existing scripts, not a parallel implementation.

### Risk 5 — Metric drift across documents

**Control:** One authoritative benchmark file only.

---

## 11. Definition of done

The submission is ready when all of the following are true:

- An audit summary exists and reflects real repository state.
- The grader has a clear entry point and architecture overview.
- Task 2 has one documented runnable path.
- Stage 3 is honestly represented as live-demonstrated or dry-run-only.
- End-to-end validation exists through either real handoff scripts or an explicitly documented absence.
- Benchmark evidence, failure analysis, and lessons learned support one central finding.
- No major document contradicts another.
- A fresh grader can complete the checklist below without prior context.
- `TRACK2_EVALUATION_REPORT.md` is clearly marked as the authoritative benchmark source.

### Fresh Grader Test

- [ ] Find the entry point in under 60 seconds.
- [ ] Understand Task 2 -> Task 3 flow in under 3 minutes.
- [ ] Locate benchmark evidence in under 2 minutes.
- [ ] Verify setup using one documented command.
- [ ] Verify end-to-end evidence using one documented command.
- [ ] Identify known limitations without searching multiple documents.

---

## 12. What not to do

- Do not create a second benchmark report with independent numbers.
- Do not copy large amounts of code into `Knowledge_Atlas` unless the audit proves it is necessary.
- Do not claim real Article Eater integration if the downstream consumer is only a local stub.
- Do not run a broad live acquisition sweep merely to inflate evidence.
- Do not add flashy docs before the underlying evidence exists.

---

## 13. Immediate next actions

1. Write `AUDIT_SUMMARY.md`.
2. Build `GRADER_GUIDE.md` and `TRACK2_ARCHITECTURE.md`.
3. Add the Task 2 packaging wrapper and run documentation.
4. Check whether live Stage 3 transitions already exist before deciding on a mini-run.
5. Implement Phase 7 handoff and chain verification only after the visibility layer is in place.
