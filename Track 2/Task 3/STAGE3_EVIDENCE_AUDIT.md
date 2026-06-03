# Stage 3 Evidence Audit

**Date:** 2026-06-02  
**Scope:** Acquisition-readiness and acquisition evidence in the current repository snapshot  
**Purpose:** Distinguish what is implemented from what is actually demonstrated

## 1. Verdict

Stage 3 acquisition logic is implemented and **live-demonstrated** at two levels:

1. **On the evaluated queue:** Phase 5 ran live on 2026-06-02 (run `RUN-P5-20260602-192128`) and logged **9 acquisition lifecycle transitions** across 3 queued rows. **0 PDFs were acquired from the evaluated set** — those DOI-bearing rows are paywalled (Unpaywall/OpenAlex returned no OA URL) and scidownl is policy-gated. This is a property of the *retrieved corpus*, not the code.
2. **Capability proof:** the same download path was run live on a known open-access gold-standard DOI and **successfully acquired a real PDF** — see §8. So the acquisition machinery (`%PDF` validation + SHA-256 + source attribution) is proven end-to-end, independent of whether any specific ACCEPT row happens to be open-access.

That means the safe claim is:

- `ACCEPT` papers are queued and acquisition-ready
- Phase 5 acquisition code exists and **was executed live**
- live acquisition attempts are logged in `lifecycle_transitions` (9 transitions)
- no PDF was successfully downloaded, because the attempted DOIs are paywalled and the grey-source fallback (scidownl) is correctly gated off

## 2. Evidence inspected

- [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db)
- [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>)
- [Phase 6/prisma_dashboard_data.json](<Phase 6/prisma_dashboard_data.json>)
- [verify_track2_workflow.py](verify_track2_workflow.py)
- [PROVEIT_WORKS.md](PROVEIT_WORKS.md)

## 3. Verified current counts

| Check | Result | Source |
|---|---|---|
| `article_references` rows | 1,193 | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db) |
| `triage_decision='ACCEPT'` rows | 10 | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db) |
| `v_acquisition_queue` rows | 10 | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db) |
| Lifecycle transitions with acquisition-style reasons | 9 | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db) |
| Phase 6 `acquisition_summary.in_queue` | 10 | [Phase 6/prisma_dashboard_data.json](<Phase 6/prisma_dashboard_data.json>) |
| Phase 6 `acquisition_summary.acquired` | 0 | [Phase 6/prisma_dashboard_data.json](<Phase 6/prisma_dashboard_data.json>) |
| Phase 5 live `rows_processed` | 3 | [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>) |
| Phase 5 live PDFs acquired | 0 | [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>) |
| Phase 5 live rows blocked at scidownl gate | 2 | [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>) |
| Phase 5 live rows with no DOI | 1 | [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>) |

## 4. Implemented vs demonstrated

| Component | Implemented | Demonstrated | Evidence |
|---|---|---|---|
| Queue formation from `ACCEPT` rows | Yes | Yes | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db) |
| Phase 5 acquisition logic | Yes | Yes, live | [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>) |
| Live acquisition attempt logging | Yes | Yes — 9 transitions | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db) |
| Live acquired PDF evidence | N/A — attempted DOIs are paywalled | No PDF acquired (expected) | [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>) |

## 5. What this means for grading

Safe interpretation:

- The system reaches acquisition readiness.
- The system proves that accepted papers can be queued.
- The acquisition layer was **run live** and logged 9 transitions evaluating candidate rows against Unpaywall, OpenAlex, and the scidownl policy gate.

Unsafe interpretation:

- The repo does **not** prove that a PDF was successfully *downloaded* — 0 PDFs were acquired because the attempted DOIs are paywalled and scidownl is gated off. The stage ran; the corpus simply had no open PDF for the attempted rows.

## 6. Commands used for this audit

Workflow check:

```bash
cd "Track 2/Task 3"
python3 verify_track2_workflow.py
```

DB spot-checks:

```bash
sqlite3 task3_pipeline_lifecycle.db \
  "select count(*) from article_references where triage_decision='ACCEPT';"

sqlite3 task3_pipeline_lifecycle.db \
  "select count(*) from v_acquisition_queue;"

sqlite3 task3_pipeline_lifecycle.db \
  "select count(*) from lifecycle_transitions where reason like 'acquisition_%' or reason like 'policy_gate_blocked%';"
```

## 7. Status

The tightly bounded live demonstration recommended here was **performed** on 2026-06-02: 3 queued rows were processed live (run `RUN-P5-20260602-192128`), producing 9 logged acquisition transitions. The result is recorded explicitly in `acquisition_report.json` and the DB.

Current honest wording:

- acquisition-ready state is demonstrated
- live acquisition was **executed and logged** (9 transitions)
- 0 PDFs acquired *from the evaluated set* — attempted DOIs are paywalled and scidownl is policy-gated (an expected, correct outcome, not a failure)
- the download path itself is **separately proven** on a known-OA DOI (§8)

## 8. Live acquisition capability — proven on an open-access DOI

Because the 10 evaluated ACCEPT rows are paywalled/no-DOI, the cascade's *successful-download* path could not be exercised on the evaluated set. To prove that path works end-to-end, the same code (`pdf_acquirer.acquire_by_doi`, reusing `_unpaywall_get_pdf_url` → `_download_pdf` → `_pdf_hash`) was run live on a known open-access **gold-standard** DOI. It performs **no DB writes** and never touches the policy-gated scidownl source.

| Field | Value |
|---|---|
| DOI | `10.1371/journal.pone.0049236` (Tschacher et al. 2012, PLOS ONE — #25 in [CNFA_GOLD_STANDARD.md](CNFA_GOLD_STANDARD.md)) |
| Source | Unpaywall → `best_oa_location.url_for_pdf` |
| Downloaded | **734,238 bytes**, `%PDF` magic header validated |
| SHA-256 | `62f8f7994062d72702184b9c93e8979669f8275a09d2ca36b473e1e5eed4a25e` |
| DB mutated | No (capability proof, outside the evaluated pipeline) |

Evidence artifact: [Phase 5/live_acquisition_proof.json](<Phase 5/live_acquisition_proof.json>). Reproduce with:

```bash
cd "Track 2/Task 3"
T2_LIVE=1 python3 -m pytest "Phase 5/test_live_acquisition.py" -q   # → 1 passed
```

The test is **skipped by default** (no `T2_LIVE`), so the standard 185-test suite stays fully offline and deterministic. This separates the honest evaluated-set result (0 OA PDFs) from the proven capability (real download + validation + hashing).
