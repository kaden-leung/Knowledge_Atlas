"""Small labeled abstract evaluation to produce a confusion table for triage classifier.

This test loads `fixtures/abstract_eval.json`, runs the Stage 2B keyword-fallback
classifier on each example, and asserts the confusion counts are produced.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# Ensure Phase 4 modules are importable
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from stage2b_triage_decision import keyword_fallback_classify_with_abstract  # noqa: E402


def test_abstract_eval_confusion():
    fixtures = _HERE / "fixtures" / "abstract_eval.json"
    data = json.loads(fixtures.read_text(encoding="utf-8"))

    tp = fp = tn = fn = 0
    for entry in data:
        label = entry.get("label")
        title = entry.get("title")
        venue = entry.get("venue")
        abstract = entry.get("abstract")

        _, conf = keyword_fallback_classify_with_abstract(title, venue, abstract)
        predicted = "RELEVANT" if conf >= 0.50 else "NOT_RELEVANT"

        if predicted == "RELEVANT" and label == "RELEVANT":
            tp += 1
        elif predicted == "RELEVANT" and label == "NOT_RELEVANT":
            fp += 1
        elif predicted == "NOT_RELEVANT" and label == "NOT_RELEVANT":
            tn += 1
        elif predicted == "NOT_RELEVANT" and label == "RELEVANT":
            fn += 1

    # This fixture intentionally exposes the keyword fallback's limits:
    # false accepts for architecture-adjacent pedagogy/engineering papers, and
    # one false reject for a relevant review that scores below the hard threshold.
    total = tp + fp + tn + fn
    assert total == len(data)
    assert {"tp": tp, "fp": fp, "tn": tn, "fn": fn} == {
        "tp": 2,
        "fp": 2,
        "tn": 1,
        "fn": 1,
    }
