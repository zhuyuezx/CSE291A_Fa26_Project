#!/usr/bin/env bash
# Turn a fresh Ubuntu (24.04 or 26.04) EC2 instance into an inference endpoint:
#   1. build llama.cpp at a pinned tag (native CPU kernels, or CUDA if an
#      NVIDIA GPU with a working driver is visible),
#   2. download SHA-256-checked Qwen3.5 GGUF files,
#   3. run llama-server as a systemd service on port 8080,
#   4. record the node's hardware and software in /opt/llm/node_info.txt.
#
#   scp -i team.pem Phase2/deploy/setup_node.sh ubuntu@<public-ip>:
#   ssh -i team.pem ubuntu@<public-ip> 'bash setup_node.sh'
#
# Re-running is safe: the clone, build, and verified downloads are reused.
# Server settings live in /opt/llm/server.env; edit it, then
# `sudo systemctl restart llama-server`.
#
# Overrides (environment): LLAMA_TAG, SERVE, DOWNLOAD, PORT, PARALLEL, CTX, VISION.
set -euo pipefail

LLAMA_TAG="${LLAMA_TAG:-b12617}"              # must be identical on every node
SERVE="${SERVE:-qwen3.5-2b}"                  # model the server loads
DOWNLOAD="${DOWNLOAD:-qwen3.5-0.8b qwen3.5-2b}"  # models staged on disk
PORT="${PORT:-8080}"
PARALLEL="${PARALLEL:-4}"   # server slots = requests decoded concurrently
CTX="${CTX:-16384}"         # total KV context, shared by all slots (unified KV)
# 1 = also download and load the vision projector (image input). Text-only by
# default: images are out of scope for now, and 2B + projector does not fit G1's 3 GB GPU.
VISION="${VISION:-0}"
ROOT=/opt/llm
SRC=$ROOT/llama.cpp

# Q4_K_M weights and F16 vision projector from unsloth/Qwen3.5-*-GGUF.
# Hashes are the Hugging Face LFS SHA-256 values (checked 2026-11-21).
model_vars() {
  case "$1" in
    qwen3.5-0.8b) REPO=unsloth/Qwen3.5-0.8B-GGUF; GGUF=Qwen3.5-0.8B-Q4_K_M.gguf
      GSHA=bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517
      MSHA=56e4c6cfe73b0c82e3e82bc518d7591997e61d81f723fc41a586f4fa69ea2453 ;;
    qwen3.5-2b) REPO=unsloth/Qwen3.5-2B-GGUF; GGUF=Qwen3.5-2B-Q4_K_M.gguf
      GSHA=aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223
      MSHA=7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7 ;;
    qwen3.5-4b) REPO=unsloth/Qwen3.5-4B-GGUF; GGUF=Qwen3.5-4B-Q4_K_M.gguf
      GSHA=00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4
      MSHA=cd88edcf8d031894960bb0c9c5b9b7e1fea6ebee02b9f7ce925a00d12891f864 ;;
    *) echo "unknown model: $1" >&2; exit 1 ;;
  esac
  MDIR="$ROOT/models/${REPO#*/}"
}

fetch() {  # fetch <repo> <file> <sha256> <dir>
  local repo=$1 file=$2 sha=$3 dir=$4 out="$4/$2"
  mkdir -p "$dir"
  if [ -f "$out" ] && echo "$sha  $out" | sha256sum -c --status; then
    echo "  have $file"; return
  fi
  echo "  downloading $repo/$file"
  curl -fL --retry 3 -o "$out.part" "https://huggingface.co/$repo/resolve/main/$file"
  if ! echo "$sha  $out.part" | sha256sum -c --status; then
    echo "SHA-256 mismatch for $repo/$file" >&2; exit 1
  fi
  mv "$out.part" "$out"
}

imds() {  # EC2 instance metadata (IMDSv2)
  local t
  t=$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token \
        -H 'X-aws-ec2-metadata-token-ttl-seconds: 60') || return 0
  curl -s -m 2 -H "X-aws-ec2-metadata-token: $t" \
    "http://169.254.169.254/latest/meta-data/$1" || true
}

echo "== packages"
APT=(sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600)
"${APT[@]}" update -y
"${APT[@]}" install -y build-essential cmake git curl libssl-dev pciutils
# Background package upgrades add CPU noise to measurements on short-lived lab nodes.
sudo systemctl disable --now unattended-upgrades 2>/dev/null || true

echo "== hardware"
GPU=0
if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  GPU=1
elif lspci | grep -qi nvidia; then
  echo "An NVIDIA GPU is attached but nvidia-smi does not work. Install the driver" >&2
  echo "first (g6f needs the NVIDIA GRID driver; see Phase2/deploy/README.md)." >&2
  exit 1
fi
CORES=$(lscpu -p=Core,Socket | grep -v '^#' | sort -u | wc -l)
echo "arch=$(uname -m) vcpus=$(nproc) physical_cores=$CORES gpu=$GPU"

