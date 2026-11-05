"""Theoretical speed and memory cost of a model from its config alone.

Roofline model on one device:
  prefill time  = max(prefill FLOPs / peak FLOP/s, weight bytes / bandwidth)
  decode TPOT   = max(bytes read per token / bandwidth, FLOPs per token / peak)
  memory        = weight file + KV cache at num_ctx + linear-attention state
  load time     = weight file / SSD read bandwidth

Bytes read per decode token cover the active weights (all layers, the active
experts only for MoE, and the LM head; not the vision encoder) plus the KV
cache of full-attention layers. Compute buffers and runtime overheads are not
modeled; compare_theory.py measures how far reality is from this bound.

    python Phase1/harness/theory.py            # table for every configured model
"""

import json

from common import PHASE1

CONFIG_DIR = PHASE1 / "configs"
KV_BYTES = 2      # f16 KV cache
STATE_BYTES = 4   # f32 recurrent state


def load_configs():
    models = json.loads((CONFIG_DIR / "models.json").read_text())
    hw = json.loads((CONFIG_DIR / "hardware.json").read_text())
    return {m["name"]: m for m in models}, hw


def derived(cfg):
    """Parameter and byte counts that the roofline needs."""
    embed = cfg["vocab_size"] * cfg["hidden_size"]
    v = cfg.get("vision")
    vision = v["depth"] * (4 * v["hidden_size"] ** 2
                           + 2 * v["hidden_size"] * v["intermediate_size"]) if v else 0
    moe = cfg.get("moe")
    inactive = ((moe["num_experts"] - moe["experts_per_token"]) * 3 * cfg["hidden_size"]
                * moe["expert_intermediate_size"] * cfg["num_layers"]) if moe else 0
    active_text = cfg["params_total"] - vision - inactive
    # Decode reads the LM head but only one row of the input embedding.
    decode_params = active_text - (0 if cfg["tie_word_embeddings"] else embed)
    # Prefill multiplies every prompt token through the layers; the LM head
    # runs on the last token only.
    prefill_params = active_text - embed * (1 if cfg["tie_word_embeddings"] else 2)
    lin = cfg.get("linear_attention")
    state = (lin["num_layers"] * lin["num_value_heads"] * lin["key_head_dim"]
             * lin["value_head_dim"] * STATE_BYTES) if lin else 0
    return {
        "params_vision": vision,
        "params_inactive_experts": inactive,
        "params_active_text": active_text,
        "params_decode": decode_params,
        "params_prefill": prefill_params,
        "bytes_per_param": cfg["file_bytes"] / cfg["params_total"],
        "kv_bytes_per_token_full": 2 * cfg["num_kv_heads"] * cfg["head_dim"] * KV_BYTES,
        "state_bytes": state,
    }


def kv_bytes(cfg, ctx):
    """KV cache bytes for `ctx` tokens of context."""
    per_layer = 2 * cfg["num_kv_heads"] * cfg["head_dim"] * KV_BYTES
    total = cfg["num_full_attention_layers"] * per_layer * ctx
    sw = cfg.get("sliding_window")
    if sw:
        total += sw["num_layers"] * per_layer * min(ctx, sw["window"])
    return total


def estimate(cfg, hw, prompt_tokens, output_tokens, num_ctx=8192):
    d = derived(cfg)
    bw = hw["mem_bandwidth_GBps"] * 1e9
    flops = hw["peak_tflops"] * 1e12
    p, o = prompt_tokens, output_tokens
    attn_dim = cfg["num_attention_heads"] * cfg["head_dim"]

    prefill_flops = 2 * d["params_prefill"] * p
    prefill_flops += 2 * cfg["num_full_attention_layers"] * attn_dim * p * p  # causal QK^T and AV
    sw = cfg.get("sliding_window")
    if sw:
        prefill_flops += 4 * sw["num_layers"] * attn_dim * p * min(p, sw["window"])
    weight_bytes_active = d["bytes_per_param"] * d["params_decode"]
    prefill_s = max(prefill_flops / flops, weight_bytes_active / bw)

    ctx_mid = p + o / 2  # average context length while decoding
    decode_bytes = weight_bytes_active + kv_bytes(cfg, ctx_mid) + 2 * d["state_bytes"]
    decode_flops = 2 * d["params_decode"] + 4 * cfg["num_full_attention_layers"] * attn_dim * ctx_mid
    tpot_s = max(decode_bytes / bw, decode_flops / flops)

    memory = cfg["file_bytes"] + kv_bytes(cfg, num_ctx) + d["state_bytes"]
    return {
        "prefill_s": prefill_s,
        "prefill_tps": p / prefill_s,
        "tpot_ms": 1000 * tpot_s,
        "decode_tps": 1 / tpot_s,
        "ttft_s": prefill_s + tpot_s,
        "e2e_s": prefill_s + o * tpot_s,
        "memory_gb": memory / 2**30,
        "load_s": cfg["file_bytes"] / (hw["ssd_read_GBps"] * 1e9),
        "decode_bound": "memory" if decode_bytes / bw >= decode_flops / flops else "compute",
        "prefill_bound": "compute" if prefill_flops / flops >= weight_bytes_active / bw else "memory",
    }


def main():
    models, hw = load_configs()
    print(f"Device: {hw['name']}  (prompt 512, output 256, num_ctx 8192)\n")
    print(f"{'model':<16}{'active B':>9}{'decode GB/tok':>14}{'prefill tok/s':>14}"
          f"{'decode tok/s':>13}{'memory GB':>10}{'load s':>8}")
    for name, cfg in models.items():
        d = derived(cfg)
        e = estimate(cfg, hw, 512, 256)
        print(f"{name:<16}{d['params_active_text'] / 1e9:>9.2f}"
              f"{d['bytes_per_param'] * d['params_decode'] / 1e9:>14.2f}"
              f"{e['prefill_tps']:>14.0f}{e['decode_tps']:>13.1f}{e['memory_gb']:>10.2f}"
              f"{e['load_s']:>8.2f}")


if __name__ == "__main__":
    main()
