# Phase 2: status and how to work on the fleet

*Last updated 2026-11-22 (Nov 21, evening PT). Phase 2 code and the final report are due **Dec 10**.*

## What changed after Phase 1

The instructor's feedback on Phase 1 ([Phase1/comment.txt](../Phase1/comment.txt)): the heterogeneity to study is **different devices, not different models**. Phase 1 only compared models on one MacBook.

So Phase 2 is organized like this:

- **Core study:** the *same* model on every machine (Qwen3.5-2B, Q4_K_M, one identical GGUF file). The router decides **which machine** runs each request, using measured per-machine profiles and each machine's current queue. It is compared against always-one-machine, round-robin, and a simple load-aware baseline, as Option 3 requires.
- **Optional extension:** choosing a different model per request (the Phase 1 GSM8K tier work), reported separately with answer quality.
- **AWS only.** The laptops are dropped.
- **Text only, for now.** Image requests are out of scope. Endpoints are set up without the vision projector (`VISION=0`, the default in `setup_node.sh`). G1's 3 GB GPU cannot hold the 2B model plus the projector anyway: it runs out of memory reserving the vision encoder's buffers. The early C1, C2, and G2 tests included images; their text results are unaffected.

## The fleet

Everything is in **us-west-2 (Oregon)**, in the shared group account. Every endpoint runs `llama-server` from llama.cpp `b12617` on port 8080: thinking off, 4 request slots, 16K shared context, prompt cache off.

| Name | Instance | Hardware | Zone | Private IP | $/h | Status |
|---|---|---|---|---|---|---|
| **R** (router) | `m7g.large` | Graviton3, 2 vCPU, 8 GiB | 2d | 172.31.60.152, Elastic IP **32.191.208.76** | ~0.08 | ready |
| **C1** | `c7g.xlarge` | Graviton3 (Arm), 4 cores, 8 GiB | 2d | 172.31.61.18 | 0.145 | ready, tested |
| **C2** | `c7i.xlarge` | Xeon Sapphire Rapids (x86, AMX), 2 cores × 2 threads, 8 GiB | 2b | 172.31.41.144 | 0.179 | ready, tested |
| **G1** | `g6f.large` | 1/8 NVIDIA L4 (**3 GB** VRAM), 2 vCPU | 2d | 172.31.56.6 | ~0.20 | ready (text-only); tests pending until the fleet is free |
| **G2** | `g4dn.xlarge` | NVIDIA T4 (16 GB), 4 vCPU | 2c | 172.31.11.54 | 0.526 | ready, tested |

Running everything costs about **$1.15/h**. With all instances stopped, the disks and the Elastic IP still cost about **$0.55/day**. The group cap is **$20/day**.

The CPU pair (C1 vs. C2) varies CPU architecture at an equal vCPU count and roughly equal price. The GPU pair (G1 vs. G2) varies GPU share and memory: G1 can hold the 2B model plus its vision projector, but not the 4B. The private IPs never change; public addresses change on every stop/start, except the router's Elastic IP.

## Getting connected (once per person)

1. Get the team key `cse291_router_key.pem` from Jason (it is never in the repo). Save it as `~/.ssh/cse291_router_key.pem`.
2. Add this line at the **top** of `~/.ssh/config` (create the file if needed):
   ```
   Include <path to this repo>/Phase2/deploy/ssh_config
   ```
3. Connect with `ssh cse-router`, `ssh cse-c1`, `ssh cse-c2`, `ssh cse-g1` or `ssh cse-g2`. The endpoints are reached *through* the router. VS Code Remote-SSH lists the same names.

SSH is allowed from the **UCSD campus network** (`128.54.0.0/16`). From home, add your own IP as an extra SSH rule in security group `launch-wizard-8` (EC2 → Security Groups), with your name in the description. If SSH suddenly times out, check your IP first.

## Ground rules

1. **One experiment at a time.** The endpoints are shared; two load tests at once ruin both sets of numbers. Run every measurement on the router through the lock:
   ```bash
   fleet-run status                                       # who holds the fleet; each endpoint's health and busy slots
   fleet-run <your-name> python3 my_experiment.py         # refused if someone else is running
   fleet-run --wait <your-name> python3 my_experiment.py  # queue instead
   ```
