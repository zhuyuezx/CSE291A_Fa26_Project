## Request-level tests: G2 (http://localhost:8080)

57 requests, 0 failed or timed out.

### One request at a time (medians)

| target prompt | output tokens | prompt tokens | TTFT s | prefill tok/s | decode tok/s | end-to-end s | runs |
|---|---|---|---|---|---|---|---|
| 128 | 32 | 202 | 0.08 | 2600.9 | 120.1 | 0.35 | 3 |
| 128 | 256 | 203 | 0.07 | 2954.3 | 116.9 | 2.26 | 3 |
| 512 | 32 | 607 | 0.18 | 3508.3 | 119.6 | 0.44 | 3 |
| 512 | 256 | 608 | 0.17 | 3617.2 | 116.5 | 2.37 | 3 |
| 2048 | 32 | 2169 | 0.53 | 4163.7 | 118.1 | 0.80 | 3 |
| 2048 | 256 | 2168 | 0.53 | 4162.0 | 115.0 | 2.75 | 3 |

### Concurrent requests (prompt 512, output 128; server has a fixed number of slots)

| requests | median TTFT s | max TTFT s | median end-to-end s | per-request decode tok/s | throughput (output tok/s) | vs. 1 request |
|---|---|---|---|---|---|---|
| 1 | 0.16 | 0.17 | 1.26 | 117.1 | 102.0 | 1.00 |
| 2 | 0.32 | 0.32 | 1.62 | 98.5 | 158.4 | 1.55 |
| 4 | 0.61 | 0.64 | 2.63 | 63.9 | 194.4 | 1.91 |
| 8 | 1.94 | 3.28 | 3.97 | 63.2 | 194.0 | 1.90 |

Throughput = all output tokens / wall time from first send to last reply. Requests beyond the slot count wait in the server's queue, which shows up in TTFT.

### Image requests (bar chart, "which bar is tallest?")

| image px | prompt tokens | TTFT s | prefill s (incl. vision) | end-to-end s | correct |
|---|---|---|---|---|---|
| 256 | 102 | 0.08 | 0.08 | 0.09 | 3/3 |
| 512 | 294 | 0.18 | 0.17 | 0.19 | 3/3 |
| 1024 | 1062 | 0.66 | 0.63 | 0.67 | 3/3 |

