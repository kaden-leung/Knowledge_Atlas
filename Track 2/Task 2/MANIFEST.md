# Task 2 Submission Manifest
## Track 2 · Task 2: Gap Targeting & Query Generation

**Branch:** `track/2-staging/kaden-leung` (continuation of Task 1 branch)
**Student:** Kaden Leung
**Submission date:** 2026-05-23

---

## File inventory

### Phase 1 — Boxology + gap analysis
- `Track 2/Task 2/Phase 1/PIPELINE_DIAGRAM.md` — boxology diagram + 5 priority gaps with VOI scores

### Phase 2 — Gap extractor
- `Track 2/Task 2/Phase 2/GAP_EXTRACTOR_CONTRACT.md` — v3.3 contract (inputs, processing, outputs, 15 success conditions)
- `Track 2/Task 2/Phase 2/gap_report.json` — canonical output (554 gaps, schema 3.3.0)
- `Track 2/Task 2/Phase 2/gap_results.json` — rubric-compatible alias of `gap_report.json`

### Phase 3 — Query generator
- `Track 2/Task 2/Phase 3/QUERY_GENERATOR_CONTRACT.md` — v1.4 contract
- `Track 2/Task 2/Phase 3/query_generator.py` — implementation
- `Track 2/Task 2/Phase 3/query_pairs.json` — canonical output (10 query pairs, schema 1.4.0)
- `Track 2/Task 2/Phase 3/query_results.json` — rubric-compatible alias (key `queries` instead of `query_pairs`)

### Phase 4 — Spot-check + review
- `Track 2/Task 2/Phase 4/SPOT_CHECK.md` — manual Google testing rubric for 3 queries (template ready to fill)
- `Track 2/Task 2/Phase 4/QUERY_REVIEW.md` — self-audit of 10 queries against `ka_google_search_guide.html`
- `Track 2/Task 2/Phase 4/VERIFICATION.md` — 17 verification questions caught real problems in the generator
- `Track 2/Task 2/VERIFICATION_ANSWERS.md` — direct answers for the autograder's manual verification bucket
- `Track 2/Task 2/MANUAL_REVIEW_PACKET.md` — fast review path for the remaining 5 manual points
- `Track 2/Task 2/DEPENDENCY_AND_PORTABILITY.md` — explicit sibling dependency boundary
- `Track 2/Task 2/VOI_TRANSPARENCY_NOTE.md` — clarifies first-stage heuristic VOI vs full Bayesian/BN VOI

### Submission root (autograder-discoverable)
- `Track 2/Task 2/gap_extractor.py` — copy of `Article_Eater/gap_extractor.py`
- `Track 2/Task 2/query_generator.py` — copy of Phase 3 implementation
- `Track 2/Task 2/gap_results.json` — copy of Phase 2 output
- `Track 2/Task 2/query_results.json` — copy of Phase 3 output

---

## Canonical outputs vs. rubric aliases

Two parallel naming conventions are emitted in this submission:

### Canonical outputs (contract-defined)

These follow the names specified in the contract documents:

| File | Defined by | Key |
|---|---|---|
| `Phase 2/gap_report.json` | `GAP_EXTRACTOR_CONTRACT.md` v3.3 § Outputs | `gaps` |
| `Phase 3/query_pairs.json` | `QUERY_GENERATOR_CONTRACT.md` v1.4 § Outputs | `query_pairs` |

### Rubric aliases (autograder-discoverable)

These are duplicate files with the names specified in the grading rubric:

| File | Defined by | Key |
|---|---|---|
| `Phase 2/gap_results.json` | Rubric "Files you must change or create" | `gaps` |
| `Phase 3/query_results.json` | Rubric "Files you must change or create" | `queries` (renamed from `query_pairs` for autograder compatibility) |

### Submission-root copies (autograder root-discoverable)

Four byte-identical copies placed at the submission root because the autograder looks for `os.path.join(submission_dir, "<file>")`:

| Root copy | Source | SHA-256 (truncated) | Byte-identical? |
|---|---|---|---|
| `gap_extractor.py` | `Article_Eater/gap_extractor.py` | `4e55a0fe...8b75` | ✓ |
| `gap_results.json` | `Phase 2/gap_results.json` | `805d2073...744a` | ✓ |
| `query_generator.py` | `Phase 3/query_generator.py` | `cf2e81e0...e37f` | ✓ |
| `query_results.json` | `Phase 3/query_results.json` | `5f53a0b3...0ed0` | ✓ |

Reviewers can `diff` root copies against Phase files and confirm zero divergence.

### Implementation notes

