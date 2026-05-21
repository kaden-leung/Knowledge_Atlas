#!/bin/bash
# ============================================================
# V7 Complete Overnight Pipeline — Full Soup-to-Nuts
# ============================================================
# Phases:
#   1. V7 DB sync (157 already-extracted papers)
#   2. Canonical rebuild + KA payload regeneration
#   3. DYK generation (empirical first, stops on quota)
#   4. Docling batch on remaining ~968 papers (local CPU)
#   5. Substitution graph extraction (Docling-first, 3-voice)
# ============================================================
set -eo pipefail

AE="/Users/davidusa/REPOS/Article_Eater_PostQuinean_v1_recovery"
KA="/Users/davidusa/REPOS/Knowledge_Atlas"
LOG="$KA/logs/v7_overnight_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$KA/logs"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# ---- PHASE 1: V7 DB SYNC ----
log "=== PHASE 1: SYNC ALREADY-EXTRACTED PAPERS INTO V7 DB ==="
cd "$AE"
python3 -c "
import sys; sys.path.insert(0, '.')
from pathlib import Path
from src.services.gold_v7_authority import build_gold_v7_authority
from src.services.v7_extraction_registry import V7ExtractionRegistry
auth = build_gold_v7_authority(Path('.'))
registry = V7ExtractionRegistry(auth.registry_db_path, auth)
counts = registry.sync_from_outputs()
print(f'Synced: {counts.papers} papers, {counts.field_rows} fields, {counts.visual_rows} visuals, {counts.measurement_rows} measurements')
" | tee -a "$LOG"

# ---- PHASE 2: CANONICAL REBUILD + KA PAYLOADS ----
log "=== PHASE 2: CANONICAL REBUILD (export + EN/BN + topics) ==="
cd "$AE"
python3 scripts/run_v7_canonical_rebuild.py --skip-payloads 2>&1 | tee -a "$LOG"

log "=== PHASE 2b: REGENERATE KA PAYLOADS ==="
cd "$KA"
python3 scripts/build_ka_adapter_payloads.py 2>&1 | tee -a "$LOG"

log "=== PHASE 2c: VERIFY PAYLOAD GROWTH ==="
python3 -c "
import json
arts = json.load(open('data/ka_payloads/articles.json'))
dets = json.load(open('data/ka_payloads/article_details.json'))
evid = json.load(open('data/ka_payloads/evidence.json'))
print(f'articles.json: {len(arts.get(\"articles\",[]))} papers')
print(f'article_details.json: {len(dets.get(\"details\",{}))} entries')
print(f'evidence.json: {len(evid.get(\"evidence\",[]))} claims')
" | tee -a "$LOG"

# ---- PHASE 3: DYK GENERATION ----
log "=== PHASE 3: REGENERATE PAPER_IDS.TXT + DYK GENERATION ==="
cd "$KA"
python3 -c "
import json, os
arts = json.load(open('data/ka_payloads/articles.json'))
# Check for existing DYK cards
dyk_path = 'data/ka_payloads/did_you_know_llm_overrides.json'
existing_ids = set()
if os.path.exists(dyk_path):
    existing_dyk = json.load(open(dyk_path))
    existing_ids = {c.get('paper_id') for c in existing_dyk.get('cards',[])}
all_arts = arts.get('articles',[])
empirical = sorted([a['paper_id'] for a in all_arts
    if a.get('paper_id') not in existing_ids
    and a.get('article_type','').lower() in ('empirical_research','empirical')])
other = sorted([a['paper_id'] for a in all_arts
    if a.get('paper_id') not in existing_ids
    and a['paper_id'] not in empirical])
os.makedirs('data/v7_complete_run_2026-05-19', exist_ok=True)
with open('data/v7_complete_run_2026-05-19/paper_ids.txt','w') as f:
    for pid in empirical + other: f.write(pid + '\n')
print(f'Wrote {len(empirical)} empirical + {len(other)} other = {len(empirical)+len(other)} papers for DYK')
" | tee -a "$LOG"

log "=== PHASE 3b: PREFLIGHT DYK TESTS ==="
python3 -m pytest -q tests/test_v7_complete_dyk_run.py tests/test_dyk_llm_authoring_contract.py 2>&1 | tee -a "$LOG"
python3 scripts/verify_dyk_llm_authoring_contract.py --strict 2>&1 | tee -a "$LOG"

log "=== PHASE 3c: DYK BATCH RUN ==="
LLM_INVOCATION_MODE=api \
LLM_PROVIDER=google \
LLM_MODEL=gemini-2.5-pro \
python3 scripts/run_v7_complete_with_dyk.py \
  --corpus-list data/v7_complete_run_2026-05-19/paper_ids.txt \
  --batch-size 50 \
  --concurrency 10 \
  --mode api \
  --provider google \
  --model gemini-2.5-pro \
  --max-cards-per-paper 3 \
  --output-dir data/v7_complete_dyk_cards \
  --consolidate-into data/ka_payloads/did_you_know_llm_overrides.json \
  2>&1 | tee -a "$LOG" || log "DYK batch stopped (quota or error) — continuing"

log "=== PHASE 3d: FINAL DYK VERIFICATION ==="
python3 scripts/verify_dyk_llm_authoring_contract.py --strict data/ka_payloads/did_you_know_llm_overrides.json 2>&1 | tee -a "$LOG" || true

