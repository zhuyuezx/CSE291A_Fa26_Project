# Router: cost model, policies, simulator, live runs

Everything here is standard-library Python (3.9+), except `router.py`, which needs `aiohttp` (installed in `/opt/fleet/venv` on the router node).

**Scope: text only.** The endpoints serve no vision projector (`setup_node.sh` `VISION=0`). Use a text-only mix in live runs: `B-decode-heavy` or `D-phase1-T1T2T3` (the default). `live.py` refuses image mixes unless `--images` is passed. Mixes A and C include images, so they need text-only versions before they can serve as the dev/held-out mixes live.

| File | What it does |
|---|---|
| `fit_profiles.py` | Fits each node's cost profile from `results/<NODE>/server.jsonl` and writes `profiles.json`: prefill time vs. prompt length, decode step vs. batch size and context, image encode time. |
| `nodemodel.py` | Fluid model of one llama-server (4 slots, FIFO queue, images encoded alone, prefill stalls decoding sequences). The simulator uses it as the node; ECT uses it to predict. |
| `policies.py` | always-*node*, round-robin, random, JSQ, best-idle, SED, ECT, ECT-global, ECT-oracle. |
| `simulate.py` | `validate`: model vs. the measured endpoint tests. `grid`: every policy on the same traces over 4 text mixes × Poisson/bursty × loads × 5 seeds. |
| `live.py` | Routes a real open-loop trace across live endpoints and logs ECT's predicted latency for every request. |
| `../harness/interference_test.py` | Measures what a long prompt does to a sequence already decoding on the same node. |

```bash
python3 Phase2/router/fit_profiles.py C1 C2 G2
python3 Phase2/router/simulate.py validate
python3 Phase2/router/simulate.py grid --nodes C1 C2 G2 --n 2000 --seeds 5 --loads 0.25 0.5 1.0 1.5 2.0 2.5 --cv 1 3
# on the router (endpoints default to deploy/endpoints.json private IPs; only nodes with a profile are used)
fleet-run <name> python3 Phase2/router/live.py --policies round-robin JSQ SED ECT-global --n 40 --load 0.5
```

Load 1.0 is the sum of each node's rate when it serves the whole mix one request at a time. Batching and good placement let the fleet go beyond it. Each summary table also gives the absolute rate in requests per minute. The SLO is 3× the request's latency on the best idle node.

## Model check

The fitted model reproduces every single-request, concurrency (1–8), and image test on C1, C2, and G2 within about 3%. The one behaviour not in those tests, a new prompt stalling a decoding sequence, was measured separately (`results/interference.jsonl`). A 2.2K-token prompt arriving mid-decode stretched a 160-token request from 7.7 s to 41.3 s on C1 (model: 40.0 s) and from 15.9 s to 30.4 s on C2 (model: 30.0 s).

## Simulation, text only

Each table gives each policy's latency divided by the best policy's latency in the same cell, as a geometric mean over the cells. ECT-oracle is excluded from "best".

**C1 + C2** (`results/sim_summary_C1-C2.md`, 40 cells, 1.6–16 req/min):

| | round-robin | JSQ | best-idle | SED | ECT | ECT-global | ECT-oracle |
|---|---|---|---|---|---|---|---|
| mean, all cells | 1.56 | 1.46 | 1.06 | 1.03 | 1.03 | **1.02** | 1.03 |
| p95, all cells | 1.80 | 1.61 | 1.10 | 1.05 | 1.04 | **1.03** | 1.03 |
| mean, worst cell | 2.61 | 2.31 | 1.48 | 1.11 | 1.15 | **1.08** | 1.15 |

**C1 + C2 + G2** (`results/sim_summary_C1-C2-G2.md`, 48 cells, 9–141 req/min):

| | always-G2 | round-robin | JSQ | SED | ECT | ECT-global | ECT-oracle |
|---|---|---|---|---|---|---|---|
| mean, all cells | 1.78 | 95.9 | 3.39 | **1.01** | 1.14 | 1.07 | 1.13 |
| mean, load ≤ 1.0 | 1.04 | 136 | 4.16 | 1.01 | 1.01 | **1.00** | 1.00 |
| mean, load > 1.0 | 3.06 | 67.5 | 2.76 | **1.00** | 1.30 | 1.13 | 1.27 |
| mean, worst cell | 8.12 | 1357 | 6.77 | **1.05** | 1.99 | 1.44 | 2.10 |

Mean end-to-end latency in seconds for mix A-text with Poisson arrivals, and the share of requests sent to the CPU nodes by SED:

| load (req/min) | always-G2 | JSQ | SED | ECT-global | SED's CPU share |
|---|---|---|---|---|---|
| 0.5 (22) | 2.0 | 9.4 | 2.0 | 2.0 | 0% |
| 1.0 (44) | 2.9 | 10.0 | 2.9 | 2.9 | 1% |
| 1.5 (65) | 10.4 | 13.1 | 5.6 | 7.0 | 5% |
| 2.0 (87) | 188 | 106 | **27.8** | 34.3 | 14% |
| 2.5 (109) | 337 | 404 | **138** | 147 | 20% |

- **G2 dominates when it is not saturated.** Up to load 1.0, sending everything to G2 is optimal. JSQ is 3–5× worse there because it sends requests to idle CPU nodes that are 10× slower.
- **The CPU nodes become useful under contention.** Above roughly 1.5× nominal load, moving 5–20% of requests to C1 and C2 cuts mean latency 2–7× versus always-G2. Long-output requests go mostly to C1, long-prompt requests to C2. At 2.5× the fleet is overloaded under every policy, and those numbers grow with run length.
- **SED is the most robust policy** (within 5% of the best in every cell) and needs only the profiles and per-node request counts. ECT-global is close below saturation but spills too late near it. Plain ECT, even with oracle knowledge (ECT-oracle), is worse: it optimizes only the new request's finish time.

`results/sim_*_C1-C2_images.*` are the first C1 + C2 runs with image requests and the old load definition (load 1.0 = every request on its best node). They are kept for `live_trial1`.

## Live, on the fleet

`results/live_trial1.md`: C1 + C2, mix A-balanced with 256/512 px images, 40 requests per policy at 4.9 req/min, Poisson arrivals, run from the router:

| policy | mean e2e s | p95 e2e s | p95 TTFT s | SLO met |
|---|---|---|---|---|
| round-robin | 25.9 | 57.5 | 35.3 | 78% |
| JSQ | 26.0 | 64.4 | 32.2 | 75% |
| SED | 18.8 | 37.5 | 28.9 | 95% |
| ECT-global | 19.2 | 36.2 | 20.4 | 92% |

On the same trace the simulator predicted a mean of 25.2 s for round-robin, 17.4 s for SED, and 17.6 s for ECT-global. ECT's predicted latency had a median absolute error of 4–23% depending on the request class. This is one short run per policy: it checks that the simulator holds, it is not the evaluation.

## Caveats and next steps

- G1 has no profile yet. Once its tests are in `results/G1/`, run `fit_profiles.py C1 C2 G1 G2`.
- Next live run: C1 + C2 + G2 at 1.5–2.0× load, where the policies differ.
- Except for GSM8K, the request classes' lengths are synthetic.
- `live.py` estimates prompt tokens as characters / 4, which reads 5–10% low. Live `/slots` state is not used yet.
