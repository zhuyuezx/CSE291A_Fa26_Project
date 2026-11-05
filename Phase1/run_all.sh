#!/usr/bin/env bash
# Run every Phase 1 experiment against a local Ollama server, then analyze.
# Models that are not installed (`ollama pull <model>`) are skipped.
set -euo pipefail
cd "$(dirname "$0")/harness"

installed() {
  local out=()
  for m in "$@"; do
    if curl -s "${OLLAMA_URL:-http://localhost:11434}/api/tags" | grep -q "\"name\":\"$m\""; then
      out+=("$m")
    else
      echo "skipping $m (not installed)" >&2
    fi
  done
  echo "${out[@]}"
}

# E1/E4: isolated profiles and cold start.
python3 run_profile.py --models $(installed qwen3.5:0.8b gemma3:1b qwen3-vl:4b qwen3.5:35b qwen3.5:2b)

# E5: GSM8K tier labels.
python3 run_quality.py --n 100 --models $(installed qwen3.5:0.8b gemma3:1b qwen3-vl:4b qwen3.5:35b qwen3.5:2b)

# E2: open-loop load curves on the smallest Qwen3.5 model.
python3 run_load.py --model qwen3.5:0.8b --rates 0.5 1 2 4 --n 30

# Offline routing simulation: small model -> large model.
for small in $(installed qwen3.5:0.8b gemma3:1b qwen3.5:2b qwen3-vl:4b); do
  python3 route_sim.py --small "$small" --large qwen3.5:35b
done

python3 analyze.py