# ---- PHASE 4: DOCLING STATUS CHECK ----
log "=== PHASE 4: DOCLING STATUS (running in AG with 6 parallel workers) ==="
cd "$AE"
python3 -c "
import os
from pathlib import Path
papers_dir = Path('data/papers')
docling_count = sum(1 for d in os.listdir(papers_dir)
    if d.startswith('PDF-') and (papers_dir / d / 'docling').exists()
    and any((papers_dir / d / 'docling').glob('*.md')))
total = sum(1 for d in os.listdir(papers_dir) if d.startswith('PDF-'))
print(f'Docling coverage: {docling_count}/{total} papers ({100*docling_count/total:.1f}%)')
" 2>&1 | tee -a "$LOG"

# ---- PHASE 5: SUBSTITUTION GRAPH EXTRACTION (streams behind Docling) ----
log "=== PHASE 5: SUBSTITUTION GRAPH EXTRACTION (per-paper Docling gate) ==="
cd "$AE"

# Archive old pre-Docling staging data
python3 -c "
import sqlite3
from pathlib import Path
db_path = Path('substitution_graph.db')
if db_path.exists():
    db = sqlite3.connect(str(db_path))
    old_count = db.execute('SELECT count(DISTINCT paper_id) FROM staging_construct_measure_extractions').fetchone()[0]
    if old_count > 0:
        db.execute('''CREATE TABLE IF NOT EXISTS staging_archive AS
                      SELECT *, 'pre_docling_2026-05-20' as archive_reason
                      FROM staging_construct_measure_extractions WHERE 0''')
        db.execute('''INSERT INTO staging_archive
                      SELECT *, 'pre_docling_2026-05-20' as archive_reason
                      FROM staging_construct_measure_extractions''')
        db.execute('DELETE FROM staging_construct_measure_extractions')
        db.commit()
        print(f'Archived {old_count} pre-Docling papers. Starting fresh with Docling text only.')
    else:
        print('Staging table is empty. Starting fresh.')
else:
    print('No existing substitution_graph.db found.')
" 2>&1 | tee -a "$LOG"

# Streaming extraction loop: process Docling-ready papers, wait for more, repeat
log "=== Starting streaming extraction loop ==="
python3 -c "
import os, time, subprocess, sys
from pathlib import Path

papers_dir = Path('data/papers')
consecutive_idle = 0

while consecutive_idle < 3:
    # Count Docling-ready papers not yet extracted
    import sqlite3
    db = sqlite3.connect('substitution_graph.db')
    try:
        done_ids = {r[0] for r in db.execute('SELECT DISTINCT paper_id FROM staging_construct_measure_extractions').fetchall()}
    except:
        done_ids = set()
    db.close()

    docling_ready = sorted([
        d for d in os.listdir(papers_dir)
        if d.startswith('PDF-') and (papers_dir / d / 'docling').exists()
        and any((papers_dir / d / 'docling').glob('*.md'))
        and d not in done_ids
    ])

    if not docling_ready:
        consecutive_idle += 1
        print(f'No new Docling-ready papers to extract (idle pass {consecutive_idle}/3). Waiting 5 min...')
        time.sleep(300)
        continue

    consecutive_idle = 0
    print(f'Found {len(docling_ready)} Docling-ready papers to extract. Processing...')

    # Run the extractor on this batch (--ag-only uses Gemini API only)
    result = subprocess.run(
        ['python3', 'scripts/substitution_graph_extract.py', '--limit', str(len(docling_ready)), '--ag-only'],
        capture_output=False, text=True
    )
    if result.returncode != 0:
        print(f'Extractor exited with code {result.returncode} (quota?). Stopping.')
        break

    print(f'Pass complete. Checking for newly Docling-converted papers...')
    time.sleep(30)

print('Streaming extraction loop finished.')
" 2>&1 | tee -a "$LOG" || log "Substitution graph stopped (quota or error)"

# ---- FINAL SUMMARY ----
log "=== OVERNIGHT RUN COMPLETE ==="
cd "$KA"
python3 -c "
import json, sqlite3, os
from pathlib import Path

# DYK cards
dyk_path = Path('data/ka_payloads/did_you_know_llm_overrides.json')
if dyk_path.exists():
    dyk = json.load(open(dyk_path))
    print(f'DYK cards: {len(dyk.get(\"cards\",[]))}')

# KA articles
arts = json.load(open('data/ka_payloads/articles.json'))
print(f'KA articles: {len(arts.get(\"articles\",[]))}')

# V7 DB
ae = Path('$AE')
v7_db = ae / 'data' / 'v7_gold_extraction_registry.db'
if v7_db.exists():
    v7 = sqlite3.connect(str(v7_db))
    count = v7.execute('SELECT count(*) FROM gold_papers').fetchone()[0]
    print(f'V7 DB papers: {count}')

# Substitution graph
sg_db = ae / 'substitution_graph.db'
if sg_db.exists():
    sg = sqlite3.connect(str(sg_db))
    sg_count = sg.execute('SELECT count(DISTINCT paper_id) FROM staging_construct_measure_extractions').fetchone()[0]
    print(f'Substitution graph papers: {sg_count}')

# Docling coverage
papers_dir = ae / 'data' / 'papers'
docling_count = sum(1 for d in os.listdir(papers_dir)
    if d.startswith('PDF-') and (papers_dir / d / 'docling').exists()
    and any((papers_dir / d / 'docling').glob('*.md')))
print(f'Docling converted: {docling_count}')
" 2>&1 | tee -a "$LOG"

log "=== Log saved to $LOG ==="
