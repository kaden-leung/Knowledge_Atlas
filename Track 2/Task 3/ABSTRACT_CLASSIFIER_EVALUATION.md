# Abstract Classifier Evaluation

**Purpose:** provide a small labeled check of Stage 2B keyword-fallback classification validity. This is not a production validation set; it is a transparent sanity evaluation that separates parser correctness from scientific classification accuracy.

## Fixture

The labeled fixture is [Phase 4/fixtures/abstract_eval.json](<Phase 4/fixtures/abstract_eval.json>). It contains 6 examples drawn from the current ACCEPT / near-ACCEPT pattern:

| Count | Meaning |
|---:|---|
| 3 | CNFA-relevant examples |
| 3 | Not-relevant or CNFA-adjacent false-positive controls |

## Current Result

Running [Phase 4/test_abstract_eval.py](<Phase 4/test_abstract_eval.py>) against `keyword_fallback_classify_with_abstract()` produces:

| Metric | Count |
|---|---:|
| True positives | 2 |
| False positives | 2 |
| True negatives | 1 |
| False negatives | 1 |
| Precision | 50.0% |
| Recall | 66.7% |

## Interpretation

The keyword fallback is good enough to demonstrate the class pipeline, but it is not good enough for autonomous production ingestion.

Observed error pattern:

- **False accepts:** architecture-adjacent papers in pedagogy or energy/comfort engineering can accumulate enough vocabulary hits to look CNFA-relevant.
- **False rejects:** relevant review or synthesis papers can score below the hard `0.50` threshold when they use broad health/architecture language rather than mechanism-heavy CNFA vocabulary.

Production implication: before any autonomous Article Eater ingestion, replace or supplement the keyword fallback with the intended semantic classifier and evaluate it on a larger externally reviewed labeled set.
