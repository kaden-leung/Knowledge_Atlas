# Task 3 Test Isolation Note

## Current Class-Grading Status

The PR-only checkout runs:

```text
89 passed, 1 skipped
```

The full dependency-ready workspace runs:

```text
186 passed, 1 skipped
```

The chain verifier reads the committed evidence database and reports:

```text
CHAIN: 9/9 checks passed
```

## What Is Isolated

Most unit tests create temporary SQLite databases using `tmp_path` or `:memory:`:

- Phase 3 schema/dedupe/loader tests
- Phase 4 triage and abstract-collector tests
- Phase 5 PDF-acquirer tests
- Phase 6 dashboard-generation tests

These tests do not mutate the committed evidence database.

## What Is A Reproducibility Artifact

`task3_pipeline_lifecycle.db` is a committed evidence artifact. It is used by `verify_track2_workflow.py` to prove that the end-to-end chain exists and remains internally consistent.

It is not meant to be mutated during grading. Pipeline regeneration is optional and should be run intentionally with a fresh copy or reset procedure.

## Production Blocker

For enterprise CI, the pipeline should add a stronger reset/isolation harness:

- fresh temp DB per integration run
- explicit fixture reset before PRISMA/dashboard regeneration
- no shared mutable DB in parallel jobs
- archived run IDs for live API executions

The current state is class-grade reliable and auditable, but production parallel CI needs the reset harness above.
