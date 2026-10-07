#!/usr/bin/env bash
# End-to-end smoke test of the kicad-routing toolchain on a synthetic board.
# Usage: bash tests/smoke_test.sh [kicad_python]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"; S="$ROOT/scripts"
PY="${1:-${KICAD_PYTHON:-python3}}"
OUT="$(mktemp -d)/kr"; mkdir -p "$OUT"
"$PY" "$S/doctor.py" || true
"$PY" "$HERE/make_test_board.py" "$OUT/test.kicad_pcb"
cp "$HERE/test_plan.json" "$OUT/plan.json"
JAR_ARGS=()
if [[ -n "${FREEROUTING_JAR:-}" && -f "${FREEROUTING_JAR}" ]]; then
  JAR_ARGS=(--jar "$FREEROUTING_JAR")
else
  echo "No FREEROUTING_JAR - using pip 'freeroute' (install: pip install freeroute)"
  "$PY" - "$OUT/plan.json" <<'PYEOF'
import json, sys
p = json.load(open(sys.argv[1])); p["autoroute"]["engine"] = "freeroute-py"; json.dump(p, open(sys.argv[1], "w"), indent=2)
PYEOF
fi
"$PY" "$S/analyze_board.py" "$OUT/test.kicad_pcb" -o "$OUT/analysis.json"
"$PY" "$S/route_critical.py" connect "$OUT/test.kicad_pcb" "C1:1" "Y1:1" --width 0.25 --lock
"$PY" "$S/route_critical.py" connect "$OUT/test.kicad_pcb" "C2:1" "Y1:2" --width 0.25 --lock
set +e
"$PY" "$S/route_pipeline.py" "$OUT/test.kicad_pcb" --plan "$OUT/plan.json" -o "$OUT/routed.kicad_pcb" "${JAR_ARGS[@]}"
RC=$?
set -e
echo "pipeline exit $RC (1 = ran but board needs work, which is expected for this synthetic test)"
echo "artifacts in $OUT"
[[ -f "$OUT/routed.kicad_pcb" && -f "$OUT/routed.kicad_pcb.pipeline.json" ]] && echo "SMOKE TEST: TOOLCHAIN OK" || { echo "SMOKE TEST: FAILED"; exit 1; }
