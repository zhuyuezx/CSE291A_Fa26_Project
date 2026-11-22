#!/usr/bin/env python3
"""Offline comparison of routing policies on the measured node profiles.

Each node is a nodemodel.Node fitted to its own measurements. Every policy
sees the same request trace (same arrival times, shapes, and output lengths),
so differences come from routing alone.

  python3 Phase2/router/simulate.py validate      # model vs. measured endpoint tests
  python3 Phase2/router/simulate.py grid          # all mixes x arrivals x loads x policies

Request classes (output lengths are what the server actually generates):
  gsm    GSM8K question, prompt and output lengths sampled as pairs from
         Phase 1's qwen3.5:2b runs (median 97 -> 220 tokens; decode-heavy)
  story  short prompt, long story (T3 in Phase 1)
  summ   ~2K-token document, one-sentence answer (T2; prefill-heavy)
  rag    0.5-1.2K-token context, medium answer
  img    bar-chart question at 256/512/1024 px, letter answer
The grid uses the text-only mixes (images are out of scope for Phase 2). Mix A
is the development mix; B, C, D are held out. A-balanced, which includes
images, is kept for the first live run (results/live_trial1.md).
"""

import argparse
import csv
import json
import math
import random
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

from nodemodel import Job, Node, load_profiles
from policies import POLICIES, build

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT_DIR = HERE / "results"
NET_S = 0.002  # measured C1 <-> C2 request overhead (results/README.md)
SLO_X = 3.0    # deadline: 3x the request's latency on the best idle node

MIXES = {
    "A-text": {"gsm": .45, "story": .15, "summ": .25, "rag": .15},
    "B-decode-heavy": {"gsm": .60, "story": .30, "summ": .05, "rag": .05},
    "C-prefill-heavy": {"gsm": .20, "summ": .45, "rag": .35},
    "D-phase1-T1T2T3": {"gsm": .50, "summ": .25, "story": .25},
    "A-balanced": {"gsm": .40, "story": .15, "summ": .20, "rag": .15, "img": .10},
}
GRID_MIXES = ["A-text", "B-decode-heavy", "C-prefill-heavy", "D-phase1-T1T2T3"]
IMG_PX = {256: .50, 512: .35, 1024: .15}


def gsm_pairs():
    path = REPO / "Phase1/results/raw/e5_gsm8k.jsonl"
    rows = [json.loads(line) for line in path.open()]
    return [(r["prompt_tokens"], r["output_tokens"]) for r in rows
            if r["model"] == "qwen3.5:2b" and r.get("ok") and r.get("output_tokens")]


def make_request(cls, rng, gsm, vision_tokens):
    if cls == "gsm":
        p, o = rng.choice(gsm)
        return {"cls": cls, "prompt": p, "px": 0, "out": o, "max_tokens": 512}
    if cls == "story":
        o = 256 if rng.random() < 0.8 else rng.randint(150, 256)
        return {"cls": cls, "prompt": rng.randint(30, 60), "px": 0, "out": o, "max_tokens": 256}
    if cls == "summ":
        return {"cls": cls, "prompt": rng.randint(1500, 2500), "px": 0,
                "out": rng.randint(15, 40), "max_tokens": 64}
    if cls == "rag":
        return {"cls": cls, "prompt": rng.randint(500, 1200), "px": 0,
                "out": rng.randint(40, 200), "max_tokens": 256}
    if cls == "img":
        px = rng.choices(list(IMG_PX), weights=list(IMG_PX.values()))[0]
        return {"cls": cls, "prompt": vision_tokens[px], "px": px,
                "out": rng.randint(1, 4), "max_tokens": 8}
    raise ValueError(cls)


def trace(mix, n, rate, cv, seed, gsm, vision_tokens):
    """n requests with mean arrival rate `rate` (req/s); cv=1 is Poisson,
    cv>1 is gamma-distributed (bursty) interarrivals."""
    rng = random.Random(seed)
    classes, weights = list(MIXES[mix]), list(MIXES[mix].values())
    t, reqs = 0.0, []
    for i in range(n):
        if cv == 1:
            t += rng.expovariate(rate)
        else:
            k = 1 / cv ** 2
            t += rng.gammavariate(k, 1 / (rate * k))
        r = make_request(rng.choices(classes, weights=weights)[0], rng, gsm, vision_tokens)
        r.update(rid=i, t=t)
        reqs.append(r)
    return reqs


def nominal_capacity(profiles, mix, gsm, vision_tokens, n=4000):
    """Requests/s the fleet serves if every node handles the whole mix one
    request at a time: the sum of each node's own rate. A load of 1.0 means
    this rate. Batching and shape-aware placement let a good router go beyond it."""
    rng = random.Random(123)
    nodes = [Node(k, v) for k, v in profiles.items()]
    classes, weights = list(MIXES[mix]), list(MIXES[mix].values())
    work = {nd.name: 0.0 for nd in nodes}
    for _ in range(n):
        r = make_request(rng.choices(classes, weights=weights)[0], rng, gsm, vision_tokens)
        for nd in nodes:
            work[nd.name] += nd.service_s(r["prompt"], r["px"], r["out"])
    return sum(n / w for w in work.values())


