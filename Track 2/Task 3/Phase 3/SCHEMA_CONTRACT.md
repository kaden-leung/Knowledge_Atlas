# Schema Contract — `article_references` + `lifecycle_transitions`

**Track 2 · Task 3 · Phase 3**
**Author:** Kaden Leung
**Contract Version:** 1.0.0
**Last Updated:** 2026-05-28
**Output Schema Version:** 1.0.0

---

## 1. System Summary

`article_references` is the candidate buffer between harvesters (Phase 2 + the review-PDF reference harvester) and the triage funnel (Phase 4). Every paper the system knows about — but does not yet have a PDF for — lives here as exactly one row. `lifecycle_transitions` is the audit log: every state change on an `article_references` row writes one row here, attributed to a named writer.

This contract is the single source of truth that Phases 4 and 5 read against. Phase 3's two writers — `db_loader.py` (Phase 2 → DB) and `reference_harvester.py` (PDFs → DB) — both go through one shared mutation path: `insert_or_dedupe_reference()` in `dedupe.py`.

The grader's check: every harvested candidate must be inserted (or deduplicated against an existing row) before any later phase touches it. **Free-floating outputs do not count.** A `search_results.json` row that doesn't make it into the DB is invisible to the rest of the pipeline.

---

## 2. Inputs

### 2.1 From Phase 2 (`db_loader.py`)

A `search_results.json` file conforming to the [Phase 2 JSON Schema](../Phase%202/schema/search_results.schema.json) (schema version 1.1.0). The loader reads the `results` array; each element becomes one call to `insert_or_dedupe_reference()`.

### 2.2 From PDF directories (`reference_harvester.py`)

Configurable directory paths containing review PDFs. Defaults: `Part 2 Pdfs/` (5 PDFs) and `Part_One_10pdfs/` (10 PDFs). Each PDF is opened with `pdfplumber`, its references section is located, and each parsed reference line becomes one call to `insert_or_dedupe_reference()`.

### 2.3 Configuration

| Parameter | Default | Meaning |
|---|---|---|
| `db_path` | `Track 2/Task 3/task3_pipeline_lifecycle.db` | Local DB (source of truth) |
| `shared_snapshot_path` | `Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db` | Materialized snapshot (gitignored) |
| `run_id` | inherits from input | Stamped on every row inserted in this run |
| `corpus_snapshot_csv` | `pdf_identity_inventory_local.csv` | Stub for existing-corpus dedupe (empty on this machine) |
| `title_jaccard_threshold` | `0.92` | Conservative; merges only when ≥92% of tokens overlap |
| `dry_run` | `False` | Plan inserts in `:memory:`; no real DB write |

---

## 3. Processing

The two writers each follow this flow:

1. **Apply migrations.** Idempotent — `apply_migrations(db_path)` creates the schema on first run, no-ops on subsequent runs.
2. **Read input** (JSON for `db_loader`, PDFs for `reference_harvester`).
3. **Open a single SQLite transaction** (`BEGIN IMMEDIATE`).
4. **For each candidate**, call `insert_or_dedupe_reference(candidate, conn, run_id, created_by=<writer>)`. The dedupe path is the **only** mutation path — direct `INSERT` is forbidden by convention and verified by `test_no_direct_insert`.
5. **Commit** (or rollback if `--dry-run`).
6. **Materialize shared snapshot** (db_loader only, end-of-run): `VACUUM INTO '<shared_snapshot_path>'` produces a byte-identical copy at the course-spec path. The shared path is gitignored — never written to during normal operation.
7. **Write audit JSON** (`db_load_report.json` or `reference_harvest_results.json`).

### 3.1 Determinism

For a fixed set of inputs run in the same order on the same calendar date, two reruns produce identical row counts, identical `reference_id` values, identical `discovered_via` strings, and identical row content. (`created_at`/`updated_at`/`at` timestamps will differ — they are wall-clock and excluded from equality.)

### 3.2 Idempotency

Running `db_loader.py` twice against the same `search_results.json` is a no-op the second time: the DOI-exact-match branch fires for every row, no new rows are inserted, and `discovered_via` does not grow because the writer's `discovered_via` value is already present in every row.

---

## 4. Outputs

