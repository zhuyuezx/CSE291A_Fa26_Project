### Latency and throughput (seconds; throughput in completed requests/min)

| policy | ok | throughput | mean e2e | p50 e2e | p95 e2e | p99 e2e | p50 TTFT | p95 TTFT | requests per endpoint |
|---|---|---|---|---|---|---|---|---|---|
| always:C1 | 30/30 | 12.3 | 18.9 | 19.1 | 35.8 | 37.2 | 7.7 | 15.6 | C1:30 C2:0 |
| always:C2 | 30/30 | 11.2 | 24.5 | 26.7 | 47.3 | 50.2 | 4.8 | 25.1 | C1:0 C2:30 |
| first_idle | 30/30 | 13.4 | 11.1 | 8.3 | 25.1 | 27.7 | 2.0 | 6.6 | C1:16 C2:14 |
| least_outstanding | 30/30 | 13.7 | 11.2 | 9.4 | 22.5 | 24.9 | 2.1 | 7.9 | C1:16 C2:14 |
| random | 30/30 | 13.0 | 13.2 | 10.2 | 29.7 | 32.5 | 2.5 | 6.2 | C1:11 C2:19 |
| round_robin | 30/30 | 13.7 | 11.2 | 8.2 | 24.5 | 25.2 | 1.8 | 7.6 | C1:15 C2:15 |

### Mean end-to-end latency by request class (seconds)

| policy | T1 (n=12) | T2 (n=6) | T3 (n=12) |
|---|---|---|---|
| always:C1 | 12.8 | 13.2 | 27.9 |
| always:C2 | 18.7 | 13.2 | 35.9 |
| first_idle | 6.3 | 8.3 | 17.2 |
| least_outstanding | 6.5 | 8.2 | 17.4 |
| random | 7.7 | 8.5 | 21.1 |
| round_robin | 6.4 | 7.7 | 17.7 |

### Router overhead

| policy | joined | decision p50 µs | decision p99 µs | added latency p50 ms | added latency p99 ms |
|---|---|---|---|---|---|
| always:C1 | 30 | 2.9 | 5.0 | 0.90 | 2.96 |
| always:C2 | 30 | 3.1 | 10.5 | 0.85 | 2.91 |
| first_idle | 30 | 4.7 | 7.7 | 0.78 | 2.91 |
| least_outstanding | 30 | 4.4 | 5.3 | 0.81 | 2.90 |
| random | 30 | 4.3 | 7.4 | 0.74 | 3.00 |
| round_robin | 30 | 1.1 | 2.4 | 0.83 | 2.86 |

0 failed requests.
