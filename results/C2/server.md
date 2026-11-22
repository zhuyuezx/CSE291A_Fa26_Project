## Request-level tests: C2 (http://localhost:8080)

57 requests, 0 failed or timed out.

### One request at a time (medians)

| target prompt | output tokens | prompt tokens | TTFT s | prefill tok/s | decode tok/s | end-to-end s | runs |
|---|---|---|---|---|---|---|---|
| 128 | 32 | 201 | 1.49 | 144.3 | 10.7 | 4.47 | 3 |
| 128 | 256 | 204 | 1.50 | 143.9 | 10.4 | 26.07 | 3 |
| 512 | 32 | 607 | 3.75 | 161.2 | 10.6 | 6.76 | 3 |
| 512 | 256 | 608 | 3.76 | 162.7 | 10.3 | 28.62 | 3 |
| 2048 | 32 | 2166 | 13.63 | 160.2 | 10.1 | 16.78 | 3 |
| 2048 | 256 | 2167 | 13.69 | 160.1 | 9.8 | 39.64 | 3 |

### Concurrent requests (prompt 512, output 128; server has a fixed number of slots)

| requests | median TTFT s | max TTFT s | median end-to-end s | per-request decode tok/s | throughput (output tok/s) | vs. 1 request |
|---|---|---|---|---|---|---|
| 1 | 3.56 | 3.88 | 15.90 | 10.4 | 8.1 | 1.00 |
| 2 | 7.34 | 7.74 | 27.35 | 6.4 | 9.3 | 1.16 |
| 4 | 14.29 | 14.67 | 37.43 | 5.5 | 13.6 | 1.69 |
| 8 | 33.23 | 52.20 | 57.04 | 5.5 | 13.6 | 1.69 |

Throughput = all output tokens / wall time from first send to last reply. Requests beyond the slot count wait in the server's queue, which shows up in TTFT.

### Image requests (bar chart, "which bar is tallest?")

| image px | prompt tokens | TTFT s | prefill s (incl. vision) | end-to-end s | correct |
|---|---|---|---|---|---|
| 256 | 102 | 1.65 | 1.65 | 1.75 | 3/3 |
| 512 | 294 | 5.41 | 5.40 | 5.51 | 3/3 |
| 1024 | 1062 | 30.83 | 30.81 | 30.93 | 3/3 |

