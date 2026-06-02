# Lessons Learned

**Date:** 2026-06-02  
**Purpose:** Summarize what evaluation changed about the project

## 1. Main lesson

Evaluation showed that retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature.

That changed the project from a simple pipeline demonstration into a measured retrieval-system analysis. The most important work was not making the pipeline look perfect; it was identifying where the pipeline actually loses value.

## 2. What changed because of evaluation

| Initial assumption | Evaluation result | Lesson |
|---|---|---|
| The main risk was classifier quality | Most missed benchmark papers were never retrieved | Retrieval coverage has to improve before classifier tuning can raise recall |
| Higher-VOI queries would be more productive | ACCEPT rate did not track cleanly with VOI inside the narrow score range | VOI ranking needs either wider score separation or an additional retrieval-quality signal |
| Query syntax validated in the UI would transfer cleanly to API search | Two queries returned zero API results | Query validation has to happen through the same retrieval interface used by the pipeline |
| Abstract collection failures would mostly be API bugs | Many failures were legitimate `MISSING_ABSTRACT` terminal states | Missing evidence should be logged explicitly rather than forced into REJECT |
| Acquisition readiness and acquisition execution were the same story | The DB proves readiness, while live acquisition remains unverified | Implemented, dry-run, and live-demonstrated states need separate labels |

## 3. What improved after measurement

- The benchmark report now identifies retrieval coverage as the dominant bottleneck.
- The Stage 1 classifier keyword list was expanded after human validation found lexical false negatives.
- Corrupted abstract handling was added after a metadata audit found a wrong-paper abstract.
- Query reformulation became explicit future work after null-result analysis.
- The grader path now separates verified evidence from planned or dry-run-only functionality.

## 4. What remains limited

- The current demonstrated classifier is keyword fallback, not the intended semantic classifier.
- The benchmark corpus is useful but still small and author-curated.
- The handoff layer is local validation, not external production integration.
- PDF acquisition is dry-run evidenced, not live-demonstrated in the current verified DB state.

## 5. What surprised me most

**Tests passing did not mean retrieval was working.**

Before running the benchmark, 185/185 unit tests passed and the pipeline executed end-to-end without errors. That looked like success. The benchmark showed 33% retrieval recall and 13% end-to-end recall. The gap between "the pipeline runs correctly" and "the pipeline finds the right papers" was much larger than expected. A test suite can verify that a search engine reliably queries APIs and stores results — it cannot verify that the right papers are being found. That distinction was not obvious before measurement.

**VOI did not predict which queries would find useful papers.**

The query with the highest VOI (SC3-step3, VOI 0.478) contributed 2 ACCEPTs. The query with the lowest VOI (CSMP1-step2, VOI 0.443) also contributed 2 ACCEPTs. Three intermediate-VOI queries added 43 papers to the buffer and 0 ACCEPTs. The score that was supposed to rank query priority had no discriminating power within the 0.035 range that all ten queries produced. This was not a signal that VOI scoring is wrong in theory — it was a signal that a 0.035 spread is too compressed to rank anything.

**The biggest single miss was a linguistic edge case, not a model failure.**

The worst classifier bug was not a sophisticated semantic error. It was that "architecture" is not a substring of "architectural" — they differ at position 12. Every paper using the adjectival form got clf=0.00 and was rejected at Stage 1. The most-cited foundational CNFA paper in the benchmark was among them. This was found not by testing but by asking why a known paper was absent from the ACCEPT list. The lesson: the most impactful quality problems are often not found by running tests. They are found by examining specific failures.

---

## 6. Final takeaway

The strongest version of this project is honest: it demonstrates a working gap-driven retrieval and triage chain, then uses evaluation to show that the next major improvement should target retrieval coverage before downstream triage refinement.
