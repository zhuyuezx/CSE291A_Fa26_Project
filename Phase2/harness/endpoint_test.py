#!/usr/bin/env python3
"""Request-level tests against one llama-server endpoint.

  single      one request at a time over a prompt-length x output-length grid
  concurrent  N simultaneous requests (prompt 512, output 128), N = 1, 2, 4, 8
  image       one bar-chart image per --image-sizes value (off by default; needs a
              server started with a vision projector)

TTFT and end-to-end latency are measured on the client. Prefill and decode
token counts and durations come from the server's `timings` field. Every
prompt starts with a random nonce and sets cache_prompt=false, so no request
reuses another's prefill. Text requests set ignore_eos, so they generate exactly
max_tokens tokens. Uses only the standard library, so it runs on a fresh node.

    python3 endpoint_test.py --url http://localhost:8080 --name C1 \
        --data-dir ~/data --out server.jsonl --summary server.md
"""

import argparse
import base64
import http.client
import json
import random
import re
import statistics
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CHARS_PER_TOKEN = 4.0  # rough; the actual prompt token count is recorded


def nonce():
    return uuid.uuid4().hex[:8]


def chat(url, messages, max_tokens, ignore_eos=True, timeout=900):
    """Send one streaming chat request and return its timing record."""
    u = urllib.parse.urlsplit(url)
    body = json.dumps({
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "ignore_eos": ignore_eos,
        "cache_prompt": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    rec = {"ok": False, "max_tokens": max_tokens, "ignore_eos": ignore_eos,
           "t_start": time.time()}
    t0 = time.perf_counter()
    ttft, timings, parts = None, {}, []
    try:
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
        conn.request("POST", "/v1/chat/completions", body,
                     {"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {resp.read()[:300]!r}")
        for raw in resp:
            line = raw.strip()
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                break
            chunk = json.loads(data)
            if "timings" in chunk:
                timings = chunk["timings"]
            for choice in chunk.get("choices", []):
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    parts.append(piece)
        conn.close()
        rec["ok"] = True
    except Exception as e:  # recorded, never dropped
        rec["error"] = f"{type(e).__name__}: {e}"
    e2e = time.perf_counter() - t0
    rec["t_end"] = time.time()

    pn, pms = timings.get("prompt_n"), timings.get("prompt_ms")
    on, oms = timings.get("predicted_n"), timings.get("predicted_ms")
    rec.update({
        "ttft_s": ttft,
        "e2e_s": e2e,
        "prompt_tokens": pn,
        "prefill_s": pms / 1000 if pms else None,
        "output_tokens": on,
        "decode_s": oms / 1000 if oms else None,
        "prefill_tps": 1000 * pn / pms if pn and pms else None,
        "decode_tps": 1000 * on / oms if on and oms and on > 1 else None,
        "tpot_ms": oms / on if on and oms and on > 1 else None,
        "text": "".join(parts)[:200],
    })
    return rec


def length_prompt(questions, target_tokens, seed):
    """About target_tokens tokens of GSM8K problem text, then a writing task
    (same construction as Phase 1's workloads.length_prompt)."""
    qs = questions[:]
    random.Random(seed).shuffle(qs)
    header = f"[request {nonce()}] Below are several word problems.\n\n"
    tail = "\nTask: Write a long, detailed, multi-paragraph story inspired by these problems."
    body, i = "", 0
    while len(header) + len(body) + len(tail) < target_tokens * CHARS_PER_TOKEN:
        body += f"Problem {i + 1}: {qs[i % len(qs)]}\n\n"
        i += 1
    return header + body + tail


def chart_answer(seed):
    """Tallest bar of Phase 1's chart_image(size, seed); the values depend only on the seed."""
    labels = ["A", "B", "C", "D", "E"]
    values = random.Random(seed).sample(range(2, 20), len(labels))
    return labels[values.index(max(values))]


def user(content):
    return [{"role": "user", "content": content}]


# ---------------------------------------------------------------- summary

def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def fmt(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def summarize(recs, name, url):
    md = [f"## Request-level tests: {name} ({url})", ""]
    n_fail = sum(not r["ok"] for r in recs)
    md.append(f"{len(recs)} requests, {n_fail} failed or timed out.")
    short = [r for r in recs if r["ok"] and r.get("ignore_eos")
             and r.get("output_tokens") != r["max_tokens"]]
    if short:
        md.append(f"{len(short)} fixed-length requests returned a different token count than max_tokens.")
    md.append("")

    single = [r for r in recs if r["kind"] == "single" and r["ok"]]
    if single:
        rows = []
        for p in sorted({r["target_prompt"] for r in single}):
            for o in sorted({r["target_output"] for r in single}):
                g = [r for r in single if r["target_prompt"] == p and r["target_output"] == o]
                if not g:
                    continue
                rows.append([p, o, fmt(med(r["prompt_tokens"] for r in g), 0),
                             fmt(med(r["ttft_s"] for r in g)),
                             fmt(med(r["prefill_tps"] for r in g), 1),
                             fmt(med(r["decode_tps"] for r in g), 1),
                             fmt(med(r["e2e_s"] for r in g)), len(g)])
        md += ["### One request at a time (medians)", "",
               table(["target prompt", "output tokens", "prompt tokens", "TTFT s",
                      "prefill tok/s", "decode tok/s", "end-to-end s", "runs"], rows), ""]

    conc = [r for r in recs if r["kind"] == "concurrent" and r["ok"]]
    if conc:
        rows, base = [], None
        for n in sorted({r["conc"] for r in conc}):
            g = [r for r in conc if r["conc"] == n]
            tput = []
            for k in sorted({r["rep"] for r in g}):
                batch = [r for r in g if r["rep"] == k]
                span = max(r["t_end"] for r in batch) - min(r["t_start"] for r in batch)
                tput.append(sum(r["output_tokens"] or 0 for r in batch) / span)
            t = med(tput)
            base = base or t
            rows.append([n, fmt(med(r["ttft_s"] for r in g)), fmt(max(r["ttft_s"] or 0 for r in g)),
                         fmt(med(r["e2e_s"] for r in g)), fmt(med(r["decode_tps"] for r in g), 1),
                         fmt(t, 1), fmt(t / base if base else None)])
        p = conc[0]["target_prompt"]
        o = conc[0]["target_output"]
        md += [f"### Concurrent requests (prompt {p}, output {o}; server has a fixed number of slots)", "",
               table(["requests", "median TTFT s", "max TTFT s", "median end-to-end s",
                      "per-request decode tok/s", "throughput (output tok/s)", "vs. 1 request"], rows), "",
               "Throughput = all output tokens / wall time from first send to last reply. "
               "Requests beyond the slot count wait in the server's queue, which shows up in TTFT.", ""]

    img = [r for r in recs if r["kind"] == "image"]
    if img:
        rows = []
        for px in sorted({r["image_px"] for r in img}):
            g = [r for r in img if r["image_px"] == px]
            ok = [r for r in g if r["ok"]]
            rows.append([px, fmt(med(r["prompt_tokens"] for r in ok), 0),
                         fmt(med(r["ttft_s"] for r in ok)),
                         fmt(med(r["prefill_s"] for r in ok)),
                         fmt(med(r["e2e_s"] for r in ok)),
                         f"{sum(bool(r.get('correct')) for r in g)}/{len(g)}"])
        md += ["### Image requests (bar chart, \"which bar is tallest?\")", "",
               table(["image px", "prompt tokens", "TTFT s", "prefill s (incl. vision)",
                      "end-to-end s", "correct"], rows), ""]
    return "\n".join(md)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--name", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--prompts", nargs="+", type=int, default=[128, 512, 2048])
    ap.add_argument("--outputs", nargs="+", type=int, default=[32, 256])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--conc", nargs="+", type=int, default=[1, 2, 4, 8])
    ap.add_argument("--conc-reps", type=int, default=2)
    ap.add_argument("--conc-prompt", type=int, default=512)
    ap.add_argument("--conc-output", type=int, default=128)
    ap.add_argument("--image-sizes", nargs="*", type=int, default=[],
                    help="e.g. 256 512 1024; empty (default) skips image tests")
    args = ap.parse_args()

    data = Path(args.data_dir).expanduser()
    questions = [json.loads(line)["question"]
                 for line in (data / "gsm8k_test_n100_seed0.jsonl").read_text().splitlines()
                 if line.strip()]
    recs = []
    out = open(args.out, "w")

    def log(rec, **fields):
        rec.update(fields, name=args.name, url=args.url)
        recs.append(rec)
        out.write(json.dumps(rec) + "\n")
        out.flush()
        status = "ok" if rec["ok"] else rec.get("error")
        print(f"{fields} ttft={fmt(rec['ttft_s'])} e2e={fmt(rec['e2e_s'])} "
              f"prompt={rec['prompt_tokens']} out={rec['output_tokens']} {status}", flush=True)

    chat(args.url, user(f"[{nonce()}] Reply with OK."), 4)  # warm-up, not recorded

    for p in args.prompts:
        for o in args.outputs:
            for k in range(args.reps):
                rec = chat(args.url, user(length_prompt(questions, p, seed=k)), o)
                log(rec, kind="single", target_prompt=p, target_output=o, rep=k)

    for n in args.conc:
        for k in range(args.conc_reps):
            prompts = [length_prompt(questions, args.conc_prompt, seed=100 * k + i) for i in range(n)]
            with ThreadPoolExecutor(max_workers=n) as pool:
                batch = list(pool.map(lambda pr: chat(args.url, user(pr), args.conc_output), prompts))
            for i, rec in enumerate(batch):
                log(rec, kind="concurrent", conc=n, rep=k, idx=i,
                    target_prompt=args.conc_prompt, target_output=args.conc_output)

    for px in args.image_sizes:
        for k in range(args.reps):
            path = data / "images" / f"chart_{px}px_seed{k}.png"
            b64 = base64.b64encode(path.read_bytes()).decode()
            content = [
                {"type": "text", "text": f"[{nonce()}] Which bar in this chart is the tallest? "
                                         "Reply with the letter only."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]
            rec = chat(args.url, user(content), 8, ignore_eos=False)
            m = re.search(r"\b([A-E])\b", rec["text"])
            answer = chart_answer(k)
            log(rec, kind="image", image_px=px, rep=k, answer=answer,
                correct=bool(m) and m.group(1) == answer)

    out.close()
    Path(args.summary).write_text(summarize(recs, args.name, args.url) + "\n")


if __name__ == "__main__":
    main()
