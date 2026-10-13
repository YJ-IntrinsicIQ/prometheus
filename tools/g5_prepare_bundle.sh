#!/usr/bin/env bash
# M63 / G5 — reproduces the scratch replacement bundle end to end. Read-only on the repository; everything is written under $WORK (default /private/tmp/claude-501/g5b).
# Needs the evidence root BASE (a symlink farm with the G3 overlays; default /private/tmp/claude-501/g4/root) and the repaired candidates CAND.
set -euo pipefail
cd "$(dirname "$0")/.."
WORK=${WORK:-/private/tmp/claude-501/g5b}; BASE=${BASE:-/private/tmp/claude-501/g4/root}; CAND=${CAND:-$WORK/cand}
mkdir -p "$WORK"
python3 pipelines/g4_investor_answers.py --root "$BASE" --out "$CAND" >/dev/null
python3 tools/g5_build_bundle.py --root "$BASE" --cand "$CAND" --out "$WORK/bundle"
python3 tools/g5_build_sandbox.py --base "$BASE" --bundle "$WORK/bundle" --out "$WORK/root"
dump() {  # $1 = root, $2 = output json
  ( cd apps/ask-intrinsiciq && cp ../../tools/g5_dump_surfaces.test.ts.txt src/lib/challenge/g5dump.test.ts \
    && G5_DUMP="$2" ASK_INTRINSICIQ_REPO_ROOT="$1" npx vitest run src/lib/challenge/g5dump.test.ts >/dev/null 2>&1; rm -f src/lib/challenge/g5dump.test.ts )
}
dump "$WORK/root" "$WORK/surf_pass1.json"
dump "" "$WORK/surf_served.json" 2>/dev/null || true
python3 tools/g5_clean_inventory.py --cand "$CAND" --root "$BASE" --surf-cand "$WORK/surf_pass1.json" --surf-served "$WORK/surf_served.json" --json "$WORK/clean_pass1.json" >/dev/null
python3 tools/g5_build_sidecar.py --inventory "$WORK/clean_pass1.json" --ledger-root "$BASE" --sandbox-root "$WORK/root"
dump "$WORK/root" "$WORK/surf_pass2.json"
