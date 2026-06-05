"""Pipeline operational thresholds and constants.

Import this module for threshold values rather than hardcoding them in
individual pipeline stages. Changing a threshold here propagates to all
stages, generate_run_report.py, and the circuit breakers.
"""
from __future__ import annotations

# ── SerpAPI budget ────────────────────────────────────────────────────────────
SERPAPI_MONTHLY_BUDGET: int = 250       # hard limit from account plan
SERPAPI_PER_RUN_CAP: int = 50           # enforced in search_runner.py

# ── Retrieval quality thresholds ──────────────────────────────────────────────
MIN_QUERY_SUCCESS_RATE: float = 0.80    # fail run if < 80% of queries return results
MAX_NULL_QUERY_RATE: float = 0.20       # warn if > 20% queries return zero results

# ── Abstract collection thresholds ───────────────────────────────────────────
MIN_DOI_ABSTRACT_HIT_RATE: float = 0.70 # warn if DOI-bearing abstract hit rate < 70%

# ── Stage 1 triage thresholds ────────────────────────────────────────────────
MAX_STAGE1_REJECTION_RATE: float = 0.90 # warn if > 90% of candidates rejected at Stage 1

# ── Stage 2B triage thresholds (production targets, not autograder criteria) ──
MIN_ACCEPT_PRECISION: float = 0.70      # TP / (TP + FP) on labeled evaluation set
MIN_ACCEPT_RECALL: float = 0.50         # TP / (TP + FN) on labeled evaluation set
MAX_FALSE_ACCEPT_RATE: float = 0.30     # FP / total ACCEPTs
MAX_HIGH_VOI_FALSE_REJECT_RATE: float = 0.10  # FN rate among VOI >= 0.45 papers

# ── Circuit breaker thresholds ────────────────────────────────────────────────
SERPAPI_CIRCUIT_BREAKER_CONSECUTIVE_429S: int = 3
ABSTRACT_SOURCE_CIRCUIT_BREAKER_CONSECUTIVE_FAILS: int = 5
PDF_ACQUIRER_NO_OA_WARN_THRESHOLD: int = 3  # warn only, do not open circuit

# ── DB integrity ─────────────────────────────────────────────────────────────
EVIDENCE_DB_MIN_ROWS: int = 1193        # committed evidence DB expected minimum
EVIDENCE_DB_MIN_ACCEPTS: int = 10       # committed evidence DB expected ACCEPT count

# ── Human review gate ────────────────────────────────────────────────────────
REVIEW_SIGN_OFF_MAX_AGE_DAYS: int = 30  # policy_clearance.json sign_off_date max age
