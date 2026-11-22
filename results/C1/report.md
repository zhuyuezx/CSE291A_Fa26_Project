# Endpoint test report: C1

Generated 2026-11-22T00:39:40Z by Phase2/harness/run_node_tests.sh.
Server settings: THREADS=4 NGL=0 PARALLEL=4 CTX=16384.

## Node

```
instance_type=c7g.xlarge
availability_zone=us-west-2d
private_ip=172.31.61.18
arch=aarch64
cpu=Neoverse-V1
vcpus=4
physical_cores=4
mem_total_gib=7
os=Ubuntu 26.04.1 LTS
kernel=7.0.0-1018-aws
compiler=gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0
llama_tag=b12617
llama_commit=44c20b1
serve_model=Qwen3.5-2B-Q4_K_M.gguf
serve_model_sha256=aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223
mmproj_sha256=7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7
setup_time=2026-11-21T23:47:05Z
```

## llama-bench: Qwen3.5-2B Q4_K_M (pp = prefill, tg = decode; tokens/s, mean ± sd of 3 runs)

| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           pp128 |        102.84 ± 0.38 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           pp512 |         94.80 ± 1.45 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |          pp2048 |         72.37 ± 0.45 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |            tg32 |         22.57 ± 0.02 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           tg128 |         22.16 ± 0.66 |

build: 44c20b1 (1)

## llama-bench: Qwen3.5-0.8B Q4_K_M

| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |           pp128 |        217.14 ± 0.09 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |           pp512 |        182.94 ± 0.07 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |          pp2048 |        114.27 ± 0.49 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |            tg32 |         47.01 ± 0.04 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |           tg128 |         46.19 ± 1.05 |

build: 44c20b1 (1)

## llama-bench: thread scaling, Qwen3.5-2B

| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       1 |           pp512 |         28.41 ± 0.01 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       1 |           tg128 |          7.02 ± 0.00 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           pp512 |         52.06 ± 0.01 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           tg128 |         12.48 ± 0.01 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           pp512 |         94.29 ± 1.16 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           tg128 |         22.58 ± 0.00 |

build: 44c20b1 (1)

## Cold start (Qwen3.5-2B + vision projector)

`disk`: page cache dropped first, so the model is read from EBS. `page_cache`: files already in memory.
`start_to_health_s`: systemctl start until /health answers. `first_request_s`: a 1-token request right after.

| mode | rep | start to health s | first request s |
|---|---|---|---|
| disk | 1 | 14.846 | 0.183298 |
| disk | 2 | 14.877 | 0.183121 |
| disk | 3 | 14.932 | 0.183131 |
| page_cache | 1 | 1.205 | 0.183543 |
| page_cache | 2 | 1.210 | 0.182801 |
| page_cache | 3 | 1.209 | 0.183974 |

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


## Memory (llama-server, after all tests)

```
VmHWM:	 4048264 kB
VmRSS:	 4048264 kB
               total        used        free      shared  buff/cache   available
Mem:            7755        3198        2685           0        2034        4556
Swap:              0           0           0
```
