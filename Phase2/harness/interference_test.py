#!/usr/bin/env python3
"""Does a new long prompt stall sequences that are already decoding?

Request A (short prompt, fixed 160-token output) starts alone. Once it is
decoding, request B (a ~2K-token prompt, 8-token output) arrives on the same
endpoint. A's token arrival times show what B's prefill does to A's decode;
B's time to first token shows what A's decode does to B's prefill. Each is
compared with the same request run alone.

    python3 interference_test.py --url http://localhost:8080 --name C1 --data-dir ~/data
"""

import argparse
import http.client
import json
import statistics
import threading
import time
import urllib.parse
from pathlib import Path

from endpoint_test import length_prompt, nonce, user


def stream(url, messages, max_tokens, ignore_eos, out):
    """Streaming chat request; appends each content chunk's arrival time to out['tokens']."""
    u = urllib.parse.urlsplit(url)
    body = json.dumps({"messages": messages, "max_tokens": max_tokens, "temperature": 0,
                       "stream": True, "ignore_eos": ignore_eos, "cache_prompt": False,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    out.update(t_send=time.perf_counter(), tokens=[], timings={})
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=900)
    conn.request("POST", "/v1/chat/completions", body, {"Content-Type": "application/json"})
    for raw in conn.getresponse():
        line = raw.strip()
        if not line.startswith(b"data:") or line[5:].strip() == b"[DONE]":
            continue
        chunk = json.loads(line[5:])
        out["timings"] = chunk.get("timings", out["timings"])
        if any((c.get("delta") or {}).get("content") for c in chunk.get("choices", [])):
            out["tokens"].append(time.perf_counter())
    conn.close()
    out["t_done"] = time.perf_counter()


def gaps(rec):
    ts = [rec["t_send"]] + rec["tokens"]
    return [b - a for a, b in zip(ts, ts[1:])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--a-out", type=int, default=160)
    ap.add_argument("--b-prompt", type=int, default=2048)
    ap.add_argument("--b-after-tokens", type=int, default=20, help="start B once A has this many tokens")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    questions = [json.loads(line)["question"] for line in
                 (Path(args.data_dir).expanduser() / "gsm8k_test_n100_seed0.jsonl").open()]
    msg_a = lambda: user(f"[{nonce()}] Write a long, detailed story about a city on Mars.")
    msg_b = lambda k: user(length_prompt(questions, args.b_prompt, seed=k))

    stream(args.url, user(f"[{nonce()}] Reply with OK."), 2, False, {})  # warm-up

    a_alone, b_alone = {}, {}
    stream(args.url, msg_a(), args.a_out, True, a_alone)
    stream(args.url, msg_b(1), 8, False, b_alone)

    a_mix, b_mix = {}, {}
    ta = threading.Thread(target=stream, args=(args.url, msg_a(), args.a_out, True, a_mix))
    ta.start()
    while len(a_mix.get("tokens", [])) < args.b_after_tokens:
        time.sleep(0.005)
    stream(args.url, msg_b(2), 8, False, b_mix)
    ta.join()

    b_ttft_alone = b_alone["tokens"][0] - b_alone["t_send"]
    b_ttft_mix = b_mix["tokens"][0] - b_mix["t_send"]
    # A's tokens that arrived while B was being prefilled (B sent .. B's first token).
    during = [t for t in a_mix["tokens"] if b_mix["t_send"] <= t <= b_mix["tokens"][0]]
    stall = max(g for g, t in zip(gaps(a_mix), a_mix["tokens"]) if t >= b_mix["t_send"])
    res = {
        "name": args.name,
        "a_step_alone_ms": 1e3 * statistics.median(gaps(a_alone)[1:]),
        "a_e2e_alone_s": a_alone["t_done"] - a_alone["t_send"],
        "a_e2e_mix_s": a_mix["t_done"] - a_mix["t_send"],
        "a_longest_gap_during_b_s": stall,
        "a_tokens_during_b_prefill": len(during),
        "b_prompt_tokens": b_mix["timings"].get("prompt_n"),
        "b_ttft_alone_s": b_ttft_alone,
        "b_ttft_mix_s": b_ttft_mix,
    }
    print(json.dumps(res, indent=2))
    if args.out:
        with open(args.out, "a") as f:
            f.write(json.dumps(res) + "\n")


if __name__ == "__main__":
    main()