def run(policy_name, profiles, reqs, seed=0):
    nodes = {k: Node(k, v) for k, v in profiles.items()}
    pol = build(policy_name, profiles, nodes, seed)
    byid = {r["rid"]: r for r in reqs}
    where, done, overhead = {}, {}, []

    def collect(t):
        fin = []
        for name, nd in nodes.items():
            nd.advance(t)
            fin += [(j.t_done, name, j) for j in nd.finished]
            nd.finished = []
        for t_done, name, j in sorted(fin, key=lambda x: x[0]):
            done[j.rid] = j
            pol.on_complete(byid[j.rid], name, t_done, j.out)

    for r in reqs:
        collect(r["t"])
        c0 = time.perf_counter()
        name = pol.route(r, r["t"])
        overhead.append(time.perf_counter() - c0)
        pol.on_dispatch(r, name, r["t"])
        where[r["rid"]] = name
        nodes[name].submit(Job(r["rid"], r["prompt"], r["px"], r["out"]), r["t"] + NET_S)
    for name, nd in nodes.items():
        nd.drain()
    collect(float("inf"))

    model = {k: Node(k, v) for k, v in profiles.items()}
    rows = []
    for r in reqs:
        j = done[r["rid"]]
        best = min(m.service_s(r["prompt"], r["px"], r["out"]) for m in model.values())
        rows.append({"rid": r["rid"], "cls": r["cls"], "node": where[r["rid"]],
                     "e2e": j.t_done - r["t"], "ttft": j.t_first - r["t"], "best": best})
    return rows, overhead


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(math.ceil(q / 100 * len(xs))) - 1)]


def summarize(rows, overhead, warmup):
    rows = rows[warmup:]
    e2e = [r["e2e"] for r in rows]
    share = {}
    for r in rows:
        share[r["node"]] = share.get(r["node"], 0) + 1
    return {
        "mean_e2e": statistics.mean(e2e), "p50_e2e": pct(e2e, 50),
        "p95_e2e": pct(e2e, 95), "p99_e2e": pct(e2e, 99),
        "p95_ttft": pct([r["ttft"] for r in rows], 95),
        "slo_attain": sum(r["e2e"] <= SLO_X * r["best"] for r in rows) / len(rows),
        "mean_slowdown": statistics.mean(r["e2e"] / r["best"] for r in rows),
        "share": " ".join(f"{k}:{v / len(rows):.2f}" for k, v in sorted(share.items())),
        "route_us": 1e6 * statistics.mean(overhead),
    }


# ---------------------------------------------------------------- validation

def validate(profiles):
    """Replay endpoint_test.py's single and concurrent tests in the model."""
    for name, prof in profiles.items():
        recs = [json.loads(line) for line in (REPO / prof["source"]).open()]
        print(f"\n{name}: measured vs. model (seconds)")
        print(f"{'test':<28}{'TTFT meas':>10}{'model':>8}{'e2e meas':>10}{'model':>8}")
        keys = sorted({(r["target_prompt"], r["target_output"]) for r in recs if r["kind"] == "single"})
        for p, o in keys:
            g = [r for r in recs if r["kind"] == "single" and r["target_prompt"] == p
                 and r["target_output"] == o]
            pt = statistics.median(r["prompt_tokens"] for r in g)
            nd = Node(name, prof)
            nd.submit(Job(0, pt, 0, o), 0.0)
            nd.drain()
            j = nd.finished[0]
            print(f"{f'single {pt:.0f}->{o}':<28}{statistics.median(r['ttft_s'] for r in g):>10.2f}"
                  f"{j.t_first:>8.2f}{statistics.median(r['e2e_s'] for r in g):>10.2f}{j.t_done:>8.2f}")
        for n in sorted({r["conc"] for r in recs if r["kind"] == "concurrent"}):
            g = [r for r in recs if r["kind"] == "concurrent" and r["conc"] == n and r["rep"] == 0]
            nd = Node(name, prof)
            for i, r in enumerate(g):
                nd.submit(Job(i, r["prompt_tokens"], 0, r["output_tokens"]), 0.0)
            nd.drain()
            meas_t = sorted(r["ttft_s"] for r in g)
            meas_e = sorted(r["e2e_s"] for r in g)
            mod_t = sorted(j.t_first for j in nd.finished)
            mod_e = sorted(j.t_done for j in nd.finished)
            for lab, a, b in (("median", statistics.median, statistics.median), ("max", max, max)):
                print(f"{f'concurrent x{n} ({lab})':<28}{a(meas_t):>10.2f}{b(mod_t):>8.2f}"
                      f"{a(meas_e):>10.2f}{b(mod_e):>8.2f}")
        img = [r for r in recs if r["kind"] == "image"]
        for px in sorted({r["image_px"] for r in img}):
            g = [r for r in img if r["image_px"] == px]
            nd = Node(name, prof)
            nd.submit(Job(0, 0, px, 1), 0.0)
            nd.drain()
            print(f"{f'image {px}px':<28}{statistics.median(r['ttft_s'] for r in g):>10.2f}"
                  f"{nd.finished[0].t_first:>8.2f}")


