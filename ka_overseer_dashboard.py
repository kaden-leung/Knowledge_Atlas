"""KA Overseer Dashboard — light Streamlit admin view.

Source authority:
    docs/AF_PIPELINE_BOXOLOGY_AND_MONITORING_REQUIREMENTS_2026-05-24.md §4 §6

Two pages, picked from the sidebar:
  * Page 1 — AF→KA Pipeline Flow: boxology funnel with live counts,
    reconciler bridge widget, source attribution, stuck-paper detector.
  * Page 2 — Overseer Health & Activity: verifier health, reconciler
    activity, drift events, completion-queue triage.

Tech: native Streamlit only (no plotly, no streamlit-autorefresh). Manual
refresh button. Plain vertical funnel for the boxology per DK's call.

Usage:
    streamlit run ka_overseer_dashboard.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# Make overseer modules importable when running from project root.
import sys
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overseer.article_finder_connector import (  # noqa: E402
    ArticleFinderNotFound,
    connect_readonly as connect_af_readonly,
    resolve_af_db_path,
)
from overseer.db import resolve_db_path as resolve_ka_db_path  # noqa: E402


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

@st.cache_resource(ttl=30)
def get_ka_conn():
    path = resolve_ka_db_path()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_resource(ttl=30)
def get_af_conn():
    try:
        path = resolve_af_db_path()
    except ArticleFinderNotFound:
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_one(conn: sqlite3.Connection, sql: str, params=()) -> object:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return row[0]


def _fetch_groupby(conn: sqlite3.Connection, sql: str, params=()) -> list[tuple]:
    return [(r[0], r[1]) for r in conn.execute(sql, params).fetchall()]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------------------
# Page 1: AF→KA Pipeline Flow
# ---------------------------------------------------------------------------

def page_pipeline_flow():
    st.title("AF→KA Pipeline Flow")

    af_conn = get_af_conn()
    ka_conn = get_ka_conn()
    if af_conn is None:
        st.error(
            "Article Finder DB not found at the expected location "
            "(~/REPOS/Article_Finder_v3_2_3/data/article_finder.db). "
            "Reconciler bridge and AF-side counts are unavailable until AF is reachable."
        )
        st.stop()

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption(f"As of {_utc_now()}")
    with col_b:
        if st.button("Refresh", key="refresh_p1"):
            st.cache_resource.clear()
            st.rerun()

    # ─────────────────────────── Boxology Funnel ───────────────────────────
    st.header("Pipeline funnel (live counts)")

    af_total = _fetch_one(af_conn, "SELECT COUNT(*) FROM papers")
    af_with_abstract = _fetch_one(
        af_conn, "SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != ''"
    )
    af_with_pdf = _fetch_one(
        af_conn, "SELECT COUNT(*) FROM papers WHERE pdf_path IS NOT NULL AND pdf_path != ''"
    )
    af_intake_count = _fetch_one(
        af_conn,
        "SELECT COUNT(*) FROM papers WHERE atlas_intake_decision IS NOT NULL",
    )
    af_ae_handoff = _fetch_one(
        af_conn, "SELECT COUNT(*) FROM papers WHERE ae_run_id IS NOT NULL"
    )

    st.metric("Stage 0 — AF.papers row exists", f"{af_total:,}")
    st.metric("Stage 1-3 — Enriched / Abstract / Triage", f"{af_with_abstract:,} with abstract")

    with st.expander("Stage 4 — Atlas intake decided  (breakdown)"):
        intake_rows = _fetch_groupby(
            af_conn,
            "SELECT COALESCE(atlas_intake_decision, '(NULL)'), COUNT(*) "
            "FROM papers GROUP BY atlas_intake_decision ORDER BY 2 DESC",
        )
        st.metric("Total intake decisions made", f"{af_intake_count:,}")
        for label, n in intake_rows:
            badge = " ← Task A target" if label == "accept_candidate" else ""
            st.write(f"- **{label}**: {n:,}{badge}")

    st.metric("Stage 5 — PDF acquired", f"{af_with_pdf:,}")
    st.metric("Stage 8 — AE handoff", f"{af_ae_handoff:,}")

    with st.expander("Stages 9-11 — AE result + corpus match"):
        match_rows = _fetch_groupby(
            af_conn,
            "SELECT COALESCE(ae_corpus_match_status, '(NULL)'), COUNT(*) "
            "FROM papers GROUP BY ae_corpus_match_status ORDER BY 2 DESC",
        )
        for label, n in match_rows:
            st.write(f"- **{label}**: {n:,}")

    # ───────────────────────── Reconciler bridge ──────────────────────────
    st.header("AF ↔ KA reconciler bridge")

    af_accept = _fetch_one(
        af_conn,
        "SELECT COUNT(*) FROM papers WHERE atlas_intake_decision = 'accept_candidate'",
    )
    ka_candidates = _fetch_one(
        ka_conn,
        "SELECT COUNT(*) FROM artefact_registry "
        "WHERE kind = 'article_finder_candidate' AND active = 1",
    )
    pending = _fetch_one(
        ka_conn,
        "SELECT COUNT(*) FROM cross_db_sync_events WHERE status = 'pending'",
    )
    unresolved = _fetch_one(
        ka_conn,
        "SELECT COUNT(*) FROM cross_db_sync_events WHERE status = 'unresolved'",
    )
    matched_syncs = _fetch_one(
        ka_conn,
        "SELECT COUNT(*) FROM cross_db_sync_events WHERE status = 'matched'",
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("AF eligible (accept_candidate)", f"{af_accept:,}")
    c2.metric("KA article_finder_candidate", f"{ka_candidates:,}")
    gap = max(0, (af_accept or 0) - (ka_candidates or 0))
    c3.metric("Gap (unreconciled)", f"{gap:,}", delta=f"{-gap}" if gap else "0",
              delta_color="inverse")

    c4, c5, c6 = st.columns(3)
    c4.metric("Sync events: pending", f"{pending:,}")
    c5.metric("Sync events: matched", f"{matched_syncs:,}")
    c6.metric("Sync events: unresolved", f"{unresolved:,}",
              delta=f"{unresolved}" if unresolved else "0",
              delta_color="inverse")

    last_tick_at = _fetch_one(
        ka_conn,
        "SELECT MAX(occurred_at) FROM reconciler_event_log",
    )
    if last_tick_at:
        st.caption(f"Last reconciler tick recorded: {last_tick_at}")
    else:
        st.caption("Last reconciler tick: never recorded "
                   "(observability layer just landed; run a tick to populate)")

    # ─────────────────────── Source attribution ───────────────────────────
    st.header("Source attribution")

    source_rows = _fetch_groupby(
        af_conn,
        "SELECT COALESCE(source, '(NULL)'), COUNT(*) "
        "FROM papers GROUP BY source ORDER BY 2 DESC LIMIT 12",
    )
    if source_rows:
        st.bar_chart({r[0]: r[1] for r in source_rows})

    # ──────────────────────── Stuck-paper detector ────────────────────────
    st.header("Stuck papers (parked > 7 days)")

    stuck_breakdown = af_conn.execute(
        """
        SELECT atlas_intake_decision, COUNT(*) AS n
        FROM papers
        WHERE atlas_intake_decision IN ('edge_case', 'manual_review', 'needs_pdf_text')
          AND (julianday('now') - julianday(updated_at)) > 7
        GROUP BY atlas_intake_decision
        ORDER BY 2 DESC
        """,
    ).fetchall()
    if stuck_breakdown:
        for row in stuck_breakdown:
            st.write(f"- **{row[0]}**: {row[1]:,} papers parked > 7 days")
    else:
        st.write("- No papers parked > 7 days in tracked categories.")


# ---------------------------------------------------------------------------
# Page 2: Overseer Health & Activity
# ---------------------------------------------------------------------------

def page_overseer_health():
    st.title("Overseer Health & Activity")

    ka_conn = get_ka_conn()

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption(f"As of {_utc_now()}")
    with col_b:
        if st.button("Refresh", key="refresh_p2"):
            st.cache_resource.clear()
            st.rerun()

    # ──────────────────── Verifier health (run history) ───────────────────
    st.header("Verifier health")

    total_runs = _fetch_one(ka_conn, "SELECT COUNT(*) FROM verifier_run_history")
    passed_runs = _fetch_one(
        ka_conn, "SELECT COUNT(*) FROM verifier_run_history WHERE overall_passed = 1"
    )
    failed_runs = (total_runs or 0) - (passed_runs or 0)
    last_run = ka_conn.execute(
        "SELECT started_at, overall_passed, triggered_by FROM verifier_run_history "
        "ORDER BY started_at DESC LIMIT 1"
    ).fetchone()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total runs recorded", f"{total_runs:,}")
    c2.metric("Passed", f"{passed_runs:,}")
    c3.metric("Failed", f"{failed_runs:,}",
              delta=f"{failed_runs}" if failed_runs else "0",
              delta_color="inverse")

    if last_run is not None:
        verdict = "PASS" if last_run["overall_passed"] else "FAIL"
        st.caption(
            f"Last run: {last_run['started_at']} — {verdict} "
            f"(triggered by {last_run['triggered_by']})"
        )
    else:
        st.caption("No verifier runs recorded yet. Run "
                   "`python3 scripts/verify_dependency_overseer_contract.py --strict`.")

    # Recent run history table
    recent_runs = ka_conn.execute(
        "SELECT started_at, overall_passed, triggered_by FROM verifier_run_history "
        "ORDER BY started_at DESC LIMIT 20"
    ).fetchall()
    if recent_runs:
        with st.expander(f"Recent {len(recent_runs)} runs"):
            for r in recent_runs:
                verdict = "✓ PASS" if r["overall_passed"] else "✗ FAIL"
                st.write(f"- `{r['started_at']}` {verdict} — {r['triggered_by']}")

    # ───────────────────── Reconciler activity ────────────────────────────
    st.header("Reconciler activity")

    action_breakdown = _fetch_groupby(
        ka_conn,
        "SELECT action, COUNT(*) FROM reconciler_event_log GROUP BY action ORDER BY 2 DESC",
    )
    if action_breakdown:
        st.bar_chart({a: n for a, n in action_breakdown})
    else:
        st.info("No reconciler events recorded yet. Run "
                "`python3 scripts/dependency_overseer_reconciler_tick.py`.")

    tick_count = _fetch_one(
        ka_conn, "SELECT COUNT(DISTINCT tick_run_id) FROM reconciler_event_log"
    )
    last_tick = _fetch_one(
        ka_conn, "SELECT MAX(occurred_at) FROM reconciler_event_log"
    )
    c1, c2 = st.columns(2)
    c1.metric("Reconciler ticks recorded", f"{(tick_count or 0):,}")
    c2.caption(f"Most recent event: {last_tick or 'never'}")

    # ─────────────────────── Signature drift events ───────────────────────
    st.header("Signature drift events (unresolved)")

    drifts = ka_conn.execute(
        """
        SELECT lifecycle_payload_hash, created_at,
               (julianday('now') - julianday(created_at)) * 86400.0 AS age_seconds
        FROM cross_db_sync_events
        WHERE status = 'unresolved'
        ORDER BY created_at
        """,
    ).fetchall()
    if drifts:
        for d in drifts:
            age_min = int((d["age_seconds"] or 0) / 60)
            st.write(
                f"- `{d['lifecycle_payload_hash']}` — flagged {d['created_at']} "
                f"({age_min} minutes ago)"
            )
    else:
        st.write("- No unresolved drift events.")

    # ───────────────────── Completion queue triage ────────────────────────
    st.header("Completion queue")

    cq_by_sev = _fetch_groupby(
        ka_conn,
        "SELECT severity, COUNT(*) FROM completion_queue "
        "WHERE status IN ('open', 'in_review') "
        "GROUP BY severity ORDER BY CASE severity "
        "WHEN 'blocking' THEN 0 WHEN 'high' THEN 1 "
        "WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END",
    )
    if cq_by_sev:
        c_cols = st.columns(len(cq_by_sev))
        for i, (sev, n) in enumerate(cq_by_sev):
            delta_color = "inverse" if sev in ("blocking", "high") else "normal"
            c_cols[i].metric(sev, f"{n:,}", delta=f"{n}",
                             delta_color=delta_color)
    else:
        st.write("- Completion queue is empty.")

    blocking_open = ka_conn.execute(
        "SELECT queue_id, reason, paper_id, first_seen_at FROM completion_queue "
        "WHERE status IN ('open','in_review') AND severity = 'blocking' "
        "ORDER BY first_seen_at LIMIT 25"
    ).fetchall()
    if blocking_open:
        with st.expander(f"Open BLOCKING items ({len(blocking_open)})"):
            for b in blocking_open:
                st.write(
                    f"- `{b['queue_id'][:24]}…` reason=`{b['reason']}` "
                    f"paper_id=`{b['paper_id']}` since `{b['first_seen_at']}`"
                )

    # ───────────────────────── Stale artefacts ─────────────────────────────
    st.header("Stale artefacts")
    stale = _fetch_one(
        ka_conn,
        "SELECT COUNT(*) FROM artefact_registry "
        "WHERE active = 1 AND freshness_status = 'stale'",
    )
    quarantined = _fetch_one(
        ka_conn,
        "SELECT COUNT(*) FROM rebuild_queue WHERE state = 'quarantine'",
    )
    c1, c2 = st.columns(2)
    c1.metric("Stale active artefacts", f"{(stale or 0):,}",
              delta=f"{stale}" if stale else "0", delta_color="inverse")
    c2.metric("Quarantined queue items", f"{(quarantined or 0):,}",
              delta=f"{quarantined}" if quarantined else "0",
              delta_color="inverse")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="KA Overseer Dashboard",
        layout="wide",
    )
    page = st.sidebar.radio(
        "Page",
        options=("AF→KA Pipeline Flow", "Overseer Health & Activity"),
        index=0,
    )
    st.sidebar.caption(
        "Source: `docs/AF_PIPELINE_BOXOLOGY_AND_MONITORING_REQUIREMENTS_2026-05-24.md`"
    )
    if page == "AF→KA Pipeline Flow":
        page_pipeline_flow()
    else:
        page_overseer_health()


if __name__ == "__main__":
    main()
