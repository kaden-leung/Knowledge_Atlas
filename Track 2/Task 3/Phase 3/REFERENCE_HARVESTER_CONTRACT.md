# Reference Harvester Contract — Phase 3 Second Writer

**Track 2 · Task 3 · Phase 3**
**Author:** Kaden Leung
**Contract Version:** 1.0.0
**Last Updated:** 2026-05-28

---

## 1. System Summary

`reference_harvester.py` is the second writer into `article_references`. It walks a set of PDF directories, locates each PDF's references section, splits it into individual reference lines, regex-extracts DOI / year / first-author / title where possible, and calls `insert_or_dedupe_reference()` exactly once per parsed line. It is a deliberate, scope-limited heuristic extractor — not a structured-bibliography parser. The contract acknowledges parsing accuracy is roughly 70% on well-formatted PDFs and lower on older or scanned documents; Stage 1 metadata triage in Phase 4 handles the cleanup.

The grader's check is identical to the search runner's: every reference the harvester finds becomes either a new `article_references` row or merges into an existing one. Free-floating JSON outputs do not count.

---

## 2. Inputs

| Parameter | Default | Meaning |
|---|---|---|
| `pdf_dirs` | `Part 2 Pdfs/`, `Part_One_10pdfs/` | Directories of PDFs to harvest |
| `db_path` | `Track 2/Task 3/task3_pipeline_lifecycle.db` | Same DB the search runner writes to |
| `run_id` | required | Stamped on every row inserted in this harvest |
| `dry_run` | False | No DB writes; emit a planning report only |
| `output` | `reference_harvest_results.json` | Audit JSON path |

Every PDF in each directory is processed. A PDF that produces zero parseable references is recorded with `references_section_found=False`.

---

## 3. Processing

For each PDF:

1. Open with `pdfplumber`.
2. Extract text from every page.
3. **Locate the references section.** Scan from the end of the document backward for a heading matching (case-insensitive): `References`, `Bibliography`, `Works Cited`, `Literature Cited`, or `References and Notes`. If no header is found, give up on this PDF and record `references_section_found=False`.
4. **Split into entries** by reference markers (see §4 styles).
5. **Per entry**, regex-extract:
   - DOI via `r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+"`
   - Year via `r"\((\d{4})\)"` first, then bare `r"\b(19|20)\d{2}\b"`
   - First-author surname via heuristic (text before first comma, last whitespace token)
   - Title via heuristic (text between author block and year/venue marker)
6. **Compute `parse_confidence`** in `[0.0, 1.0]` based on how many of the four optional fields were extractable. Unparseable lines still get inserted with `parse_style='unparseable'`, `raw_citation` populated, and other fields null.
7. **Call `insert_or_dedupe_reference()`** with:
   - `discovered_via='review_pdf_extract'`
   - `discovered_from_paper_id=PDF-<sanitised_filename>`
   - `created_by='reference_harvester'`

The harvester opens a single transaction per PDF. A pdfplumber error on one PDF logs to the audit JSON's `errors` list and continues to the next PDF.

---

## 4. Supported parse styles

| Style | Marker regex (entry start) | Example |
|---|---|---|
| `numbered` | `^\s*(\d{1,3})\s*[.)]\s+` | `1. Smith, J. & Doe, A. (2024). Title. Journal.` |
| `bracketed` | `^\s*\[(\d{1,3})\]\s*` | `[12] Smith, J. (2024). Title.` |
| `name_year` | `^[A-Z][a-z]+,\s+[A-Z]\.\s*(?:[A-Z]\.\s*)?(?:&|,)` | `Smith, J. & Doe, A. (2024). Title.` |

**Out of scope** (still inserted but as `parse_style='unparseable'`):
- Vancouver superscript-numbered (`Smith J¹`)
- Footnote-style continuous prose
- Non-Latin scripts
- Two-column PDFs where reference text wraps unpredictably

---

## 5. Outputs

### 5.1 Rows written to `article_references`

Every parsed line produces exactly one call to `insert_or_dedupe_reference()`. Fields populated by the harvester:

