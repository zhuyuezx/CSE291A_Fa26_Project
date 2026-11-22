#!/usr/bin/env python3
"""Route a real open-loop request trace across live llama-server endpoints.

The trace comes from simulate.trace (same classes, mixes, and arrival
process), so a live run can be compared with the simulator. Each request is
turned into a real prompt; the router only sees what a deployed router would:
an estimate of the prompt length from its text, the image size, the task
class, and max_tokens. Every policy in a run replays the same trace.

For every request the log also records ECT's predicted latency on the chosen
node (from a shadow ECT that observes the same dispatches), whatever policy
routed it, so the cost model can be checked against reality.

    # from a laptop, through SSH tunnels to the endpoints
    python3 Phase2/router/live.py --endpoints C1=http://127.0.0.1:18081 C2=http://127.0.0.1:18082 \
        --policies round-robin JSQ SED ECT-global --n 40 --load 0.5
    # on the router: endpoints default to deploy/endpoints.json private IPs
    fleet-run <name> python3 Phase2/router/live.py --policies ECT-global --n 200
    # through the routing service (router.py) instead of routing in this process:
    fleet-run <name> python3 Phase2/router/live.py --router http://localhost:9000 --policies JSQ ECT-global

With --router, every request goes to router.py, which picks the node; live.py
switches the router's policy before each run (POST /admin/policy) and sends
the task class and declared max_tokens as headers (X-Task-Class, X-Max-Tokens).
ECT's predicted latency is then logged by the router (router.jsonl), not here.
"""

import argparse
import base64
import json
import queue
import random
import re
import statistics
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "harness"))

import simulate  # noqa: E402
from endpoint_test import chat, chart_answer, nonce  # noqa: E402
from nodemodel import Node, load_profiles  # noqa: E402
from policies import ECT, build  # noqa: E402

DATA = HERE.parents[1] / "Phase1" / "data"
CHARS_PER_TOKEN = 4.0
TEMPLATE_TOKENS = 15  # chat-template overhead around the user message


def document(questions, target_tokens, rng):
    qs = questions[:]
    rng.shuffle(qs)
    body, i = f"[request {nonce()}] Below are several word problems.\n\n", 0
    while len(body) < target_tokens * CHARS_PER_TOKEN:
        body += f"Problem {i + 1}: {qs[i % len(qs)]}\n\n"
        i += 1
    return body


def realize(r, questions, seed):
    """Turn a trace entry into (messages, max_tokens sent, ignore_eos, router view)."""
    rng = random.Random(seed * 100003 + r["rid"])
    cls = r["cls"]
    if cls == "gsm":
        text = f"[{nonce()}] {rng.choice(questions)}"
        msgs, send_max, ignore = [{"role": "user", "content": text}], r["max_tokens"], False
    elif cls == "story":
        text = f"[{nonce()}] Write a long, detailed story about a city on Mars."
        msgs, send_max, ignore = [{"role": "user", "content": text}], r["out"], True
    elif cls == "summ":
        text = document(questions, r["prompt"], rng) + "Task: In one sentence, say what the first problem is about."
        msgs, send_max, ignore = [{"role": "user", "content": text}], r["max_tokens"], False
    elif cls == "rag":
        text = document(questions, r["prompt"], rng) + "Task: Solve the first problem step by step."
        msgs, send_max, ignore = [{"role": "user", "content": text}], r["out"], True
    elif cls == "img":
        k = r["rid"] % 3
        b64 = base64.b64encode((DATA / "images" / f"chart_{r['px']}px_seed{k}.png").read_bytes()).decode()
        text = f"[{nonce()}] Which bar in this chart is the tallest? Reply with the letter only."
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]
        send_max, ignore = r["max_tokens"], False
    else:
        raise ValueError(cls)
    view = {"rid": r["rid"], "cls": cls, "px": r["px"], "max_tokens": r["max_tokens"],
            "prompt": r["prompt"] if cls == "img" else int(len(text) / CHARS_PER_TOKEN) + TEMPLATE_TOKENS}
    return msgs, send_max, ignore, view


def busy_slots(url):
    with urllib.request.urlopen(url + "/slots", timeout=5) as f:
        return sum(s["is_processing"] for s in json.load(f))


def wait_idle(urls):
    while any(busy_slots(u) for u in urls.values()):
        time.sleep(1)