2. **Measure from the router, develop on your laptop.** Share code and results through git. Heavy work on the router distorts the latency it measures.
3. **Whoever starts instances stops them.** Stop, don't terminate. Check the EC2 console before you leave.
4. **Don't `apt upgrade` the GPU nodes.** G1's driver was installed by hand for its exact kernel.

## Quick checks

```bash
ssh cse-router
fleet-run status
# one request to C1 from the router; "timings" gives prefill and decode token counts and milliseconds
curl -s http://172.31.61.18:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is 17*23?"}],"max_tokens":16}' | jq '.choices[0].message.content, .timings'
```

On an endpoint, server settings are in `/opt/llm/server.env` (then `sudo systemctl restart llama-server`), logs come from `journalctl -u llama-server -f`, and hardware and software versions are in `/opt/llm/node_info.txt`.

## Results so far (C1 vs. C2)

The full comparison is in [results/README.md](../results/README.md), and each node's report and raw logs are in `results/<node>/`.

| | C1 (Arm, 4 cores) | C2 (x86 + AMX, 2 cores) |
|---|---|---|
| Prefill (reading the prompt) | 95 tok/s | **155 tok/s** |
| Decode (generating) | **22.5 tok/s** | 10.3 tok/s |
| 1024 px image, time to first token | 211 s | **31 s** |

- **The faster machine depends on the request.** C2 wins when the prompt is more than about 6–11 times the output length; C1 wins otherwise, by about 2× in each direction. That's a device-level reason for the router to exist.
- **Images strongly favour C2.** C1's vision encoder is very slow; the cause isn't diagnosed yet.
- **Each CPU node saturates at about 4 simultaneous requests.** Running more together gives only 1.4–1.7× more throughput, so watching each node's queue matters.
- **Cold start is about 15 s, set by the disk's read speed.** With the model already in memory it is 1.2–1.5 s.
- **Network between nodes is about 2 ms per request**, even across zones. That is negligible next to inference time.

The G1 and G2 results will be added the same way.

## Code layout

```
Phase2/
  README.md            this file
  deploy/
    README.md          how the instances were launched and set up (AMIs, disks, GPU drivers, cost hygiene)
    setup_node.sh      turns a fresh instance into an endpoint (build llama.cpp, fetch hash-checked models, systemd service)
    setup_router.sh    router setup: tools, Python venv at /opt/fleet/venv, fleet-run
    fleet-run.sh       the experiment lock (installed on the router as `fleet-run`)
    endpoints.json     the fleet: names, instance types, zones, private IPs
    ssh_config         SSH shortcuts (cse-router, cse-c1, ...)
  harness/
    endpoint_test.py   request-level tests on one endpoint: length grid, concurrency, images (standard library only)
    run_node_tests.sh  full single-node suite: llama-bench, cold start, endpoint_test.py, memory
results/               (repo root) measurements per node and the comparison README
```

## Next steps (open for anyone to pick up)

1. **Finish the GPU measurements.** G1 and G2 run automatically; then extend `results/README.md` to all four nodes and find each node's best configuration (e.g. C2 is 16–22% faster with 4 threads instead of 2).
2. **Multi-endpoint load generator on the router.** Port Phase 1's `run_load.py` to send open-loop Poisson and bursty traffic across all endpoints, with a workload mix (short chat, long prompt, long output, images) and dev vs. held-out mixes.
3. **Network and transfer cost (E3).** Router → endpoint latency versus payload size, including large prompts and images.
4. **Router.** Baselines first: always-C1/C2/G1/G2, round-robin, least-outstanding-requests. Then the completion-time router: estimated time = queue wait + prompt/prefill rate + output/decode rate + network, using the measured profiles and live `/slots` state.
5. **Evaluation.** Steady and bursty arrivals at several loads, the fastest node idle vs. busy, repeated runs with confidence intervals.
6. **Report.**

## Known issues

- **Port 22 is reachable between nodes,** but the campus-only SSH rule shouldn't allow that. Please check that no inbound rule in `launch-wizard-8` has source `0.0.0.0/0`.
- **The router cannot SSH to the endpoints** (it has no key for them). That's by design for now: router experiments only need HTTP on port 8080.
- **The CUDA versions differ:** G1 uses CUDA 13.0 with the GRID driver (required for fractional GPUs), and G2 uses CUDA 13.2 from AWS's Deep Learning AMI. Both are recorded in `node_info.txt`.
- **Idle-stop alarms are not set up yet.** Until they are, stopping instances is manual.
