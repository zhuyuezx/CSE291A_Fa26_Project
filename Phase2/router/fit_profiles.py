#!/usr/bin/env python3
"""Fit per-node cost profiles from the endpoint measurements in results/<NODE>/.

Every term comes from endpoint_test.py's server.jsonl (server-side timings),
so the router's cost model is measured, not assumed:

  prefill_s(p)   = c0 + a*p + b*p^2          single-request prefill of p prompt tokens
  step_s(b, ctx) = (s0 + g*ctx) * m[b]       one decode step with b sequences decoding,
                                             ctx = mean context length of those sequences
  vision_s[px]                               image encode + prefill for a bar-chart image

m[b] is the decode-step slowdown with b concurrent sequences, measured from the
concurrency test (b = 1, 2, 4; b = 3 is interpolated).

    python3 Phase2/router/fit_profiles.py C1 C2      # writes Phase2/router/profiles.json
"""

import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "profiles.json"


def lstsq(rows, ys):
    """Least squares for a small dense system via normal equations (no numpy)."""
    n = len(rows[0])
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(n)] for i in range(n)]
    aty = [sum(r[i] * y for r, y in zip(rows, ys)) for i in range(n)]
    # Gauss-Jordan elimination with partial pivoting.
    m = [ata[i] + [aty[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit_node(name):
    recs = [json.loads(line) for line in (REPO / "results" / name / "server.jsonl").open()]
    recs = [r for r in recs if r["ok"]]
    single = [r for r in recs if r["kind"] == "single"]
    conc = [r for r in recs if r["kind"] == "concurrent"]
    image = [r for r in recs if r["kind"] == "image"]

    # Prefill: single requests plus the 1-request concurrency runs.
    pts = [(r["prompt_tokens"], r["prefill_s"]) for r in single]
    pts += [(r["prompt_tokens"], r["prefill_s"]) for r in conc if r["conc"] == 1]
    c0, a, b = lstsq([[1, p, p * p] for p, _ in pts], [s for _, s in pts])

    # Decode step at batch 1 vs. context length (prompt + half the output).
    dec = [(r["prompt_tokens"] + r["output_tokens"] / 2, r["decode_s"] / r["output_tokens"])
           for r in single if r["output_tokens"] >= 32]
    s0, g = lstsq([[1, c] for c, _ in dec], [s for _, s in dec])

    # Batch slowdown m[b]: per-request decode step with b sequences decoding together,
    # relative to the batch-1 step at the same context.
    m = {}
    for n in sorted({r["conc"] for r in conc}):
        if n > 4:
            continue  # beyond the slot count, requests queue rather than batch
        steps = [r["decode_s"] / r["output_tokens"] /
                 (s0 + g * (r["prompt_tokens"] + r["output_tokens"] / 2))
                 for r in conc if r["conc"] == n]
        m[n] = statistics.median(steps)
    base = m[1]
    m = {k: v / base for k, v in m.items()}
    if 3 not in m and 2 in m and 4 in m:
        m[3] = (m[2] + m[4]) / 2

    vision = {}
    for px in sorted({r["image_px"] for r in image}):
        g_ = [r for r in image if r["image_px"] == px]
        vision[str(px)] = {"seconds": statistics.median(r["prefill_s"] for r in g_),
                           "tokens": statistics.median(r["prompt_tokens"] for r in g_)}

    env = (REPO / "results" / name / "report.md").read_text()
    slots = int(env.split("PARALLEL=")[1].split()[0]) if "PARALLEL=" in env else 4
    return {
        "slots": slots,
        "prefill": {"c0": c0, "a": a, "b": b},
        "decode": {"s0": s0, "g": g, "batch_factor": {str(k): m[k] for k in sorted(m)}},
        "vision": vision,
        "source": f"results/{name}/server.jsonl",
    }


def main():
    names = sys.argv[1:] or ["C1", "C2"]
    prof = {n: fit_node(n) for n in names}
    OUT.write_text(json.dumps(prof, indent=2) + "\n")
    for n, p in prof.items():
        pf, d = p["prefill"], p["decode"]
        batch = ", x".join("%.2f" % v for v in d["batch_factor"].values())
        vis = ", ".join("%spx %.1fs" % (k, v["seconds"]) for k, v in p["vision"].items())
        print(f"{n}: prefill = {pf['c0']:.3f} + {pf['a'] * 1e3:.3f} ms*p + {pf['b'] * 1e6:.3f} us*p^2 | "
              f"decode step = {d['s0'] * 1e3:.1f} ms + {d['g'] * 1e6:.2f} us*ctx, batch x{batch} | "
              f"vision {vis}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
