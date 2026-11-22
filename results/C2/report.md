# Endpoint test report: C2

Generated 2026-11-22T00:38:10Z by Phase2/harness/run_node_tests.sh.
Server settings: THREADS=2 NGL=0 PARALLEL=4 CTX=16384.

## Node

```
instance_type=c7i.xlarge
availability_zone=us-west-2b
private_ip=172.31.41.144
arch=x86_64
cpu=Intel(R) Xeon(R) Platinum 8488C
vcpus=4
physical_cores=2
mem_total_gib=7
os=Ubuntu 26.04.1 LTS
kernel=7.0.0-1018-aws
compiler=gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0
llama_tag=b12617
llama_commit=44c20b1
serve_model=Qwen3.5-2B-Q4_K_M.gguf
serve_model_sha256=aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223
mmproj_sha256=7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7
setup_time=2026-11-22T00:17:43Z
```

## llama-bench: Qwen3.5-2B Q4_K_M (pp = prefill, tg = decode; tokens/s, mean ± sd of 3 runs)

| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           pp128 |        142.53 ± 0.17 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           pp512 |        154.81 ± 0.65 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |          pp2048 |        147.77 ± 0.68 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |            tg32 |         10.34 ± 0.07 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           tg128 |         10.35 ± 0.01 |

build: 44c20b1 (1)

## llama-bench: Qwen3.5-0.8B Q4_K_M

| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |           pp128 |        291.00 ± 0.86 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |           pp512 |        307.48 ± 9.56 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |          pp2048 |        289.09 ± 0.50 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |            tg32 |         23.82 ± 0.02 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |           tg128 |         23.71 ± 0.04 |

build: 44c20b1 (1)

## llama-bench: thread scaling, Qwen3.5-2B

| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       1 |           pp512 |         77.19 ± 0.11 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       1 |           tg128 |          5.38 ± 0.01 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           pp512 |        154.51 ± 0.56 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           tg128 |         10.25 ± 0.06 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           pp512 |        179.18 ± 0.34 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           tg128 |         12.60 ± 0.09 |

build: 44c20b1 (1)

## Cold start (Qwen3.5-2B + vision projector)

`disk`: page cache dropped first, so the model is read from EBS. `page_cache`: files already in memory.
`start_to_health_s`: systemctl start until /health answers. `first_request_s`: a 1-token request right after.

| mode | rep | start to health s | first request s |
|---|---|---|---|
| disk | 1 | 14.975 | 0.298937 |
| disk | 2 | 14.796 | 0.290711 |
| disk | 3 | 14.831 | 0.290537 |
| page_cache | 1 | 1.505 | 0.286162 |
| page_cache | 2 | 1.511 | 0.286600 |
| page_cache | 3 | 1.499 | 0.286104 |

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


## Memory (llama-server, after all tests)

```
VmHWM:	 4030612 kB
VmRSS:	 4030612 kB
               total        used        free      shared  buff/cache   available
Mem:            7774        3214        2755           2        2052        4560
Swap:              0           0           0
```
