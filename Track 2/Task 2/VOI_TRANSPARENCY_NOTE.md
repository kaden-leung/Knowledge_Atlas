# Task 2 VOI Transparency Note

## What The Score Does

Task 2 VOI is a first-stage query-prioritization heuristic. It ranks gaps before article retrieval so the search stage starts with gaps that look epistemically useful.

The score combines:

- gap type / priority
- confidence or uncertainty proxy
- framework relevance
- corpus coverage / sparsity
- depth or maturity indicators

## What The Score Does Not Do

It is not a full enterprise acquisition-priority score. It does not yet compute:

- expected information gain from a specific study design
- expected utility gain downstream
- full BN structural VOI
- active-learning uncertainty over a live corpus
- feasibility and cost of acquiring a specific paper

## How It Should Be Used

Use this VOI to decide which gaps become search queries first. After papers are retrieved and extracted, Article Eater / BN machinery should compute richer structural and epistemic VOI at the finding level.

## Review Implication

This is good enough for Task 2 class grading and first-stage article hunting. It should not be represented as production Bayesian VOI by itself.