### 4.1 `article_references` row

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| `reference_id` | TEXT (PK) | NOT NULL | `REF-YYYY-MM-DD-NNNNNN` |
| `doi` | TEXT | NULLABLE | Normalised, lowercased, no URL prefix. Unique among non-null values (partial unique index). |
| `title_raw` | TEXT | NOT NULL | Verbatim title (may be `""` for unparseable PDF lines, in which case `raw_citation` is mandatory) |
| `title_normalized` | TEXT | NOT NULL | Lowercased, punctuation-stripped title |
| `first_author_surname` | TEXT | NULLABLE | Best-effort surname extraction |
| `publication_year` | INTEGER | NULLABLE | Year |
| `venue` | TEXT | NULLABLE | Journal / venue |
| `raw_citation` | TEXT | NULLABLE | The full messy reference-list line (PDF harvester only) |
| `snippet` | TEXT | NULLABLE | SerpAPI snippet (search runner only) |
| `discovered_via` | TEXT | NOT NULL | Comma-joined sorted unique enum values; see §5 |
| `discovered_from_paper_id` | TEXT | NULLABLE | Filename-derived ID of the source PDF (review harvester only) |
| `discovered_query` | TEXT | NULLABLE | The boolean query string (search runner only) |
| `discovery_run_id` | TEXT | NOT NULL | The run that first created this row |
| `discovered_at` | TEXT | NOT NULL | `YYYY-MM-DDTHH:MM:SSZ` |
| `triage_stage` | TEXT | NOT NULL | Default `'metadata_only'`; see §7 stage enum |
| `triage_decision` | TEXT | NULLABLE | Default NULL until Phase 4 sets it |
| `triage_reason` | TEXT | NULLABLE | Free-form reason; set by Phase 4 |
| `abstract_text` | TEXT | NULLABLE | Phase 4 fills |
| `abstract_source` | TEXT | NULLABLE | Phase 4 fills |
| `classifier_confidence` | REAL | NULLABLE | Phase 4 fills |
| `voi_score` | REAL | NULLABLE | Passthrough from Phase 2 input |
| `pdf_acquisition_attempts` | INTEGER | NOT NULL, DEFAULT 0 | Phase 5 fills |
| `pdf_acquisition_last_source` | TEXT | NULLABLE | Phase 5 fills |
| `acquired_paper_id` | TEXT | NULLABLE | Phase 5 fills |
| `created_at` | TEXT | NOT NULL | Auto |
| `updated_at` | TEXT | NOT NULL | Auto on mutation |

### 4.2 `lifecycle_transitions` row

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| `transition_id` | INTEGER (PK, AUTOINCREMENT) | NOT NULL | |
| `reference_id` | TEXT | NOT NULL | FK to `article_references.reference_id`, ON DELETE CASCADE |
| `run_id` | TEXT | NOT NULL | The run that caused this transition |
| `from_stage` | TEXT | NULLABLE | NULL on initial insert |
| `to_stage` | TEXT | NOT NULL | New `triage_stage` value |
| `reason` | TEXT | NOT NULL | Short token; see §6 enum |
| `created_by` | TEXT | NOT NULL | Writer name; see §7 enum |
| `at` | TEXT | NOT NULL | `YYYY-MM-DDTHH:MM:SSZ` |

### 4.3 `v_acquisition_queue` view (read-only)

```sql
SELECT reference_id, doi, title_raw, voi_score,
       pdf_acquisition_attempts, pdf_acquisition_last_source,
       discovery_run_id
FROM article_references
WHERE triage_decision = 'ACCEPT' AND acquired_paper_id IS NULL
ORDER BY voi_score DESC NULLS LAST, created_at ASC;
```

Empty after Phase 3 (no row is ACCEPT until Phase 4 triages). Tested via SC-9.

### 4.4 Shared snapshot

After every successful `db_loader.py` run, the local DB is materialized via `VACUUM INTO <shared_path>`. The shared file is byte-identical to the local file. Gitignored.

---

## 5. `discovered_via` enum (course-locked)

A single row's `discovered_via` may be **one** of these tokens or a **comma-joined sorted unique list** of them:

- `review_pdf_extract`
- `serpapi_scholar`
- `scholarly_search`
- `paperscraper_search`
- `openalex_expansion`
- `crossref_search`
- `student_upload`

Phase 3 only emits the first four. The enum is validated at the application layer (`insert_or_dedupe_reference`), not by a DDL `CHECK` constraint — because the field stores comma-joined lists. A linter test (`test_discovered_via_app_enforced`) verifies the dedupe path rejects unknown enum values.

---

## 6. `lifecycle_transitions.reason` enum (Phase 3 emits)

| Token | When |
|---|---|
| `initial_insert:<discovered_via>` | First-time insert (DOI never seen, title not a corpus match) |
| `provenance_merge:<discovered_via>` | DOI exact match → existing row's `discovered_via` extended |
| `provenance_merge_via_title:<discovered_via>` | Title-fuzzy match → existing row's `discovered_via` extended |
| `corpus_match:<corpus_paper_id>` | Title fuzzy match against `pdf_identity_inventory_local.csv` → row inserted with `triage_stage='duplicate'` |
| `doi_enriched_via_<discovered_via>` | Existing DOI-null row, new candidate has same title and a non-null DOI → row's DOI is filled |

