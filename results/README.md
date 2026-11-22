# Phase 2 endpoint measurements

Each node was tested on itself with `Phase2/harness/run_node_tests.sh`, sending requests to `localhost`, so network cost is excluded. Every node serves the same file, **Qwen3.5-2B Q4_K_M** (SHA-256 `aaf42c8b…`), with llama.cpp `b12617`, thinking off, 4 server slots, and a 16K shared context. Full reports and raw logs are in each node's folder: [C1](C1/report.md), [C2](C2/report.md). G1 and G2 will be added when they are set up.

## The two CPU nodes

| | C1 | C2 |
|---|---|---|
| Instance | `c7g.xlarge` | `c7i.xlarge` |
| CPU | Graviton3 (Arm Neoverse-V1), **4 cores** | Xeon 8488C (Sapphire Rapids, AMX), **2 cores × 2 threads** |
| Memory / price | 7.6 GiB, $0.145/h | 7.6 GiB, $0.179/h |
| Zone | us-west-2d | us-west-2b |

## Results

### Raw speed (llama-bench, tokens/s, 2B model, server thread count)

| | C1 (4 threads) | C2 (2 threads) | Faster |
|---|---|---|---|
| Prefill, 512-token prompt | 95 | **155** | C2 ×1.6 |
| Prefill, 2048-token prompt | 72 | **148** | C2 ×2.0 |
| Decode | **22.5** | 10.3 | C1 ×2.2 |

Each machine wins one phase. Prefill is compute-bound, and C2's AMX units win it; C2 also holds its speed on long prompts, while C1 slows by about 25%. Decode is limited by memory bandwidth and scales with physical cores, and C1 has twice as many.

### End-to-end latency, one request at a time (seconds, medians of 3)

| prompt tokens → output tokens | C1 | C2 | Faster |
|---|---|---|---|
| 204 → 32 | **3.5** | 4.5 | C1 |
| 203 → 256 | **13.9** | 26.1 | C1 ×1.9 |
| 609 → 32 | 8.2 | **6.8** | C2 |
| 607 → 256 | **18.9** | 28.6 | C1 ×1.5 |
| 2168 → 32 | 32.6 | **16.8** | C2 ×1.9 |
| 2167 → 256 | 44.1 | **39.6** | C2 |

**The faster node depends on the request's shape.** C2 wins when the prompt is more than roughly 6–11 times the output length (6 for long prompts, 11 for short ones); otherwise C1 wins. Each node is about twice as fast as the other in its own region. A router that always picks one node loses that factor on the other kind of request.

### Image requests (bar chart, time to first token, seconds)

| image | prompt tokens | C1 | C2 | Faster |
|---|---|---|---|---|
| 256 px | 101 | 6.9 | **1.7** | C2 ×4 |
| 512 px | 294 | 31.4 | **5.4** | C2 ×6 |
| 1024 px | 1060 | 211.3 | **30.8** | C2 ×7 |

All 18 answers were correct. The gap is far larger than for text prefill (×1.7): almost all of C1's time goes to the vision encoder, about 200 s at 1024 px. The encoder runs in F16, and C1's F16 path appears much slower than C2's; the cause is not yet diagnosed. **Images belong on C2** (or a GPU).

### Concurrency (prompt ~600 tokens, output 128 tokens)

| simultaneous requests | C1 throughput, output tok/s | C2 throughput | C1 worst TTFT, s | C2 worst TTFT, s |
|---|---|---|---|---|
| 1 | 10.5 | 8.1 | 6.8 | 3.9 |
| 2 | 10.4 | 9.3 | 14.0 | 7.7 |
| 4 | 14.8 | 13.6 | 26.4 | 14.7 |
| 8 | 15.0 | 13.6 | 60.8 | 52.2 |

Batching helps little on a CPU: at most 1.4× (C1) and 1.7× (C2). Prefill already uses all the compute, so extra requests mostly wait, and time to first token grows roughly linearly with the queue. Both nodes saturate at about 4 concurrent requests. **Each CPU node holds only a few requests at a time, so tracking each node's queue matters as much as its speed.**

### Cold start, memory, network

| | C1 | C2 |
|---|---|---|
| Start to ready, model on disk (page cache dropped) | 14.9 s | 14.9 s |
| Start to ready, model already in memory | 1.2 s | 1.5 s |
| First 1-token request after start | 0.18 s | 0.29 s |
| Peak server memory, after all tests | 4.0 GB | 4.0 GB |
| Failures | 0 of 57 | 0 of 57 |

- **Cold start is limited by the disk.** Reading 1.95 GB in 14.9 s is 131 MB/s, which is the gp3 volume's baseline throughput of 125 MiB/s. So load time is predictable as file size ÷ disk throughput.
- **Network between nodes:** C1 ↔ C2 (different zones) takes 0.7–1.0 ms to connect and about 2 ms per request, against 0.4 ms on the same host. That is negligible next to inference times of seconds.

## What this means for the router

1. **Routing by request shape pays off even between the two CPU nodes.** Prefill-heavy requests and images go to C2; output-heavy requests go to C1. The prompt/output ratio is the deciding feature, and the cost model `prompt/prefill_rate + output/decode_rate` predicts each node's latency.
2. **Queue awareness is essential.** Each CPU node saturates at about 4 requests, after which delay grows linearly. The router has to weigh "fast but busy" against "slower but idle", which is the completion-time estimate (ECT) from the Phase 1 design.
3. **A better configuration for C2 to check:** llama-bench shows that using all 4 hardware threads instead of 2 gives C2 16% more prefill (179 vs 155 tok/s) and 22% more decode (12.6 vs 10.3). Hardware comparisons should report both thread settings, and the router should use the faster one.
