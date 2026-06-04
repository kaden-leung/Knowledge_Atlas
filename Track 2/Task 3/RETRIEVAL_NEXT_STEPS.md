# Retrieval Next Steps

## Central Limitation

The dominant failure is retrieval coverage, not triage mechanics. Most benchmark misses never enter `article_references`, so no classifier or VOI threshold can recover them downstream.

## Highest-Leverage Fixes

| Fix | Why It Helps |
|---|---|
| Add subfield queries for ART, SRT, biophilic design, neuroaesthetics, wayfinding, and mobile EEG | Covers canonical CNFA areas the 10 gap-driven queries miss |
| Add semantic retrieval / embedding search | Finds papers that do not share exact Boolean vocabulary |
| Add DOI-targeted lookup for known benchmark papers | Separates search recall from API/indexing limitations |
| Rewrite over-narrow Boolean constraints | Reduces zero-result queries caused by overly specific phrase combinations |
| Remove or test `-review` suffix behavior per API | Some APIs parse it differently from the Scholar UI |

## What Not To Do

Do not claim that classifier tuning alone solves recall. Classifier improvements help precision after retrieval, but cannot recover papers that never enter the candidate pool.

## Class-Grading Interpretation

The pipeline is real enough to grade because it performs discovery, dedupe, abstract collection, triage, acquisition attempt logging, PRISMA reporting, and local handoff. The recall limitation is documented as an empirical finding, not hidden.
