# Experiment-Only Search Output

`search_results_new_templates.json` is not part of the evaluated Task 3 DB state.

It records the controlled expansion run `RUN-20260603-020713`:

| Field | Value |
|---|---:|
| Input queries | 6 |
| SerpAPI credits used | 6 |
| Raw results | 120 |
| Candidates after dedupe | 67 |
| Null-result queries | 0 |
| Rows loaded into `task3_pipeline_lifecycle.db` | 0 |

The file is useful evidence for the retrieval-ablation discussion in
[../RETRIEVAL_ABLATION.md](../RETRIEVAL_ABLATION.md), but the graded pipeline
state remains the precision-reviewed 10-ACCEPT DB documented in
[../MANIFEST.md](../MANIFEST.md), [../PROVEIT_WORKS.md](../PROVEIT_WORKS.md),
and [../BENCHMARK_EVALUATION.md](../BENCHMARK_EVALUATION.md).

This boundary is intentional: the 67 candidates were not manually precision
reviewed, so merging them late would make the evaluated ACCEPT set less honest.
