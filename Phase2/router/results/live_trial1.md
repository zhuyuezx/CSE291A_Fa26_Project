# Live routing run trial1

Endpoints: C1 (http://172.31.61.18:8080), C2 (http://172.31.41.144:8080). Mix A-balanced, images [256, 512] px, 40 requests per policy at 4.89 req/min (load 0.5, arrival CV 1, seed 0). SLO = 3x the best idle-node latency. Prediction error is ECT's predicted latency on the chosen node vs. the measured one.

| policy | mean e2e s | p50 e2e s | p95 e2e s | p95 TTFT s | SLO met | ECT pred. median abs. error | bias | image answers | share | failed |
|---|---|---|---|---|---|---|---|---|---|---|
| round-robin | 25.9 | 23.6 | 57.5 | 35.3 | 78% | 13% | -5% | 4/4 | C1:0.50 C2:0.50 | 0 |
| JSQ | 26.0 | 22.2 | 64.4 | 32.2 | 75% | 11% | -4% | 4/4 | C1:0.55 C2:0.45 | 0 |
| SED | 18.8 | 16.7 | 37.5 | 28.9 | 95% | 16% | -4% | 4/4 | C1:0.60 C2:0.40 | 0 |
| ECT-global | 19.2 | 16.8 | 36.2 | 20.4 | 92% | 17% | -3% | 4/4 | C1:0.55 C2:0.45 | 0 |
