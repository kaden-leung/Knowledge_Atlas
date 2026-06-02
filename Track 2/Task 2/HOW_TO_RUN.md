# Task 2 How To Run

This file gives the shortest honest path to reproduce Task 2 in the current workspace.

## 1. Current reality

Task 2 depends on the local `Article_Eater` checkout for gap extraction.

- Gap extraction lives in [Article_Eater/gap_extractor.py](</Users/bigdaddy/Downloads/UCSD/COGS 160/Article_Eater/gap_extractor.py>).
- Query generation lives in [Track 2/Task 2/Phase 3/query_generator.py](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 2/Phase 3/query_generator.py>).

The submission manifest describes root-copy files, but in this workspace snapshot the canonical runnable files are the ones above.

## 2. One-command gap extraction

From [Track 2/Task 2](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 2>):

```bash
bash run_gap_extraction.sh --output /tmp/gap_report.json --top-n 10
```

This wrapper:

- sets the required `PYTHONPATH`
- points `gap_extractor.py` at the local `Article_Eater/data/templates`
- passes your extra CLI flags through unchanged

## 3. Query generation

Then run:

```bash
python3 "Phase 3/query_generator.py" \
  --gaps /tmp/gap_report.json \
  --output /tmp/query_results.json \
  --top-n 10 \
  --vocab "../../Article_Eater/contracts/vocab/cross_field_vocabulary.yaml"
```

## 4. What to expect

- Gap extraction produces a `gap_report.json`-style file with scored gaps.
- Query generation produces paired AI Citation + Boolean queries.
- The query generator is deterministic aside from `generated_at`; the determinism check is documented in [MANIFEST.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 2/MANIFEST.md>).

## 5. Known limitation

Task 2 is still not fully standalone in this workspace snapshot because gap extraction depends on the sibling `Article_Eater` repo contents. This wrapper removes the manual `PYTHONPATH` guesswork, but it does not remove the dependency itself.