Phase 4 will add `classifier_below_threshold`, `abstract_collected:<source>`, `triage_decision:<decision>`. Phase 5 will add `pdf_acquired:<source>`, `pdf_acquisition_failed:<source>`. Phase 3's contract owns only the five tokens above.

---

## 7. Writer attribution + `triage_stage` enum

### 7.1 `created_by` enum

| Value | Used by | Phase |
|---|---|---|
| `db_loader` | `db_loader.py` | 3 |
| `reference_harvester` | `reference_harvester.py` | 3 |
| `abstract_collector` | (future) | 4 |
| `abstract_triage` | (future) | 4 |
| `pdf_acquirer` | (future) | 5 |
| `manual_edit` | Reserved for ad-hoc human SQL edits | — |

A linter test (`test_transition_created_by_in_enum`) verifies every `INSERT INTO lifecycle_transitions` in Phase 3 code passes one of these.

### 7.2 `triage_stage` enum (Phase 3 emits)

| Value | Set by | Meaning |
|---|---|---|
| `metadata_only` | Phase 3 initial insert | Default — row exists, no triage yet |
| `duplicate` | Phase 3 corpus match | Row matches the existing corpus; PRISMA counts as "identified, removed at dedupe" |

Phase 4 will add `rejected_at_metadata`, `abstract_pending`, `triaged`. Phase 3's contract owns only `metadata_only` and `duplicate`.

---

## 8. Dedupe-on-insert decision tree

Every call to `insert_or_dedupe_reference(candidate, conn, run_id, created_by)` runs this in order — the first branch that fires wins:

```
1. Compute doi_norm = normalize_doi(candidate.doi)
   Compute title_norm = normalize_title(candidate.title_raw)

2. Validate discovered_via against §5 enum → raise on unknown.

3. BRANCH A — DOI exact match within article_references
   IF doi_norm AND a row exists with that doi:
       UPDATE existing.discovered_via to add candidate.discovered_via
              (sorted unique comma-join)
       UPDATE existing.updated_at = now()
       INSERT lifecycle_transitions(reason='provenance_merge:<via>')
       RETURN existing.reference_id

4. BRANCH B — Title fuzzy match against existing corpus
   IF title_norm matches a row in pdf_identity_inventory_local.csv
      with jaccard >= 0.92:
       new_id = mint_reference_id()
       INSERT new row with triage_stage='duplicate',
                            triage_decision='DUPLICATE',
                            triage_reason='matches_existing_corpus:<corpus_id>'
       INSERT lifecycle_transitions(from=NULL, to='duplicate',
                                    reason='corpus_match:<corpus_id>')
       RETURN new_id

5. BRANCH C — Late DOI arrival on a DOI-null intra-table row
   IF doi_norm AND there's a row with doi IS NULL
      AND title_jaccard >= 0.92:
       UPDATE existing.doi = doi_norm
       UPDATE existing.discovered_via to add candidate.discovered_via
       INSERT lifecycle_transitions(reason='doi_enriched_via_<via>')
       RETURN existing.reference_id

6. BRANCH D — Title fuzzy match within article_references (intra-table)
   IF title_norm matches an existing row with jaccard >= 0.92
      (AND doi situation didn't trigger branch C):
       UPDATE existing.discovered_via to add candidate.discovered_via
       INSERT lifecycle_transitions(reason='provenance_merge_via_title:<via>')
       RETURN existing.reference_id

7. BRANCH E — Fresh insert
   new_id = mint_reference_id()
   INSERT new row with triage_stage='metadata_only'
   INSERT lifecycle_transitions(from=NULL, to='metadata_only',
                                reason='initial_insert:<via>')
   RETURN new_id
```

### 8.1 `mint_reference_id`

```
prefix = "REF-" + today_iso_date + "-"           # 15 chars: "REF-YYYY-MM-DD-"
next_n = MAX(CAST(SUBSTR(reference_id, 16) AS INTEGER) for rows with that prefix) + 1
return prefix + zfill(next_n, 6)                  # e.g. REF-2026-05-28-000001
```

Counter resets per UTC date; cross-day uniqueness comes from the date prefix.

### 8.2 Title Jaccard

```python
def title_jaccard(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb: return 0.0
    return len(ta & tb) / len(ta | tb)
```

Threshold: **0.92**. Conservative; spot-checked manually after first real run (see DEDUPE_SPOTCHECK.md).

---

## 9. Invariants

