#!/usr/bin/env bash
# Full single-node test suite for an endpoint set up by deploy/setup_node.sh.
# Runs on the node itself (requests go to localhost, so no network cost is
# included), takes about 20 minutes on a 4-vCPU CPU node, and writes
# ~/results/<NAME>/ with report.md plus the raw files.
#
#   1. llama-bench: prefill/decode for the 2B and 0.8B models; thread scaling (CPU)
#   2. cold start: service start until /health, plus the first request, with the
#      model files evicted from the page cache (read from EBS) and still cached
#   3. request-level tests through llama-server (endpoint_test.py)
#   4. peak resident memory of llama-server
#
#   bash run_node_tests.sh C1          (expects endpoint_test.py and ~/data next to it)
set -euo pipefail
NAME=${1:?usage: run_node_tests.sh NAME}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=~/results/$NAME
mkdir -p "$OUT"
source /opt/llm/server.env
BIN=/opt/llm/llama.cpp/build/bin
SMALL=/opt/llm/models/Qwen3.5-0.8B-GGUF/Qwen3.5-0.8B-Q4_K_M.gguf

health() {  # wait up to 10 minutes for /health
  local deadline=$((SECONDS + 600))
  until curl -sf "localhost:$PORT/health" >/dev/null; do
    if [ $SECONDS -ge $deadline ]; then echo "llama-server not healthy after 600 s" >&2; exit 1; fi
    sleep 0.05
  done
}
now() { date +%s.%N; }
elapsed() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.3f", b - a}'; }

echo "== 1. llama-bench"
sudo systemctl stop llama-server
"$BIN/llama-bench" -m "$MODEL_PATH" -t "$THREADS" -ngl 99 -p 128,512,2048 -n 32,128 -r 3 -o md \
  2>/dev/null > "$OUT/bench_2b.md"
"$BIN/llama-bench" -m "$SMALL" -t "$THREADS" -ngl 99 -p 128,512,2048 -n 32,128 -r 3 -o md \
  2>/dev/null > "$OUT/bench_0.8b.md"
if [ "$NGL" = 0 ]; then
  # Thread counts: powers of two up to the vCPU count, plus the physical-core count.
  T=$(for t in 1 2 4 8 16 32 "$THREADS" "$(nproc)"; do
        if [ "$t" -le "$(nproc)" ]; then echo "$t"; fi
      done | sort -n | uniq | paste -sd,)
  "$BIN/llama-bench" -m "$MODEL_PATH" -t "$T" -p 512 -n 128 -r 3 -o md \
    2>/dev/null > "$OUT/bench_threads_2b.md"
fi

echo "== 2. cold start"
: > "$OUT/cold_start.jsonl"
for mode in disk page_cache; do
  for k in 1 2 3; do
    sudo systemctl stop llama-server
    if [ $mode = disk ]; then sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null; fi
    t0=$(now); sudo systemctl start llama-server; health; t1=$(now)
    first=$(curl -s -o /dev/null -w '%{time_total}' "localhost:$PORT/v1/chat/completions" \
      -H 'Content-Type: application/json' \
      -d '{"messages":[{"role":"user","content":"Reply with OK."}],"max_tokens":1,"cache_prompt":false}')
    echo "{\"kind\":\"cold_start\",\"mode\":\"$mode\",\"rep\":$k,\"start_to_health_s\":$(elapsed "$t0" "$t1"),\"first_request_s\":$first}" \
      | tee -a "$OUT/cold_start.jsonl"
  done
done

echo "== 3. request-level tests"
IMAGES=()
if [ -n "${MMPROJ_PATH:-}" ]; then IMAGES=(--image-sizes 256 512 1024); fi  # only if the server takes images
python3 "$HERE/endpoint_test.py" --url "http://localhost:$PORT" --name "$NAME" \
  --data-dir ~/data --out "$OUT/server.jsonl" --summary "$OUT/server.md" "${IMAGES[@]}"

echo "== 4. memory"
PID=$(systemctl show -p MainPID --value llama-server)
grep -E 'VmHWM|VmRSS' "/proc/$PID/status" | tee "$OUT/memory.txt"
free -m >> "$OUT/memory.txt"

echo "== report"
{
  echo "# Endpoint test report: $NAME"
  echo
  echo "Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by Phase2/harness/run_node_tests.sh."
  echo "Server settings: $(grep -E '^(THREADS|NGL|PARALLEL|CTX)=' /opt/llm/server.env | paste -sd' ')."
  echo
  echo '## Node'
  echo
  echo '```'
  cat /opt/llm/node_info.txt
  echo '```'
  echo
  echo '## llama-bench: Qwen3.5-2B Q4_K_M (pp = prefill, tg = decode; tokens/s, mean ± sd of 3 runs)'
  echo
  cat "$OUT/bench_2b.md"
  echo
  echo '## llama-bench: Qwen3.5-0.8B Q4_K_M'
  echo
  cat "$OUT/bench_0.8b.md"
  if [ -f "$OUT/bench_threads_2b.md" ]; then
    echo
    echo '## llama-bench: thread scaling, Qwen3.5-2B'
    echo
    cat "$OUT/bench_threads_2b.md"
  fi
  echo
  echo "## Cold start ($(basename "$MODEL_PATH")$([ -n "${MMPROJ_PATH:-}" ] && echo ' + vision projector'))"
  echo
  echo '`disk`: page cache dropped first, so the model is read from EBS. `page_cache`: files already in memory.'
  echo '`start_to_health_s`: systemctl start until /health answers. `first_request_s`: a 1-token request right after.'
  echo
  echo '| mode | rep | start to health s | first request s |'
  echo '|---|---|---|---|'
  sed -E 's/.*"mode":"([^"]*)","rep":([0-9]+),"start_to_health_s":([0-9.]+),"first_request_s":([0-9.]+).*/| \1 | \2 | \3 | \4 |/' \
    "$OUT/cold_start.jsonl"
  echo
  cat "$OUT/server.md"
  echo
  echo '## Memory (llama-server, after all tests)'
  echo
  echo '```'
  cat "$OUT/memory.txt"
  echo '```'
} > "$OUT/report.md"
echo "done: $OUT/report.md"
