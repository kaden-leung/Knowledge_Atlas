# Track 2 Task 1 Grader Guide

## What Changed

Task 1 fixes the public contribute-page path so submitted papers expose classifier feedback to the student instead of disappearing into a silent intake flow. The missing gap was the absence of a visible result/verdict path after submission.

## Manual Review

The autograder reports **70 / 75**. The remaining 5 points are the manual diagnosis-of-failures bucket. See [MANUAL_REVIEW_PACKET.md](MANUAL_REVIEW_PACKET.md) and [DIAGNOSIS_OF_FAILURES.md](DIAGNOSIS_OF_FAILURES.md).

## Inputs

- `ka_contribute_public.html`: public contribution page under review.
- `Phase 1 & 2/contracts/CLASSIFIER_INTEGRATION_CONTRACT_2026-05-09.md.MOVED`: inherited classifier integration contract.
- `Phase 1 & 2/contracts/schemas/classifier_response.json`: classifier response schema.

## Outputs

- A contribute page with classifier/result/verdict language visible in the submitted artifact.
- Review notes documenting the failure analysis and peer-comparison findings.
- A file-level manifest in this guide for the grader.

## Success Conditions

- The submission includes the public contribute-page artifact.
- The contract states inputs, outputs, and success criteria.
- The diagnosis identifies the missing result path as the user-facing failure.
- Verification evidence is present in the audit and walkthrough notes.

## Git Manifest

Relevant Task 1 files in this PR:

- `Track 2/Task 1/ka_contribute_public.html`
- `Track 2/Task 1/AUDIT_2026-05-18.md`
- `Track 2/Task 1/COGS160_T2_Task1_Walkthrough.md`
- `Track 2/Task 1/PEER_PR_COMPARISON_2026-05-19.md`
- `Track 2/Task 1/MANUAL_REVIEW_PACKET.md`
- `Track 2/Task 1/DIAGNOSIS_OF_FAILURES.md`
- `Track 2/Task 1/REPO_WORTHY_NOTE.md`
- `Track 2/Task 1/CONTRIBUTE_PAGE_FLOW_DIAGRAM.md`
- `Track 2/Task 1/CLASSIFIER_RESULT_BOXOLOGY.md`
- `Track 2/Task 1/Phase 1 & 2/contracts/CLASSIFIER_INTEGRATION_CONTRACT_2026-05-09.md.MOVED`
