## Request-level tests: C1 (http://localhost:8080)

57 requests, 0 failed or timed out.

### One request at a time (medians)

| target prompt | output tokens | prompt tokens | TTFT s | prefill tok/s | decode tok/s | end-to-end s | runs |
|---|---|---|---|---|---|---|---|
| 128 | 32 | 204 | 2.10 | 96.9 | 22.7 | 3.51 | 3 |
| 128 | 256 | 203 | 2.16 | 96.1 | 21.7 | 13.94 | 3 |
| 512 | 32 | 609 | 6.72 | 91.2 | 22.2 | 8.16 | 3 |
| 512 | 256 | 607 | 6.72 | 90.8 | 21.5 | 18.86 | 3 |
| 2048 | 32 | 2168 | 30.98 | 69.8 | 20.5 | 32.55 | 3 |
| 2048 | 256 | 2167 | 31.14 | 69.6 | 19.6 | 44.12 | 3 |

### Concurrent requests (prompt 512, output 128; server has a fixed number of slots)

| requests | median TTFT s | max TTFT s | median end-to-end s | per-request decode tok/s | throughput (output tok/s) | vs. 1 request |
|---|---|---|---|---|---|---|
| 1 | 6.26 | 6.77 | 12.17 | 21.6 | 10.5 | 1.00 |
| 2 | 13.01 | 13.99 | 24.58 | 11.1 | 10.4 | 0.99 |
| 4 | 25.87 | 26.39 | 34.61 | 14.6 | 14.8 | 1.40 |
| 8 | 42.39 | 60.80 | 51.49 | 14.6 | 15.0 | 1.43 |

Throughput = all output tokens / wall time from first send to last reply. Requests beyond the slot count wait in the server's queue, which shows up in TTFT.

### Image requests (bar chart, "which bar is tallest?")

| image px | prompt tokens | TTFT s | prefill s (incl. vision) | end-to-end s | correct |
|---|---|---|---|---|---|
| 256 | 101 | 6.85 | 6.85 | 6.90 | 3/3 |
| 512 | 294 | 31.42 | 31.41 | 31.46 | 3/3 |
| 1024 | 1060 | 211.29 | 211.28 | 211.34 | 3/3 |

