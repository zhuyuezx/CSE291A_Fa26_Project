"""Shared helpers for the Phase 1 harness: an Ollama streaming client,
model and host metadata, and JSONL output."""

import json
import os
import platform
import subprocess
import time
import uuid
from pathlib import Path

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
PHASE1 = Path(__file__).resolve().parents[1]
DATA_DIR = PHASE1 / "data"
RAW_DIR = PHASE1 / "results" / "raw"
SUMMARY_DIR = PHASE1 / "results" / "summary"
FIG_DIR = PHASE1 / "results" / "figures"

_info_cache = {}


def nonce():
    """Short random id placed at the start of every prompt so that Ollama's
    prefix cache never reuses work across measured requests."""
    return uuid.uuid4().hex[:8]


def model_info(model):
    if model not in _info_cache:
        r = requests.post(f"{OLLAMA_URL}/api/show", json={"model": model}, timeout=30)
        r.raise_for_status()
        d = r.json()
        det = d.get("details", {})
        digest = next((m["digest"] for m in list_models() if m["name"] == model), None)
        _info_cache[model] = {
            "model": model,
            "family": det.get("family"),
            "parameter_size": det.get("parameter_size"),
            "quantization": det.get("quantization_level"),
            "capabilities": d.get("capabilities", []),
            "digest": digest,
        }
    return _info_cache[model]


def list_models():
    return requests.get(f"{OLLAMA_URL}/api/tags", timeout=30).json().get("models", [])


def loaded_models():
    """Models currently resident in Ollama, with their memory footprint."""
    out = {}
    for m in requests.get(f"{OLLAMA_URL}/api/ps", timeout=30).json().get("models", []):
        out[m["name"]] = {"size_gb": m.get("size", 0) / 2**30,
                          "size_vram_gb": m.get("size_vram", 0) / 2**30}
    return out


def unload(model, wait_s=60):
    requests.post(f"{OLLAMA_URL}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
    deadline = time.time() + wait_s
    while model in loaded_models() and time.time() < deadline:
        time.sleep(0.5)


def chat(model, prompt, num_predict, images=None, num_ctx=8192, seed=0,
         temperature=0.0, timeout=900):
    """Send one streaming chat request and return its timing record.

    TTFT and end-to-end latency are measured on the client; prefill and decode
    token counts and durations come from Ollama's final stream chunk."""
    info = model_info(model)
    message = {"role": "user", "content": prompt}
    if images:
        message["images"] = images
    body = {
        "model": model,
        "messages": [message],
        "stream": True,
        "keep_alive": "10m",
        "options": {"num_predict": num_predict, "temperature": temperature,
                    "seed": seed, "num_ctx": num_ctx},
    }
    if "thinking" in info["capabilities"]:
        body["think"] = False

    rec = {"model": model, "num_predict": num_predict, "ok": False,
           "t_start": time.time()}
    t0 = time.perf_counter()
    ttft = None
    parts = []
    final = {}
    try:
        with requests.post(f"{OLLAMA_URL}/api/chat", json=body, stream=True,
                           timeout=timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                if "error" in chunk:
                    raise RuntimeError(chunk["error"])
                piece = chunk.get("message", {}).get("content", "")
                if piece and ttft is None:
                    ttft = time.perf_counter() - t0
                parts.append(piece)
                if chunk.get("done"):
                    final = chunk
                    break
        rec["ok"] = True
    except Exception as e:  # recorded, never dropped
        rec["error"] = f"{type(e).__name__}: {e}"
    e2e = time.perf_counter() - t0
    rec["t_end"] = time.time()

    ns = 1e-9
    n_in = final.get("prompt_eval_count") or 0
    n_out = final.get("eval_count") or 0
    prefill_s = final.get("prompt_eval_duration", 0) * ns
    decode_s = final.get("eval_duration", 0) * ns
    rec.update({
        "ttft_s": ttft,
        "e2e_s": e2e,
        "prompt_tokens": n_in,
        "prefill_s": prefill_s,
        "output_tokens": n_out,
        "decode_s": decode_s,
        "load_s": final.get("load_duration", 0) * ns,
        "server_total_s": final.get("total_duration", 0) * ns,
        "done_reason": final.get("done_reason"),
        "prefill_tps": n_in / prefill_s if prefill_s > 0 else None,
        # A 1-token reply has no meaningful decode phase.
        "decode_tps": n_out / decode_s if decode_s > 0 and n_out > 1 else None,
        "tpot_ms": 1000 * decode_s / n_out if decode_s > 0 and n_out > 1 else None,
        "client_tpot_ms": (1000 * (e2e - ttft) / (n_out - 1)
                           if ttft is not None and n_out > 1 else None),
        "text": "".join(parts),
        "family": info["family"],
        "parameter_size": info["parameter_size"],
        "quantization": info["quantization"],
    })
    return rec


def host_metadata():
    def sysctl(key):
        try:
            return subprocess.run(["sysctl", "-n", key], capture_output=True,
                                  text=True).stdout.strip()
        except OSError:
            return None
    mem = sysctl("hw.memsize")
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "chip": sysctl("machdep.cpu.brand_string"),
        "mem_gb": int(mem) / 2**30 if mem else None,
        "perf_cores": sysctl("hw.perflevel0.physicalcpu"),
        "eff_cores": sysctl("hw.perflevel1.physicalcpu"),
        "ollama_version": requests.get(f"{OLLAMA_URL}/api/version", timeout=10).json().get("version"),
        "python": platform.python_version(),
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def write_meta(path, **extra):
    """Append host and model metadata for this invocation to the JSON list
    stored next to a raw result file."""
    meta = {"host": host_metadata(), **extra}
    if "models" in extra:
        meta["model_info"] = [model_info(m) for m in extra["models"]]
    meta_path = Path(path).with_suffix(".meta.json")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    runs = json.loads(meta_path.read_text()) if meta_path.exists() else []
    meta_path.write_text(json.dumps(runs + [meta], indent=2))


def append_jsonl(path, rec):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
