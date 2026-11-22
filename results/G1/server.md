## Request-level tests: G1 (http://localhost:8080)

48 requests, 0 failed or timed out.

### One request at a time (medians)

| target prompt | output tokens | prompt tokens | TTFT s | prefill tok/s | decode tok/s | end-to-end s | runs |
|---|---|---|---|---|---|---|---|
| 128 | 32 | 204 | 0.32 | 587.6 | 15.5 | 2.38 | 3 |
| 128 | 256 | 204 | 0.30 | 684.8 | 15.0 | 17.33 | 3 |
| 512 | 32 | 609 | 0.65 | 944.5 | 15.5 | 2.70 | 3 |
| 512 | 256 | 608 | 0.63 | 966.9 | 15.0 | 17.67 | 3 |
| 2048 | 32 | 2166 | 1.83 | 1195.9 | 15.4 | 3.92 | 3 |
| 2048 | 256 | 2169 | 1.83 | 1188.4 | 15.0 | 18.88 | 3 |

### Concurrent requests (prompt 512, output 128; server has a fixed number of slots)

| requests | median TTFT s | max TTFT s | median end-to-end s | per-request decode tok/s | throughput (output tok/s) | vs. 1 request |
|---|---|---|---|---|---|---|
| 1 | 0.60 | 0.63 | 9.04 | 15.2 | 14.2 | 1.00 |
| 2 | 1.08 | 1.10 | 9.61 | 15.0 | 26.6 | 1.88 |
| 4 | 2.35 | 2.45 | 13.09 | 11.9 | 39.1 | 2.76 |
| 8 | 8.74 | 15.43 | 19.54 | 11.9 | 39.4 | 2.78 |

Throughput = all output tokens / wall time from first send to last reply. Requests beyond the slot count wait in the server's queue, which shows up in TTFT.