# ---------------------------------------------------------------- grid

def grid_cell(args):
    mix, cv, load, seed, n, profiles, gsm, vtok, policies = args
    cap = nominal_capacity(profiles, mix, gsm, vtok)
    reqs = trace(mix, n, load * cap, cv, seed, gsm, vtok)
    out = []
    for p in policies:
        rows, ov = run(p, profiles, reqs, seed)
        s = summarize(rows, ov, warmup=n // 10)
        s.update(mix=mix, arrivals="poisson" if cv == 1 else f"gamma-cv{cv:g}", load=load,
                 rate_per_min=60 * load * cap, seed=seed, policy=p)
        out.append(s)
    return out


def grid(profiles, args):
    gsm = gsm_pairs()
    vtok = {int(k): v["tokens"] for k, v in next(iter(profiles.values()))["vision"].items()}
    policies = [f"always-{k}" for k in profiles] + POLICIES
    cells = [(mix, cv, load, seed, args.n, profiles, gsm, vtok, policies)
             for mix in GRID_MIXES for cv in args.cv for load in args.loads for seed in range(args.seeds)]
    t0 = time.time()
    with Pool(args.jobs) as pool:
        res = [r for cell in pool.imap_unordered(grid_cell, cells) for r in cell]
    print(f"{len(cells)} cells x {len(policies)} policies in {time.time() - t0:.0f} s", file=sys.stderr)

    OUT_DIR.mkdir(exist_ok=True)
    tag = "-".join(profiles)
    keys = ["mix", "arrivals", "load", "rate_per_min", "seed", "policy", "mean_e2e", "p50_e2e",
            "p95_e2e", "p99_e2e", "p95_ttft", "slo_attain", "mean_slowdown", "share", "route_us"]
    with open(OUT_DIR / f"sim_runs_{tag}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in sorted(res, key=lambda r: (r["mix"], r["arrivals"], r["load"], r["seed"], r["policy"])):
            w.writerow({k: r[k] for k in keys})

    # Average over seeds.
    agg = {}
    for r in res:
        agg.setdefault((r["mix"], r["arrivals"], r["load"], r["policy"]), []).append(r)
    lines = []
    for mix in GRID_MIXES:
        for arr in sorted({r["arrivals"] for r in res}, reverse=True):
            for load in args.loads:
                rate = statistics.mean(r["rate_per_min"] for r in agg[(mix, arr, load, policies[0])])
                lines.append(f"\n### {mix}, {arr}, load {load} ({rate:.2f} req/min)\n")
                lines.append("| policy | mean e2e s | p95 e2e s | p99 e2e s | p95 TTFT s | SLO met | share |")
                lines.append("|---|---|---|---|---|---|---|")
                for p in policies:
                    g = agg[(mix, arr, load, p)]
                    m = lambda k: statistics.mean(x[k] for x in g)
                    lines.append(f"| {p} | {m('mean_e2e'):.1f} | {m('p95_e2e'):.1f} | {m('p99_e2e'):.1f} | "
                                 f"{m('p95_ttft'):.1f} | {100 * m('slo_attain'):.0f}% | {g[0]['share']} |")
    (OUT_DIR / f"sim_summary_{tag}.md").write_text(
        f"# Simulated routing on {', '.join(profiles)}, {args.seeds} seeds x {args.n} requests per cell "
        f"(first 10% dropped), SLO = {SLO_X:g}x best idle latency\n" + "\n".join(lines) + "\n")
    print(f"wrote {OUT_DIR}/sim_runs_{tag}.csv and sim_summary_{tag}.md", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["validate", "grid"])
    ap.add_argument("--profiles", default=str(HERE / "profiles.json"))
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--loads", nargs="+", type=float, default=[0.25, 0.5, 0.75, 1.0])
    ap.add_argument("--cv", nargs="+", type=float, default=[1, 3])
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--nodes", nargs="+", help="subset of profiles.json (default: all)")
    args = ap.parse_args()
    profiles = load_profiles(args.profiles)
    if args.nodes:
        profiles = {k: profiles[k] for k in args.nodes}
    if args.mode == "validate":
        validate(profiles)
    else:
        grid(profiles, args)


if __name__ == "__main__":
    main()
