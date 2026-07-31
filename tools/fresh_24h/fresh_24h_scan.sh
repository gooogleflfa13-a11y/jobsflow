#!/usr/bin/env bash
# Fresh job scan wrapper — daily (24h) or temp (since last refresh).
#
# Usage:
#   ./tools/fresh_24h/fresh_24h_scan.sh                 # daily ~24h
#   ./tools/fresh_24h/fresh_24h_scan.sh daily
#   ./tools/fresh_24h/fresh_24h_scan.sh temp            # 临时：自上次刷新至今
#   ./tools/fresh_24h/fresh_24h_scan.sh 临时
#   ./tools/fresh_24h/fresh_24h_scan.sh --show-state
#   ./tools/fresh_24h/fresh_24h_scan.sh temp --limit-per-query 20
#
# Extra flags after the mode are passed to fresh_24h_scan.py.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="$ROOT/tools/fresh_24h/fresh_24h_scan.py"

MODE="daily"
ARGS=()
if [[ $# -gt 0 ]]; then
  case "$1" in
    daily|temp|临时|temporary|ad-hoc|adhoc)
      MODE="$1"
      if [[ "$MODE" == "临时" || "$MODE" == "temporary" || "$MODE" == "ad-hoc" || "$MODE" == "adhoc" ]]; then
        MODE="temp"
      fi
      shift
      ;;
    --show-state|--help|-h)
      exec python3 "$PY" --repo "$ROOT" "$@"
      ;;
  esac
fi

# remaining args
while [[ $# -gt 0 ]]; do
  ARGS+=("$1")
  shift
done

exec python3 "$PY" --repo "$ROOT" --mode "$MODE" "${ARGS[@]+"${ARGS[@]}"}"
