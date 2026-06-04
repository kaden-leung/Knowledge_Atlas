# VOI Comparison Note

**Purpose:** clarify what Track 2's scalar VOI does and does not prove.

## Track 2 VOI

Task 2 assigns each gap/query a scalar VOI score. Task 3 carries that query-level score into Stage 2B and combines it with classifier confidence. In the committed run, the active query VOI scores occupy a narrow range:

```text
0.443-0.478
```

Rows harvested from local PDF reference lists do not carry a discovery query, so Stage 2B uses the documented fallback:

```text
voi_default = 0.443
```

This is useful for first-stage article hunting because it preserves the search intent that produced a candidate. It is not full decision-theoretic VOI.

## Comparison

| System | Inputs | Dimensions | Output | Status in this submission |
|---|---|---|---|---|
| Track 2 scalar VOI | Gap/query metadata from Task 2 | gap priority, confidence/uncertainty proxy, corpus coverage, depth tier | one query-level scalar | implemented |
| Article Eater findings VOI | extracted paper findings | gap type, confidence, effect size, maturity | finding-level VOI after extraction | not called before extraction |
| BN opportunity scoring | belief-network state | gap severity, evidence contestation, network centrality, downstream impact, feasibility | opportunity priority | not implemented |
| Article Eater active learning | BN uncertainty and corpus state | credible interval, structural VOI, epistemic VOI, supporting paper count, search terms | acquisition/search priority | not implemented |
| Bayesian VOI | prior credence, likelihood model, utility function | expected information gain, expected utility gain, downstream decision impact | decision-theoretic value | conceptual benchmark only |

## Required Judgment

Track 2 VOI is good enough for class-stage search prioritization and for preserving why a candidate was found. It is not enough to drive enterprise acquisition priorities by itself.

The current evaluation confirms this limitation: ACCEPT yield did not track cleanly with VOI inside the narrow `0.443-0.478` range. The right production path is either:

- add a richer `voi_breakdown` aligned with Article Eater / BN structural and epistemic dimensions, or
- explicitly keep this pipeline as a first-stage ranking supplier and let Article Eater compute findings-derived VOI after extraction.
