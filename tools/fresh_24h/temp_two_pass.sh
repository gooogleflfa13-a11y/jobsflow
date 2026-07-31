#!/usr/bin/env bash
# Temp (or daily) scan → two-pass score (3.3 gate → deep JD → rescore).
# Does NOT build CV materials. Materials = separate job_materials / handbook step.
#
# Usage:
#   ./tools/fresh_24h/temp_two_pass.sh              # default: temp
#   ./tools/fresh_24h/temp_two_pass.sh temp
#   ./tools/fresh_24h/temp_two_pass.sh 临时          # same as temp
#   ./tools/fresh_24h/temp_two_pass.sh daily
#   ./tools/fresh_24h/temp_two_pass.sh 3             # last 3 hours
#   ./tools/fresh_24h/temp_two_pass.sh 24            # last 24 hours
#   GATE=3.3 ./tools/fresh_24h/temp_two_pass.sh temporary
#
# Pass-2 deep: LinkedIn CLI + JobsDB Playwright. CT = teaser only (no browser).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ARG="${1:-temp}"
GATE="${GATE:-3.3}"
MODE=""
HOURS=""

# Numeric arg -> custom hours mode
if [[ "$ARG" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  MODE="temp"
  HOURS="--hours $ARG"
else
  case "$ARG" in
    daily) MODE="daily" ;;
    temp) MODE="temp" ;;
    临时|temporary|ad-hoc|adhoc)
      MODE="temp"
      ;;
    *)
      echo "ERROR: mode must be daily|temp|N(hours); got: $ARG" >&2
      exit 2
      ;;
  esac
fi

echo "=== 1) Scan (${MODE}${HOURS:+ hours=$ARG}) ==="
python3 tools/fresh_24h/fresh_24h_scan.py --mode "$MODE" $HOURS

echo ""
echo "=== 2) Two-pass score (gate=$GATE → deep JD → rescore) ==="
echo "    Deep: LinkedIn CLI + JobsDB Playwright; CT = teaser only (no browser)"
python3 tools/fresh_24h/two_pass_score.py --gate "$GATE"

echo ""
echo "Done. Open JobSearch_2026/02_Tracker/*_twopass_scored.csv"
echo "Columns: 初评分数 / 深评分数 / JD深度 ; CareerOps* = 深评"
echo "JD深度: deep (LinkedIn/JobsDB) | teaser (CT/其他) | teaser_fallback (读失败)"
echo ""
echo "Next (optional sheet): push_to_gsheet.py --also-local --min-score 3.3 --mode $MODE"
echo "Materials only on demand (never from this script):"
echo "  python3 -m tools.job_materials pipeline --package '…/C0-xxx_未投_…' --lane C"