echo "== llama.cpp $LLAMA_TAG"
sudo mkdir -p $ROOT && sudo chown "$(id -u):$(id -g)" $ROOT
if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 --branch "$LLAMA_TAG" https://github.com/ggml-org/llama.cpp "$SRC"
fi
HAVE=$(git -C "$SRC" describe --tags --exact-match 2>/dev/null || echo unknown)
if [ "$HAVE" != "$LLAMA_TAG" ]; then
  echo "$SRC is at $HAVE, not $LLAMA_TAG. Remove it and re-run." >&2; exit 1
fi
FLAGS=(-DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF)
if [ $GPU = 1 ]; then
  export PATH=/usr/local/cuda/bin:$PATH
  command -v nvcc >/dev/null || { echo "CUDA toolkit (nvcc) not found" >&2; exit 1; }
  CC=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1 | tr -d '. ')
  FLAGS+=(-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CC")  # this GPU only: faster build
  NGL=all
else
  NGL=0   # GGML_NATIVE (default ON) picks this CPU's ISA: SVE/i8mm on Graviton, AVX-512/AMX on Xeon
fi
if [ ! -x "$SRC/build/bin/llama-server" ]; then
  cmake -S "$SRC" -B "$SRC/build" "${FLAGS[@]}"
  cmake --build "$SRC/build" --config Release -j "$(nproc)" --target llama-server llama-bench
fi

echo "== models"
for m in $DOWNLOAD $SERVE; do
  model_vars "$m"
  fetch "$REPO" "$GGUF" "$GSHA" "$MDIR"
  if [ "$VISION" = 1 ]; then fetch "$REPO" mmproj-F16.gguf "$MSHA" "$MDIR"; fi
done
model_vars "$SERVE"
MMPROJ=""
if [ "$VISION" = 1 ]; then MMPROJ="$MDIR/mmproj-F16.gguf"; fi

echo "== service"
cat > $ROOT/server.env <<EOF
# Read by $ROOT/run-server.sh. Edit, then: sudo systemctl restart llama-server
MODEL_PATH=$MDIR/$GGUF
# Empty = text-only; set to an mmproj file to accept images.
MMPROJ_PATH=$MMPROJ
PORT=$PORT
THREADS=$CORES
NGL=$NGL
PARALLEL=$PARALLEL
CTX=$CTX
EXTRA_ARGS=""
EOF

# --cache-ram 0: no cross-request prompt cache, so measurements never reuse
#   another request's prefill (and an 8 GiB node is not pushed into swap).
# enable_thinking=false: matches Phase 1, where thinking was off.
cat > $ROOT/run-server.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source /opt/llm/server.env
VISION_ARGS=()
if [ -n "${MMPROJ_PATH:-}" ]; then VISION_ARGS=(--mmproj "$MMPROJ_PATH"); fi
exec /opt/llm/llama.cpp/build/bin/llama-server \
  -m "$MODEL_PATH" "${VISION_ARGS[@]}" \
  --host 0.0.0.0 --port "$PORT" \
  -t "$THREADS" -ngl "$NGL" -np "$PARALLEL" -c "$CTX" --kv-unified \
  --cache-ram 0 --metrics \
  --chat-template-kwargs '{"enable_thinking": false}' \
  $EXTRA_ARGS
EOF
chmod +x $ROOT/run-server.sh

sudo tee /etc/systemd/system/llama-server.service >/dev/null <<EOF
[Unit]
Description=llama-server inference endpoint (CSE 291A)
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
ExecStart=$ROOT/run-server.sh
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable llama-server >/dev/null
sudo systemctl restart llama-server

echo "== node info"
{
  echo "instance_type=$(imds instance-type)"
  echo "availability_zone=$(imds placement/availability-zone)"
  echo "private_ip=$(imds local-ipv4)"
  echo "arch=$(uname -m)"
  echo "cpu=$(lscpu | sed -n 's/^Model name: *//p' | head -1)"
  echo "vcpus=$(nproc)"
  echo "physical_cores=$CORES"
  echo "mem_total_gib=$(free -g | awk '/^Mem:/{print $2}')"
  if [ $GPU = 1 ]; then
    echo "gpu=$(nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv,noheader | head -1)"
  fi
  echo "os=$(. /etc/os-release && echo "$PRETTY_NAME")"
  echo "kernel=$(uname -r)"
  echo "compiler=$(gcc --version | head -1)"
  if [ $GPU = 1 ]; then echo "nvcc=$(nvcc --version | tail -1)"; fi
  echo "llama_tag=$LLAMA_TAG"
  echo "llama_commit=$(git -C "$SRC" rev-parse --short HEAD)"
  echo "serve_model=$GGUF"
  echo "serve_model_sha256=$GSHA"
  echo "vision=$VISION"
  if [ "$VISION" = 1 ]; then echo "mmproj_sha256=$MSHA"; fi
  echo "setup_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} | tee $ROOT/node_info.txt

echo "== waiting for llama-server on :$PORT"
for _ in $(seq 120); do
  if curl -sf "http://localhost:$PORT/health" >/dev/null; then
    echo "ready. Logs: journalctl -u llama-server -f"
    exit 0
  fi
  sleep 2
done
echo "llama-server did not become healthy. Check: journalctl -u llama-server -n 100" >&2
exit 1
