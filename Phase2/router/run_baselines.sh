#!/usr/bin/env bash
# Compare routing policies on one fixed, seeded request trace. For each policy:
# start the router, replay the trace through it, stop the router. Then
# summarize everything into one table. Run on the router node, holding the fleet:
#
#   fleet-run <your-name> bash ~/phase2/router/run_baselines.sh --endpoints "C1 C2" --rate 0.2 --n 30
#
# Options: --endpoints "C1 C2"  --rate 0.2  --n 30  --pattern poisson|bursty
#          --mix T1=0.5,T2=0.25,T3=0.25  --seed 0  --policies "random round_robin"
# Output: ~/runs/baselines_<UTC time>/ with client_*.jsonl, router_*.jsonl, summary.md.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
PY=/opt/fleet/venv/bin/python
ENDPOINTS="C1 C2"; RATE=0.2; N=30; PATTERN=poisson; SEED=0; POLICIES=""
MIX="T1=0.5,T2=0.25,T3=0.25"; PORT=9000
while [ $# -gt 0 ]; do
  case $1 in
    --endpoints) ENDPOINTS=$2; shift 2 ;;
    --rate) RATE=$2; shift 2 ;;
    --n) N=$2; shift 2 ;;
    --pattern) PATTERN=$2; shift 2 ;;
    --mix) MIX=$2; shift 2 ;;
    --seed) SEED=$2; shift 2 ;;
    --policies) POLICIES=$2; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
if [ -z "$POLICIES" ]; then
  POLICIES="$(for e in $ENDPOINTS; do printf 'always:%s ' "$e"; done)random round_robin least_outstanding first_idle"
fi

OUT=~/runs/baselines_$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$OUT"
printf 'endpoints=%s\nrate=%s\nn=%s\npattern=%s\nmix=%s\nseed=%s\npolicies=%s\n' \
  "$ENDPOINTS" "$RATE" "$N" "$PATTERN" "$MIX" "$SEED" "$POLICIES" > "$OUT/config.txt"
echo "writing $OUT"

for p in $POLICIES; do
  tag=${p/:/-}
  # shellcheck disable=SC2086  # endpoint names are separate arguments
  $PY "$HERE/router.py" --endpoints $ENDPOINTS --policy "$p" --seed "$SEED" --port $PORT \
    --log "$OUT/router_$tag.jsonl" > "$OUT/router_$tag.out" 2>&1 &
  RPID=$!
  for _ in $(seq 100); do curl -sf "localhost:$PORT/health" >/dev/null && break; sleep 0.1; done
  curl -sf "localhost:$PORT/health" >/dev/null || { echo "router did not start:"; cat "$OUT/router_$tag.out"; exit 1; }
  $PY "$HERE/loadgen.py" --url "http://localhost:$PORT" --rate "$RATE" --n "$N" --pattern "$PATTERN" \
    --mix "$MIX" --seed "$SEED" --tag "$p" --out "$OUT/client_$tag.jsonl"
  kill $RPID; wait $RPID 2>/dev/null || true
  sleep 5   # let the endpoints settle before the next policy
done

$PY "$HERE/summarize.py" "$OUT"/client_*.jsonl --routers "$OUT"/router_*.jsonl | tee "$OUT/summary.md"
