"""Open-loop load generator for router experiments.

Builds a seeded trace (arrival times and request classes) and replays it
against a URL: the router, or one endpoint directly. The same --seed gives the
same trace, so every policy is measured on identical work. Arrivals are
open-loop: a slow system does not slow arrivals down, so queueing shows up in
latency. `poisson` uses exponential gaps; `bursty` uses gamma gaps with the same
mean and coefficient of variation --cv.

    /opt/fleet/venv/bin/python loadgen.py --url http://localhost:9000 --rate 0.2 --n 30 \
        --tag round_robin --out client.jsonl
"""

import argparse
import asyncio
import json
import random
import time
import uuid

import aiohttp

from workloads import CLASSES, build_payload, load_data


def parse_mix(s):
    mix = {k: float(v) for k, v in (part.split("=") for part in s.split(","))}
    unknown = set(mix) - set(CLASSES)
    if unknown:
        raise SystemExit(f"unknown classes in --mix: {sorted(unknown)}; known: {sorted(CLASSES)}")
    return mix


def make_trace(n, rate, pattern, cv, mix, seed):
    rng = random.Random(seed)
    names, weights = list(mix), list(mix.values())
    t, trace = 0.0, []
    for i in range(n):
        if pattern == "poisson":
            t += rng.expovariate(rate)
        else:
            shape = 1.0 / cv ** 2
            t += rng.gammavariate(shape, 1.0 / (rate * shape))
        trace.append({"i": i, "t_arrival": t, "cls": rng.choices(names, weights)[0],
                      "seed": rng.randrange(10 ** 6)})
    return trace


async def send(session, url, item, t0, tag, out):
    await asyncio.sleep(max(0.0, t0 + item["t_arrival"] - time.time()))
    rec = {"tag": tag, "i": item["i"], "cls": item["cls"], "t_arrival": item["t_arrival"],
           "id": uuid.uuid4().hex, "ok": False}
    ttft, timings, text = None, {}, []
    start = time.perf_counter()
    rec["t_send_epoch"] = time.time()
    try:
        async with session.post(f"{url}/v1/chat/completions", json=item["payload"],
                                headers={"X-Request-Id": rec["id"]}) as r:
            rec["status"] = r.status
            rec["routed_to"] = r.headers.get("X-Routed-To")
            if r.status != 200:
                rec["error"] = (await r.text())[:300]
            else:
                async for raw in r.content:
                    if "t_first_byte_epoch" not in rec:
                        rec["t_first_byte_epoch"] = time.time()
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
                                ttft = time.perf_counter() - start
                            text.append(piece)
                rec["ok"] = True
    except Exception as e:  # recorded, never dropped
        rec["error"] = f"{type(e).__name__}: {e}"
    rec["e2e_s"] = time.perf_counter() - start
    rec["t_done_epoch"] = time.time()
    rec.update({
        "queue_delay_s": rec["t_send_epoch"] - (t0 + item["t_arrival"]),  # client lateness, should be ~0
        "ttft_s": ttft,
        "prompt_tokens": timings.get("prompt_n"),
        "prefill_s": (timings.get("prompt_ms") or 0) / 1000 or None,
        "output_tokens": timings.get("predicted_n"),
        "decode_s": (timings.get("predicted_ms") or 0) / 1000 or None,
        "text": "".join(text)[:80],
    })
    out.write(json.dumps(rec) + "\n")
    out.flush()
    return rec


async def run(args):
    data = load_data(args.data_dir)
    trace = make_trace(args.n, args.rate, args.pattern, args.cv, parse_mix(args.mix), args.seed)
    for item in trace:  # build every body up front so the client does no work during the run
        item["payload"] = build_payload(item["cls"], item["seed"], data)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=1800)
    with open(args.out, "a") as out:
        async with aiohttp.ClientSession(timeout=timeout,
                                         connector=aiohttp.TCPConnector(limit=0)) as session:
            t0 = time.time() + 1.0
            recs = await asyncio.gather(*(send(session, args.url, item, t0, args.tag, out)
                                          for item in trace))
    ok = [r for r in recs if r["ok"]]
    span = max(r["t_done_epoch"] for r in recs) - min(r["t_send_epoch"] for r in recs)
    routed = {}
    for r in recs:
        routed[r.get("routed_to")] = routed.get(r.get("routed_to"), 0) + 1
    mean = sum(r["e2e_s"] for r in ok) / len(ok) if ok else float("nan")
    print(f"{args.tag}: {len(ok)}/{len(recs)} ok in {span:.0f}s, mean e2e {mean:.1f}s, routed {routed}",
          flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:9000")
    ap.add_argument("--rate", type=float, required=True, help="mean arrivals per second")
    ap.add_argument("--n", type=int, required=True, help="number of requests")
    ap.add_argument("--pattern", choices=["poisson", "bursty"], default="poisson")
    ap.add_argument("--cv", type=float, default=3.0, help="coefficient of variation for bursty")
    ap.add_argument("--mix", default="T1=0.5,T2=0.25,T3=0.25",
                    help="class=weight,...  classes: " + "; ".join(f"{k}: {v['about']}"
                                                                for k, v in CLASSES.items()))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--data-dir", default="~/data")
    ap.add_argument("--tag", required=True, help="label for this run, e.g. the policy")
    ap.add_argument("--out", required=True)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
