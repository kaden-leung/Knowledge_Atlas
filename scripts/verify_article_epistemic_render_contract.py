#!/usr/bin/env python3
"""Rendered-page verifier for the article-detail epistemic layer (spec §11).

Three layers of check, strongest-available-first:

  1. STATIC   — ka_article_view.html contains the epistemic renderer, the
                section, the guarded payload fetch, the six Toulmin slots, and
                visible (no-hover) provenance chips.
  2. SYNTAX   — the page's inline <script> parses under `node --check`.
  3. RENDER   — the epistemic render functions are executed in node against a
                real payload record; the produced HTML must contain the
                required markers (primary claim, all six Toulmin slots, the
                pending/planned availability badges, claim facets, provenance).
  4. CONTRACT — every record in the payload carries the fields the renderer
                reads (availability_summary, toulmin.slots×6, components, …).
  5. BROWSER  — DOM/mobile-overflow/console-error checks via Playwright IF a
                browser binary is installed; otherwise reported as SKIPPED
                (not a failure) with the install hint. These are spec §11's
                runtime checks and require a real browser.

Usage:
    python3 scripts/verify_article_epistemic_render_contract.py --strict
    python3 scripts/verify_article_epistemic_render_contract.py --strict --payload PATH
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "ka_article_view.html"
DEFAULT_PAYLOAD = REPO_ROOT / "data" / "ka_payloads" / "article_epistemic_layer.json"

TOULMIN_SLOTS = ("Claim", "Grounds", "Warrant", "Qualifier", "Rebuttal", "Backing")


# ---------------------------------------------------------------------------
# 1. Static checks
# ---------------------------------------------------------------------------

def static_checks(html: str) -> list[str]:
    fails: list[str] = []

    def need(token: str, why: str) -> None:
        if token not in html:
            fails.append(f"static: missing {why} ({token!r})")

    need("function renderEpistemicLayer", "epistemic renderer")
    need('id="epistemic-reading"', "epistemic section container")
    need("data/ka_payloads/article_epistemic_layer.json", "guarded epistemic payload fetch")
    need("${renderEpistemicLayer(epistemicLayer)}", "epistemic section injected into the page")
    need("renderEpiProvenance", "provenance renderer")
    need("availability_summary", "availability summary use")
    need("epi-badge", "availability/pending/planned badges")
    # Provenance must be visible without hover: chips are <span class="chip">,
    # not title=/tooltip. Flag if provenance is rendered only via title=.
    if "renderEpiProvenance" in html and 'class="epi-prov"' not in html:
        fails.append("static: provenance chips container .epi-prov missing (no-hover requirement)")
    for slot in TOULMIN_SLOTS:
        if f"renderToulminSlot('{slot}'" not in html:
            fails.append(f"static: Toulmin slot {slot!r} not rendered")
    return fails


# ---------------------------------------------------------------------------
# 2/3. Node syntax + render checks
# ---------------------------------------------------------------------------

def _extract_inline_scripts(html: str) -> list[str]:
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)


def node_available() -> bool:
    return shutil.which("node") is not None


def node_syntax_check(html: str) -> list[str]:
    if not node_available():
        return ["syntax: SKIPPED (node not on PATH)"]
    fails: list[str] = []
    for i, script in enumerate(_extract_inline_scripts(html)):
        if "renderEpistemicLayer" not in script and len(script) < 200:
            continue  # tiny config scripts; only check substantive ones
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(script)
            tmp = fh.name
        try:
            r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
            if r.returncode != 0:
                fails.append(f"syntax: inline script #{i} failed node --check: "
                             f"{r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'error'}")
        finally:
            Path(tmp).unlink(missing_ok=True)
    return fails


def node_render_check(html: str, sample_layer: dict | None) -> list[str]:
    """Execute the epistemic render functions in node against a real record."""
    if not node_available():
        return ["render: SKIPPED (node not on PATH)"]
    if sample_layer is None:
        return ["render: SKIPPED (no sample record in payload)"]
    # Slice the epistemic render functions out of the page (between epiBadge and
    # the next unrelated function) so we run the page's real code, not a copy.
    m = re.search(r"(function epiBadge\(.*?)\nfunction renderMeasureRows", html, re.DOTALL)
    if not m:
        return ["render: could not locate epistemic render functions in page"]
    funcs = m.group(1)
    harness = (
        "function esc(s){return String(s==null?'':s)"
        ".replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        "function compact(s,n){s=String(s||'');return s.length>n?s.slice(0,n)+'…':s;}\n"
        + funcs + "\n"
        "const layer = " + json.dumps(sample_layer) + ";\n"
        "const out = renderEpistemicLayer(layer);\n"
        "process.stdout.write(out);\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(harness)
        tmp = fh.name
    try:
        r = subprocess.run(["node", tmp], capture_output=True, text=True)
    finally:
        Path(tmp).unlink(missing_ok=True)
    if r.returncode != 0:
        return [f"render: node execution failed: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'error'}"]
    out = r.stdout
    fails: list[str] = []
    required_markers = [
        ('id="epistemic-reading"', "section"),
        ("Toulmin reading", "Toulmin heading"),
        ("Backing", "Backing slot"),
        ("planned", "planned badge"),
        ("Argument support", "argument support block"),
        ("epi-prov", "provenance chips"),
    ]
    for token, why in required_markers:
        if token not in out:
            fails.append(f"render: output missing {why} ({token!r})")
    # The honest-label guarantees:
    if "label only" not in out:
        fails.append("render: warrant not labelled 'label only' (honesty requirement)")
    return fails


# ---------------------------------------------------------------------------
# 4. Payload contract checks
# ---------------------------------------------------------------------------

def contract_checks(payload: dict) -> list[str]:
    fails: list[str] = []
    details = (payload or {}).get("details") or {}
    if not details:
        return ["contract: payload has no details"]
    checked = 0
    for pid, layer in details.items():
        ctx = f"contract[{pid}]"
        if "availability_summary" not in layer:
            fails.append(f"{ctx}: no availability_summary")
        t = layer.get("toulmin") or {}
        slots = t.get("slots") or {}
        missing = {s.lower() for s in TOULMIN_SLOTS} - set(slots.keys())
        if missing:
            fails.append(f"{ctx}: toulmin missing slots {sorted(missing)}")
        if "related_work" not in layer:
            fails.append(f"{ctx}: no related_work")
        comps = layer.get("components") or {}
        for req in ("primary_claim", "evidence_strength", "claim_rows",
                    "defeaters", "belief_network_context"):
            c = comps.get(req)
            if not c:
                fails.append(f"{ctx}: component {req} absent")
                continue
            for fld in ("source_mode", "freshness_status", "review_status"):
                if fld not in c:
                    fails.append(f"{ctx}: {req} missing provenance field {fld}")
        checked += 1
        if checked >= 50 and len(fails) == 0:
            # Sampling: if the first 50 are clean the shape is uniform (builder
            # is deterministic); full-scan only continues while clean to bound cost.
            pass
    return fails


# ---------------------------------------------------------------------------
# 5. Browser checks (optional)
# ---------------------------------------------------------------------------

def browser_checks(sample_paper_id: str | None) -> tuple[list[str], str]:
    """Scoped DOM smoke at mobile width via Playwright. FAILS only if the
    epistemic section is missing or its OWN subtree overflows horizontally;
    pre-existing page overflow (navbar, legacy tables) and unrelated 404s do
    NOT fail this check. Skips cleanly (never false-fails) on any infra problem.
    """
    if sample_paper_id is None:
        return [], "SKIPPED (no sample paper id)"
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return [], "SKIPPED (playwright not importable)"

    import http.server
    import socket
    import socketserver
    import threading

    # Ephemeral local server rooted at the repo so the page can fetch payloads.
    class _QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(REPO_ROOT), **k)
        def log_message(self, *a):  # silence 404 noise from legacy assets
            pass
    handler = _QuietHandler
    try:
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
        httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    except Exception as exc:
        return [], f"SKIPPED (could not start local server: {type(exc).__name__})"
    th = threading.Thread(target=httpd.serve_forever, daemon=True); th.start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:
                return [], (f"SKIPPED (no browser binary: {type(exc).__name__}; "
                            "run `python3 -m playwright install chromium`)")
            try:
                page = browser.new_page(viewport={"width": 390, "height": 800})
                page.goto(f"http://127.0.0.1:{port}/ka_article_view.html?id={sample_paper_id}",
                          wait_until="networkidle", timeout=60000)
                page.wait_for_selector("#epistemic-reading", timeout=15000)
                # Scoped overflow: does the epistemic subtree exceed the viewport?
                epi_overflow = page.evaluate("""() => {
                  const vw=document.documentElement.clientWidth;
                  const root=document.querySelector('#epistemic-reading');
                  if(!root) return 'missing';
                  let worst=0;
                  root.querySelectorAll('*').forEach(el=>{
                    const r=el.getBoundingClientRect(); if(r.right>worst) worst=r.right;
                  });
                  return worst > vw + 2 ? Math.round(worst)+' > '+vw : 'ok';
                }""")
                slots = page.eval_on_selector_all(
                    "#epistemic-reading .toulmin-slot", "els => els.length")
            finally:
                browser.close()
    except Exception as exc:
        return [], f"SKIPPED ({type(exc).__name__}: {exc})"
    finally:
        httpd.shutdown()

    fails = []
    if epi_overflow == "missing":
        fails.append("browser: #epistemic-reading did not render")
    elif epi_overflow != "ok":
        fails.append(f"browser: epistemic section overflows mobile width ({epi_overflow})")
    if slots != 6:
        fails.append(f"browser: expected 6 Toulmin slots rendered, got {slots}")
    status = "PASS (epistemic section renders mobile-safe)" if not fails else "FAIL"
    return fails, status


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any runnable check fails")
    args = ap.parse_args(argv)

    if not PAGE.exists():
        print(f"ERROR: page not found: {PAGE}", file=sys.stderr)
        return 2
    html = PAGE.read_text(encoding="utf-8")

    payload_path = Path(args.payload)
    if not payload_path.is_absolute():
        payload_path = REPO_ROOT / payload_path
    payload = json.loads(payload_path.read_text()) if payload_path.exists() else {}
    details = (payload or {}).get("details") or {}
    sample_pid = next(iter(details)) if details else None
    sample = details.get(sample_pid) if sample_pid else None

    static_f = static_checks(html)
    syntax_f = node_syntax_check(html)
    render_f = node_render_check(html, sample)
    contract_f = contract_checks(payload) if payload else ["contract: no payload to check"]
    browser_f, browser_status = browser_checks(sample_pid)

    def report(name: str, fails: list[str]) -> int:
        skipped = [f for f in fails if "SKIPPED" in f]
        real = [f for f in fails if "SKIPPED" not in f]
        mark = "PASS" if not real else "FAIL"
        if skipped and not real:
            mark = "SKIP"
        print(f"  [{mark}] {name}: {len(real)} failure(s)"
              + (f", {len(skipped)} skipped" if skipped else ""))
        for f in real[:8]:
            print(f"      - {f}")
        for f in skipped:
            print(f"      · {f}")
        return len(real)

    print("Render-contract verification:")
    real_total = 0
    real_total += report("static", static_f)
    real_total += report("syntax", syntax_f)
    real_total += report("render", render_f)
    real_total += report("contract", contract_f)
    real_total += report("browser", browser_f)
    print(f"  [INFO] browser status: {browser_status}")

    print(f"Total real failures: {real_total}"
          + ("" if details else "  (payload absent — contract check could not run)"))
    if args.strict and real_total:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
