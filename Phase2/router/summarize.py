"""Compare router experiment runs: client logs from loadgen.py, plus optional
router logs for the router's own overhead.

    /opt/fleet/venv/bin/python summarize.py runs/X/client_*.jsonl --routers runs/X/router_*.jsonl

Router overhead per request = (router forwards - client sends) + (client gets
first byte - router gets first byte from the endpoint). Both clocks are on the
router host, so they are directly comparable.
"""

import argparse
import json

import numpy as np


def read(paths):
    out = []
    for p in paths:
        with open(p) as f:
            out += [json.loads(line) for line in f if line.strip()]
    return out


def pct(xs, q):
    xs = [x for x in xs if x is not None]
    return float(np.percentile(xs, q)) if xs else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else None


def f(x, nd=1):
    return "-" if x is None else f"{x:.{nd}f}"


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clients", nargs="+")
    ap.add_argument("--routers", nargs="*", default=[])
    args = ap.parse_args()

    recs = read(args.clients)
    routers = {r["id"]: r for r in read(args.routers) if r.get("id")}
    tags = list(dict.fromkeys(r["tag"] for r in recs))
    classes = sorted({r["cls"] for r in recs})
    endpoints = sorted({r.get("routed_to") for r in recs if r.get("routed_to")})

    rows, cls_rows, ovh_rows = [], [], []
    for tag in tags:
        g = [r for r in recs if r["tag"] == tag]
        ok = [r for r in g if r["ok"]]
        span = max(r["t_done_epoch"] for r in g) - min(r["t_send_epoch"] for r in g)
        e2e = [r["e2e_s"] for r in ok]
        ttft = [r["ttft_s"] for r in ok]
        share = " ".join(f"{e}:{sum(r.get('routed_to') == e for r in g)}" for e in endpoints)
        rows.append([tag, f"{len(ok)}/{len(g)}", f(60 * len(ok) / span, 1), f(mean(e2e)),
                     f(pct(e2e, 50)), f(pct(e2e, 95)), f(pct(e2e, 99)),
                     f(pct(ttft, 50)), f(pct(ttft, 95)), share])
        cls_rows.append([tag] + [f(mean([r["e2e_s"] for r in ok if r["cls"] == c])) for c in classes])

        joined = [(r, routers[r["id"]]) for r in ok if r["id"] in routers]
        dec = [rt["decision_us"] for _, rt in joined]
        added = [1000 * ((rt["t_up_send"] - r["t_send_epoch"]) +
                         (r["t_first_byte_epoch"] - rt["t_up_first_byte"]))
                 for r, rt in joined if "t_up_first_byte" in rt and "t_first_byte_epoch" in r]
        if joined:
            ovh_rows.append([tag, len(joined), f(pct(dec, 50), 1), f(pct(dec, 99), 1),
                             f(pct(added, 50), 2), f(pct(added, 99), 2)])

    n_cls = {c: sum(r["cls"] == c for r in recs if r["tag"] == tags[0]) for c in classes}
    print("### Latency and throughput (seconds; throughput in completed requests/min)\n")
    print(table(["policy", "ok", "throughput", "mean e2e", "p50 e2e", "p95 e2e", "p99 e2e",
                 "p50 TTFT", "p95 TTFT", "requests per endpoint"], rows))
    print("\n### Mean end-to-end latency by request class (seconds)\n")
    print(table(["policy"] + [f"{c} (n={n_cls[c]})" for c in classes], cls_rows))
    if ovh_rows:
        print("\n### Router overhead\n")
        print(table(["policy", "joined", "decision p50 µs", "decision p99 µs",
                     "added latency p50 ms", "added latency p99 ms"], ovh_rows))
    failed = [r for r in recs if not r["ok"]]
    print(f"\n{len(failed)} failed requests" + (": " + "; ".join(
        f"{r['tag']}#{r['i']} {r.get('error', '')[:80]}" for r in failed[:5]) if failed else "."))


if __name__ == "__main__":
    main()