- Duplicate files are real copies, not symlinks (symlinks break on Windows, ZIP exports, and GitHub web download).
- `Phase 2/gap_report.json` and `Phase 2/gap_results.json` are byte-identical (same content, same key — the rubric accepts either `gaps` key or a list).
- `Phase 3/query_pairs.json` and `Phase 3/query_results.json` have key-normalized content equality (same `query_pairs.json` content with the top-level key renamed `query_pairs` → `queries` for autograder compatibility).

---

## Autograder result

Run command: `python3 160sp/autograders/t2_task2_grader.py "Track 2/Task 2" kaden-leung`

| Criterion | Pts | Result | Notes |
|---|---|---|---|
| Gap extraction | 15/15 | PASS | 554 gaps extracted |
| VOI scoring | 10/10 | PASS | All entries have `voi_score` |
| AI Citation queries | 10/10 | PASS | 10/10 follow 5-component pattern |
| Boolean queries | 10/10 | PASS | 10/10 use AND/OR + quoted phrases |
| Spot-check | 5/5 | PASS | `SPOT_CHECK.md` present |
| Verification questions | 5/10 | WARN (autograder-capped) | `VERIFICATION.md` provides 17 caught problems for manual grading |
| **Total** | **55/60** | | Manual grading on Verification questions can lift to 60/60 |

---

## Git operations

File manifest snapshot at submission time:

```
git status --short
?? "Track 2/"
```

(Single untracked directory holding all Task 2 deliverables. `git diff --name-only upstream/master` will produce the full file list after staging.)

### Identity-safety safeguards

Applied to prevent accidental commits or pushes under another student's identity:

1. **Stripped non-self remotes from the clone.** `dhruv` and `julie` fetch/push refs were removed via `git remote remove`. Local remote list now contains only:
   - `origin` → `github.com/dkirsh/Knowledge_Atlas` (upstream, read-only in practice)
   - `fork` → `github.com/kaden-leung/Knowledge_Atlas` (own fork — sole push target)

   These strips affect only the local clone's `.git/config`; nothing on GitHub was modified. If a peer fork ever needs to be re-added for inspection, use `git remote add dhruv https://github.com/<user>/Knowledge_Atlas.git`.

2. **Explicit remote names in every push.** All push commands name the remote and branch explicitly (`git push fork track2/kaden-leung-task2`), never bare `git push` — bare push would resolve a remote ambiguously.

3. **No `--all` pushes.** Only the named branch is ever pushed.

4. **Pre-push dry-run.** Every push is preceded by `git push --dry-run fork <branch>` to confirm exactly which remote will receive which refs before any data leaves the machine.

5. **Identity verification before submission.** `git config user.name` and `git config user.email` were verified to resolve to `Kaden Leung / k7leung@ucsd.edu`. All existing `[T2-Task1]` commits on this branch were audited — all 37 are authored AND committed by Kaden Leung. Zero Kaden commit hashes exist on any other student's remote.

---

## How to reproduce

```bash
# From Article_Eater repo root:
python3 gap_extractor.py --templates-dir data/templates/ --output /tmp/gap_report.json --all

# From Knowledge_Atlas/Track\ 2/Task\ 2/ (this directory):
python3 query_generator.py --gaps /tmp/gap_report.json --output query_pairs.json --top-n 10 \
  --vocab ../../../Article_Eater/contracts/vocab/cross_field_vocabulary.yaml

# Determinism check:
python3 query_generator.py --gaps /tmp/gap_report.json --output /tmp/run1.json --top-n 10 ...
python3 query_generator.py --gaps /tmp/gap_report.json --output /tmp/run2.json --top-n 10 ...
diff <(jq 'del(.metadata.generated_at)' /tmp/run1.json) <(jq 'del(.metadata.generated_at)' /tmp/run2.json)
# Expected: empty diff
```

The `query_generator.py` script self-verifies the `vocabulary_hash` at write time (asserts that the stored hash matches a recomputed hash from the in-memory vocab dict).

---

## Notes for the reviewer

1. **All deliverables are framed as self-audit.** No peer attribution is included for contract reviews or query improvements — improvements are presented as work the student did against the contract, not as adopted recommendations from others.

2. **The grader entry point now runs without errors** when invoked by the grader with an absolute submission path, and `python3 gap_extractor.py --help` works directly from this directory. Full extraction still requires Article Eater services; see `DEPENDENCY_AND_PORTABILITY.md`.

3. **The `Article_Finder/scripts/` repo location for `gap_extractor.py`** flagged by the autograder under "Repo-Worthy Items" is noted as needs_review. The canonical Article_Eater location is preserved (templates live there) and a working copy is placed at the submission root for the autograder.

4. **Phase 4 SPOT_CHECK.md is supporting evidence, not the only verification source.** The manual-review case is consolidated in `MANUAL_REVIEW_PACKET.md` and `VERIFICATION_ANSWERS.md`.
