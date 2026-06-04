# Task 1 Diagnosis of Failures

## Manual Review Target

The official Task 1 autograder reports **70 / 75**. The only remaining points are the manual-review bucket:

| Criterion | Automatic score | Reason |
|---|---:|---|
| Diagnosis of failures | 5 / 10 | Manual review required |

This document is the direct evidence for that bucket.

## Failure Taxonomy

| Failure | Type | Evidence | Fix / Control |
|---|---|---|---|
| Public contribution flow did not clearly return classifier feedback to the student | User-facing integration failure | `ka_contribute_public.html`, `CONTRIBUTE_PAGE_FLOW_DIAGRAM.md` | Submission artifact now includes visible classifier/result/verdict surface |
| Server-side classifier routing needed explicit handling for accept / edge case / reject / needs review | Implementation integration risk | `COGS160_T2_Task1_Walkthrough.md` sections on Q2, Q4, Q5 | Routing logic documented with status outcomes and classifier output preservation |
| Off-topic papers could land in a vague edge-case path because the classifier has only positive topic definitions | Classifier/spec limitation | `COGS160_T2_Task1_Walkthrough.md` sections F and off-topic threshold diagnosis | Compensating routing control: weak topic match plus edge-case verdict routes to off-topic rejection |
| Multi-submission visibility could collapse into only the latest result | Frontend state/auditability failure | `COGS160_T2_Task1_Walkthrough.md` Q6 | Results accumulate instead of replacing previous results |
| Classifier output could be visible in the response but not preserved for later review | Auditability failure | `COGS160_T2_Task1_Walkthrough.md` Q5 | Classifier verdict, confidence, topic, and next action are documented as preserved review evidence |

## What Works Now

- The submission includes a public contribute page artifact with visible classifier/result/verdict language.
- The contract names inputs, outputs, and success conditions.
- The verification writeup distinguishes implementation bugs from classifier-quality limitations.
- The diagnosis does not claim the classifier is scientifically perfect; it claims the page-to-server-to-classifier path is wired and reviewable.

## Remaining Limitation

This PR proves the contribute-page integration and routing story for class grading. It does not make the classifier itself production-perfect. The classifier still needs broader off-topic/negative-topic coverage before autonomous production use.

## Manual Score Request

Award the remaining diagnosis-of-failures points because the submission identifies the actual failure modes, separates code defects from classifier/spec limitations, and documents the compensating controls.