def set_router_policy(router, name):
    req = urllib.request.Request(router + "/admin/policy", data=json.dumps({"policy": name}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as f:
        return json.load(f)["policy"]


def run_policy(name, reqs, payloads, urls, profiles, seed, log, router=None):
    pol = build(name, profiles, None, seed)
    obs = ECT(profiles)  # shadow predictor, observes the same dispatches
    if router:
        set_router_policy(router, name)  # the router decides; pol and obs stay unused
    done = queue.Queue()
    threads, out = [], []
    t0 = time.perf_counter()

    def worker(r, node, msgs, send_max, ignore, view, t_disp, pred):
        if router:
            rec = chat(router, msgs, send_max, ignore_eos=ignore, headers={
                "X-Task-Class": r["cls"], "X-Max-Tokens": str(view["max_tokens"])})
            node = rec.get("routed_to")
        else:
            rec = chat(urls[node], msgs, send_max, ignore_eos=ignore)
        t_end = time.perf_counter() - t0
        rec.update(policy=name, rid=r["rid"], cls=r["cls"], px=r["px"], node=node,
                   t_arrival=r["t"], t_dispatch=t_disp, t_done=t_end, prompt_est=view["prompt"],
                   pred_e2e_s=None if pred is None else pred - t_disp,
                   via_router=bool(router))
        if r["cls"] == "img":
            m = re.search(r"\b([A-E])\b", rec.get("text") or "")
            rec["correct"] = bool(m) and m.group(1) == chart_answer(r["rid"] % 3)
        done.put(rec)

    def drain():
        while True:
            try:
                rec = done.get_nowait()
            except queue.Empty:
                return
            view = payloads[rec["rid"]][3]
            n_out = rec.get("output_tokens") or 0
            if not router:
                pol.on_complete(view, rec["node"], rec["t_done"], n_out)
                obs.on_complete(view, rec["node"], rec["t_done"], n_out)
            out.append(rec)
            log.write(json.dumps(rec) + "\n")
            log.flush()
            pred = "   -  " if rec["pred_e2e_s"] is None else f"{rec['pred_e2e_s']:6.1f}s"
            print(f"  [{name}] rid {rec['rid']:>3} {rec['cls']:<5} -> {rec['node']}  "
                  f"e2e {rec['e2e_s']:6.1f}s  pred {pred}  "
                  f"{'ok' if rec['ok'] else rec.get('error')}", flush=True)

    for r in reqs:
        while time.perf_counter() - t0 < r["t"]:
            drain()
            time.sleep(min(0.05, max(0.0, r["t"] - (time.perf_counter() - t0))))
        drain()
        msgs, send_max, ignore, view = payloads[r["rid"]]
        t = time.perf_counter() - t0
        if router:
            node, pred = None, None  # the router picks the node; the worker records it
        else:
            node = pol.route(view, t)
            pred = obs.score(node, view, t)
            pol.on_dispatch(view, node, t)
            obs.on_dispatch(view, node, t)
        th = threading.Thread(target=worker, args=(r, node, msgs, send_max, ignore, view, t, pred))
        th.start()
        threads.append(th)
    while len(out) < len(reqs):
        drain()
        time.sleep(0.05)
    return out


def summary(name, recs, profiles):
    ok = [r for r in recs if r["ok"]]
    models = [Node(k, v) for k, v in profiles.items()]
    for r in ok:
        p = r["prompt_tokens"] or r["prompt_est"]
        r["best"] = min(m.service_s(p if not r["px"] else 0, r["px"], r["output_tokens"] or 1)
                        for m in models)
    e2e = [r["e2e_s"] for r in ok]
    err = [(r["pred_e2e_s"] - r["e2e_s"]) / r["e2e_s"] for r in ok if r["pred_e2e_s"] is not None]
    share = {}
    for r in ok:
        share[r["node"]] = share.get(r["node"], 0) + 1
    img = [r for r in ok if r["cls"] == "img"]
    return {
        "policy": name, "n": len(recs), "failed": len(recs) - len(ok),
        "mean_e2e": statistics.mean(e2e), "p50_e2e": simulate.pct(e2e, 50),
        "p95_e2e": simulate.pct(e2e, 95), "p95_ttft": simulate.pct([r["ttft_s"] for r in ok], 95),
        "slo_attain": sum(r["e2e_s"] <= simulate.SLO_X * r["best"] for r in ok) / len(ok),
        "pred_median_abs_err": statistics.median(abs(e) for e in err) if err else None,
        "pred_median_bias": statistics.median(err) if err else None,
        "img_correct": f"{sum(r.get('correct', False) for r in img)}/{len(img)}",
        "share": " ".join(f"{k}:{v / len(ok):.2f}" for k, v in sorted(share.items())),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoints", nargs="+", help="NAME=URL; default: deploy/endpoints.json")
    ap.add_argument("--policies", nargs="+", default=["round-robin", "JSQ", "SED", "ECT-global"])
    # The fleet is text-only (no vision projector), so the default mix has no images.
    ap.add_argument("--mix", default="D-phase1-T1T2T3", choices=list(simulate.MIXES))
    ap.add_argument("--img-px", nargs="+", type=int, default=[256, 512, 1024])
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--load", type=float, default=0.5)
    ap.add_argument("--cv", type=float, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--images", action="store_true",
                    help="allow mixes with image requests (only if every endpoint runs with VISION=1)")
    ap.add_argument("--router", default=None,
                    help="route through router.py at this URL (e.g. http://localhost:9000)")
    args = ap.parse_args()

    if args.endpoints:
        urls = dict(e.split("=", 1) for e in args.endpoints)
    else:
        eps = json.loads((HERE.parent / "deploy" / "endpoints.json").read_text())["endpoints"]
        urls = {e["name"]: f"http://{e['private_ip']}:{e['port']}" for e in eps}
    profiles = {k: v for k, v in load_profiles().items() if k in urls}
    urls = {k: urls[k] for k in profiles}
    if not urls:
        sys.exit("no endpoint has a profile in profiles.json")

    if simulate.MIXES[args.mix].get("img") and not args.images:
        sys.exit(f"mix {args.mix} has image requests, but the endpoints serve text only "
                 "(setup_node.sh VISION=0); use a text-only mix such as B-decode-heavy or "
                 "D-phase1-T1T2T3, or pass --images if every endpoint loads a vision projector")
    simulate.IMG_PX = {px: w for px, w in simulate.IMG_PX.items() if px in args.img_px}
    has_img = bool(simulate.MIXES[args.mix].get("img"))
    img_note = f"images {sorted(simulate.IMG_PX)} px" if has_img else "text only"
    gsm = simulate.gsm_pairs()
    vtok = {int(k): v["tokens"] for k, v in next(iter(profiles.values()))["vision"].items()}
    cap = simulate.nominal_capacity(profiles, args.mix, gsm, vtok)
    rate = args.load * cap
    reqs = simulate.trace(args.mix, args.n, rate, args.cv, args.seed, gsm, vtok)
    questions = [json.loads(line)["question"] for line in (DATA / "gsm8k_test_n100_seed0.jsonl").open()]
    payloads = {r["rid"]: realize(r, questions, args.seed) for r in reqs}
    print(f"endpoints {urls}\nmix {args.mix}, {img_note}, "
          f"{args.n} requests at {60 * rate:.2f} req/min (load {args.load}, cv {args.cv:g}); "
          f"arrivals span {reqs[-1]['t'] / 60:.1f} min per policy", flush=True)

    tag = args.tag or time.strftime("%Y%m%d-%H%M%S")
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    rows = []
    with open(out_dir / f"live_{tag}.jsonl", "w") as log:
        for name in args.policies:
            wait_idle(urls)
            print(f"== {name}", flush=True)
            recs = run_policy(name, reqs, payloads, urls, profiles, args.seed, log, args.router)
            s = summary(name, recs, profiles)
            rows.append(s)
            print(json.dumps(s), flush=True)

    lines = [f"# Live routing run {tag}", "",
             f"Endpoints: {', '.join(f'{k} ({v})' for k, v in urls.items())}. Mix {args.mix}, "
             f"{img_note}, {args.n} requests per policy at "
             f"{60 * rate:.2f} req/min (load {args.load}, arrival CV {args.cv:g}, seed {args.seed}). "
             f"SLO = {simulate.SLO_X:g}x the best idle-node latency. Prediction error is ECT's "
             "predicted latency on the chosen node vs. the measured one.", "",
             "| policy | mean e2e s | p50 e2e s | p95 e2e s | p95 TTFT s | SLO met | "
             "ECT pred. median abs. error | bias | image answers | share | failed |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in rows:
        if s["pred_median_abs_err"] is None:  # --router: predictions are in the router's log
            pred_cols = "- | - |"
        else:
            pred_cols = f"{100 * s['pred_median_abs_err']:.0f}% | {100 * s['pred_median_bias']:+.0f}% |"
        lines.append(f"| {s['policy']} | {s['mean_e2e']:.1f} | {s['p50_e2e']:.1f} | {s['p95_e2e']:.1f} | "
                     f"{s['p95_ttft']:.1f} | {100 * s['slo_attain']:.0f}% | {pred_cols} "
                     f"{s['img_correct']} | {s['share']} | {s['failed']} |")
    (out_dir / f"live_{tag}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
