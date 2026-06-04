# Task 3 Dependency and Portability Note

## What Works In A PR-Only Checkout

The official grader and lightweight verification paths work from the PR checkout:

```bash
python3 160sp/autograders/t2_task3_grader.py "/path/to/Track 2/Task 3" kaden-leung
cd "Track 2/Task 3"
python3 verify_track2_workflow.py
python3 -m pytest -q
python3 search_runner.py --help
python3 abstract_collector.py --help
python3 abstract_triage.py --help
```

Current PR-only pytest result:

```text
89 passed, 1 skipped
```

The PR-only suite skips sibling-dependent tests cleanly instead of failing import collection.

## What Requires The Full COGS-160 Workspace

The complete offline suite and full live pipeline use sibling repositories:

- `Article_Finder` for `core.ae_corpus_dedupe` and classifier utilities.
- `Article_Eater` for paper-fetcher clients and VOI helpers.
- `atlas_shared` for optional classifier integrations.

In the dependency-ready full workspace, the complete offline result is:

```text
186 passed, 1 skipped
```

## atlas_shared Options

Provide one of:

- installed package: `pip install atlas_shared`
- local checkout: `KA_ATLAS_SHARED_SRC=/path/to/atlas_shared/src`
- sibling checkout next to `Knowledge_Atlas`

If absent, sibling-dependent tests are skipped and Stage 1 uses the keyword fallback. This is a class-safe fallback, not the intended production classifier.

## Class-Grading Boundary

For class grading, the committed database, JSON evidence, dashboard, and root shims are sufficient. For full regeneration or production operation, use the full COGS-160 sibling checkout.
