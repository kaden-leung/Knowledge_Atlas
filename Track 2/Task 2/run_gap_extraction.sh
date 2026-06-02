#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AE_ROOT="$ROOT/Article_Eater"

export PYTHONPATH="$AE_ROOT:$AE_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

python3 "$AE_ROOT/gap_extractor.py" \
  --templates-dir "$AE_ROOT/data/templates" \
  "$@"