- **I-1.** Every row in `article_references` has non-null `reference_id`, `title_raw`, `title_normalized`, `discovered_via`, `discovery_run_id`, `discovered_at`, `triage_stage`.
- **I-2.** `reference_id` matches the regex `^REF-\d{4}-\d{2}-\d{2}-\d{6}$`.
- **I-3.** Among rows with non-null `doi`, no two share the same value (enforced by `idx_article_references_doi` partial unique index).
- **I-4.** Every `INSERT INTO article_references` has a matching `INSERT INTO lifecycle_transitions` in the same transaction. (Tested by `test_transition_logged_on_insert`.)
- **I-5.** Every `lifecycle_transitions.created_by` is in the §7.1 enum.
- **I-6.** Every emitted timestamp matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`.
- **I-7.** The local DB and the shared snapshot are byte-equal after `db_loader.py` finishes (or the shared snapshot doesn't exist if `--dry-run`).

---

## 10. Success Conditions

| SC | Statement | Test |
|---|---|---|
| SC-1 | Every required column is NOT NULL where declared; defaults apply correctly. | `test_required_columns_present`, `test_default_triage_stage_is_metadata_only` |
| SC-2 | Stored DOIs match `^10\.` and are lowercase. | `test_doi_constraint_normalised` |
| SC-3 | Partial unique index prevents two rows from sharing a non-null DOI; two NULL DOIs are allowed. | `test_unique_doi_partial_index`, `test_two_null_dois_allowed` |
| SC-4 | Every `article_references` insert is paired with a `lifecycle_transitions` row in the same transaction. | `test_transition_logged_on_insert` |
| SC-5 | DOI exact match → existing row updated, no new row, `discovered_via` extended. | `test_doi_exact_match_merges_via` |
| SC-6 | Title Jaccard ≥ 0.92 within `article_references` → merge, not insert. | `test_title_jaccard_above_threshold_merges` |
| SC-7 | Title fuzzy match against corpus snapshot → row inserted with `triage_stage='duplicate'`. | `test_corpus_snapshot_match_inserts_as_duplicate` |
| SC-8 | DOI-null existing row + same-title new candidate with DOI → existing row's DOI filled. | `test_doi_enrichment_on_late_arrival` |
| SC-9 | `v_acquisition_queue` returns only `ACCEPT` rows with NULL `acquired_paper_id`, ordered by VOI desc. | `test_v_acquisition_queue_filters_correctly` |
| SC-10 | `reference_id` format is `REF-YYYY-MM-DD-NNNNNN`; daily counter increments. | `test_reference_id_format`, `test_reference_id_substr_position` |
| SC-11 | `apply_migrations` is idempotent — running it twice is a no-op the second time. | `test_migrations_idempotent` |
| SC-12 | All Phase-3 indexes exist after migrations. | `test_indexes_present` |
| SC-13 | `lifecycle_transitions.created_by` is NOT NULL. | `test_created_by_required_on_transition` |

---

## 11. Known Limitations

1. **Corpus snapshot is empty.** `pdf_identity_inventory_local.csv` ships as a header-only stub because the source `pdf_identity_inventory/latest.csv` does not exist on this machine. Dedupe still works on DOI and intra-table title; `BRANCH B` (corpus match) will never fire until the snapshot is populated.
2. **Title Jaccard at 0.92 is a heuristic.** Spot-checked manually after first real run; threshold may be tuned to 0.95 if false positives appear. See `DEDUPE_SPOTCHECK.md`.
3. **`reference_id` counter resets daily.** Two runs on the same date that both insert into a fresh DB will produce overlapping IDs. In our actual workflow this is fine — we don't reset the DB between runs.
4. **`discovered_via` is comma-joined text, not a normalized relation.** Querying "all rows discovered via X" requires `LIKE '%X%'`. Acceptable for Phase 6 dashboard volume; could be normalized in a future revision.
5. **No CHECK constraint on `discovered_via` enum.** The field stores comma-joined values which SQLite `CHECK` cannot validate cleanly. Enforcement is application-side in `insert_or_dedupe_reference`. A linter test verifies the writer rejects unknown enum values.

---

## 12. Non-Goals

- **No triage decisions.** Phase 4 owns Stage 1 (metadata triage) and Stage 2 (abstract collection + triage decision). Phase 3 leaves `triage_decision = NULL`, `triage_stage = 'metadata_only'` (or `'duplicate'` for corpus matches).
- **No abstract collection.** Phase 4.
- **No PDF acquisition.** Phase 5.
- **No PRISMA dashboard HTML.** Phase 6 (Phase 3 only ships the SQL the dashboard will execute).
- **No writes to `Article_Finder.db.papers`.** The `discovered_from_paper_id` and `acquired_paper_id` columns are soft FKs (informational TEXT). Cross-DB foreign keys are not enforced by SQLite anyway.

---

## Change Log

- **1.0.0 (2026-05-28)** — Initial release. SC-1 through SC-13. Aligned with course spec for `article_references` columns, `discovered_via` enum, dedupe-on-insert protocol. Documented local-DB-with-materialized-snapshot strategy.