| Field | Source |
|---|---|
| `discovered_via` | always `'review_pdf_extract'` |
| `discovered_from_paper_id` | `PDF-<sanitised filename>` |
| `raw_citation` | full reference-line text as captured (always set) |
| `doi` | regex-extracted (often `None`) |
| `title_raw` | parsed title; falls back to first 80 chars of `raw_citation` if heuristic returned nothing |
| `first_author_surname`, `publication_year`, `venue` | best-effort, may be `None` |
| `voi_score` | always `None` (these references aren't from a VOI-scored gap) |

### 5.2 `reference_harvest_results.json`

```json
{
  "metadata": {
    "schema_version": "1.0.0",
    "run_id": "RUN-20260528-120000",
    "generated_at": "2026-05-28T12:00:01Z",
    "pdf_dirs": ["Part 2 Pdfs", "Part_One_10pdfs"],
    "pdfs_scanned": 20,
    "pdfs_with_references_section": 0,
    "raw_reference_lines": 0,
    "parsed_lines": {"numbered": 0, "bracketed": 0, "name_year": 0, "unparseable": 0},
    "inserted_into_db": 0,
    "merged_count": 0,
    "marked_duplicate_count": 0
  },
  "per_pdf": [
    {
      "pdf_path": "...",
      "pdf_id": "PDF-...",
      "references_section_found": true,
      "raw_lines": 0,
      "parsed_lines": 0,
      "unparseable_lines": 0,
      "inserted": 0,
      "merged": 0,
      "errors": []
    }
  ],
  "unparseable_lines_sample": []
}
```

`unparseable_lines_sample` is capped at 20 examples; the full set lives in the DB as rows with `parse_style='unparseable'`.

---

## 6. Invariants

- **I-1.** Every reference line that produces a successful `pdfplumber` extraction either ends up in `article_references` (as a new row, a merged row, or a corpus-match duplicate) or is recorded in `reference_harvest_results.json.errors[]` with the failing PDF identified.
- **I-2.** Every row written by the harvester has `discovered_via` including `'review_pdf_extract'`.
- **I-3.** Every row written by the harvester has `discovered_from_paper_id` non-null and matching the regex `^PDF-[A-Za-z0-9_-]+$`.
- **I-4.** Every `lifecycle_transitions` row from this writer has `created_by='reference_harvester'`.
- **I-5.** Direct `INSERT INTO article_references` outside `insert_or_dedupe_reference()` is forbidden (linter test).

---

## 7. Success Conditions

| SC | Statement | Test |
|---|---|---|
| SC-H1 | DOI regex finds the DOI on a sample reference line. | `test_extracts_doi_from_reference_line` |
| SC-H2 | Year extracted from `(2024)` parens or bare 4-digit year. | `test_extracts_year_from_parens`, `test_extracts_year_bare` |
| SC-H3 | First-author surname extracted from the standard `Surname, X.` opening. | `test_extracts_first_author_surname` |
| SC-H4 | `numbered` style detected and parsed correctly. | `test_parses_numbered_style` |
| SC-H5 | `bracketed` style detected and parsed correctly. | `test_parses_bracketed_style` |
| SC-H6 | `name_year` style detected and parsed correctly. | `test_parses_name_year_style` |
| SC-H7 | Lines that match no style still produce a row with `parse_style='unparseable'`. | `test_unparseable_falls_through_with_raw_only` |
| SC-H8 | PDF without a references section returns an empty per-pdf entry with `references_section_found=False`. | `test_handles_pdf_with_no_references_section` |
| SC-H9 | Missing PDF directory logs a warning and exits with code 0. | `test_handles_missing_pdf_directory` |
| SC-H10 | Every harvester insert goes through `insert_or_dedupe_reference` (no raw `INSERT INTO article_references` in the file). | `test_harvester_uses_dedupe_path` |
| SC-H11 | Every row has `discovered_via='review_pdf_extract'`. | `test_discovered_via_set_to_review_pdf_extract` |
| SC-H12 | Every row has `discovered_from_paper_id` matching `^PDF-[A-Za-z0-9_-]+$`. | `test_discovered_from_paper_id_set_to_pdf_id` |

---

## 8. Known Limitations

1. **Heuristic parser.** ~70% accuracy on well-formatted modern PDFs. Old, scanned, or non-English documents may produce many `unparseable` rows.
2. **Two-column layouts.** Reference text may wrap unpredictably across columns; we capture left-column text only and accept partial losses.
3. **AE coordination scripts not used.** The course spec references `scripts/coordination/extract_neuro_key_review_references.py`, which does not exist on this machine. We build our own equivalent.
4. **Prototyping corpus.** Course spec references a 46-PDF review corpus at `/Users/davidusa/...`; substituted with 20 local PDFs from `Part 2 Pdfs/` (10) + `Part_One_10pdfs/` (10). Not all are review papers, so harvest yield may be lower than the spec implies.
5. **Filename → paper_id.** `PDF-<sanitised>` is a soft FK to the `papers` table the AE recovery repo would maintain. We don't enforce existence; we accept any string matching the regex.

---

## 9. Non-Goals

- No triage decisions on harvested rows. Default `triage_stage='metadata_only'`; Phase 4 Stage 1 will reject most noisy harvested lines.
- No abstract collection.
- No DOI resolution beyond regex extraction. If the PDF says `10.x/y`, we store `10.x/y`; we do not call CrossRef to verify.
- No citation-graph extraction (which paper cites which).
- No in-text citation context.
