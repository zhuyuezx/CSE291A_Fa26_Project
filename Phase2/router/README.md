# Router: cost model, policies, simulator, live runs

Everything here is standard-library Python (3.9+), so it runs unchanged on a laptop and on the router.

| File | What it does |
|---|---|
| `fit_profiles.py` | Fits each node's cost profile from `results/<NODE>/server.jsonl` and writes `profiles.json`: prefill time vs. prompt length, decode step vs. batch size and context, image encode time. |
| `nodemodel.py` | Fluid model of one llama-server (4 slots, FIFO queue, images encoded alone, prefill stalls decoding sequences). The simulator uses it as the node; ECT uses it to predict. |
| `policies.py` | always-*node*, round-robin, random, JSQ, best-idle, SED, ECT, ECT-global, ECT-oracle. |
| `simulate.py` | `validate`: model vs. the measured endpoint tests. `grid`: every policy on the same traces over 4 mixes × Poisson/bursty × 5 loads × 5 seeds. |
| `live.py` | Routes a real open-loop trace across live endpoints and logs ECT's predicted latency for every request. |
| `../harness/interference_test.py` | Measures what a long prompt does to a sequence already decoding on the same node. |

```bash
python3 Phase2/router/fit_profiles.py C1 C2
python3 Phase2/router/simulate.py validate
python3 Phase2/router/simulate.py grid --n 2000 --seeds 5 --loads 0.1 0.25 0.5 0.75 1.0 --cv 1 3
# on the router (endpoints default to deploy/endpoints.json private IPs; only nodes with a profile are used)
fleet-run <name> python3 Phase2/router/live.py --policies round-robin JSQ SED ECT-global --n 40 --load 0.5
```

## Results so far (C1 + C2 only)

**Model check.** The fitted model reproduces every single-request, concurrency (1–8), and image test within about 3%. The one behaviour not in those tests, a new prompt stalling a decoding sequence, was measured separately (`results/interference.jsonl`). A 2.2K-token prompt arriving mid-decode stretched a 160-token request from 7.7 s to 41.3 s on C1 (model: 40.0 s) and from 15.9 s to 30.4 s on C2 (model: 30.0 s).

**Simulation** (`results/sim_summary.md`, `results/sim_runs.csv`). Each policy's mean latency divided by the best policy's in the same cell, geometric mean over all 40 cells:

| round-robin | JSQ | best-idle | SED | ECT | ECT-global | ECT-oracle |
|---|---|---|---|---|---|---|
| 3.19 | 2.14 | 1.20 | 1.03 | 1.06 | **1.02** | 1.06 |

- Routing by request shape is the main gain: JSQ sends long prompts and images to C1, where they take 2–7× longer.
- Plain ECT does worse under bursts even with the true output length (ECT-oracle). It minimizes only the new request's finish time and ignores the decoding sequences it stalls. ECT-global counts that cost and is within 15% of the best in every cell.
- SED, which needs no queue model, is nearly as good.

**Live, on the fleet** (`results/live_trial1.md`). Mix A with 256/512 px images, 40 requests per policy at 4.9 req/min, Poisson arrivals, run from the router:

| policy | mean e2e s | p95 e2e s | p95 TTFT s | SLO met |
|---|---|---|---|---|
| round-robin | 25.9 | 57.5 | 35.3 | 78% |
| JSQ | 26.0 | 64.4 | 32.2 | 75% |
| SED | 18.8 | 37.5 | 28.9 | 95% |
| ECT-global | 19.2 | 36.2 | 20.4 | 92% |

The simulator predicted 25.2 / 17.4 / 17.6 s mean for round-robin / SED / ECT-global on the same trace. ECT's predicted latency had a median absolute error of 4–23% depending on the request class. This is one short run per policy, so treat it as a check that the simulator holds, not as the evaluation.

## Caveats and next steps

- Only C1 and C2 have profiles. Add G1 and G2 by running `run_node_tests.sh` on them and then `fit_profiles.py C1 C2 G1 G2`.
- Except for GSM8K, the request classes' lengths are synthetic. The SLO is 3× the request's latency on the best idle node.
- `live.py` estimates prompt tokens as characters / 4, which reads 5–10% low. Live `/slots` state is not used yet.
