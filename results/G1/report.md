# Endpoint test report: G1

Generated 2026-11-22T03:12:59Z by Phase2/harness/run_node_tests.sh.
Server settings: THREADS=1 NGL=all PARALLEL=4 CTX=16384.

## Node

```
instance_type=g6f.large
availability_zone=us-west-2d
private_ip=172.31.56.6
arch=x86_64
cpu=AMD EPYC 7R13 Processor
vcpus=2
physical_cores=1
mem_total_gib=7
gpu=NVIDIA L4-3Q, 3072 MiB, 580.159.03, 8.9
os=Ubuntu 24.04.5 LTS
kernel=7.0.0-1018-aws
compiler=gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
nvcc=Build cuda_13.0.r13.0/compiler.36424714_0
llama_tag=b12617
llama_commit=44c20b1
serve_model=Qwen3.5-2B-Q4_K_M.gguf
serve_model_sha256=aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223
vision=0
setup_time=2026-11-22T03:03:23Z
```

## llama-bench: Qwen3.5-2B Q4_K_M (pp = prefill, tg = decode; tokens/s, mean ± sd of 3 runs)

| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           pp128 |       743.65 ± 39.99 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           pp512 |       1279.64 ± 2.94 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |          pp2048 |       1302.47 ± 8.16 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |            tg32 |         16.41 ± 0.22 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           tg128 |         16.56 ± 0.02 |

build: 44c20b1 (1)

## llama-bench: Qwen3.5-0.8B Q4_K_M

| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           pp128 |       1273.31 ± 6.37 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           pp512 |      2145.49 ± 78.03 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |          pp2048 |       2194.06 ± 2.01 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |            tg32 |         26.78 ± 2.16 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           tg128 |         28.38 ± 0.11 |

build: 44c20b1 (1)

## Cold start (Qwen3.5-2B-Q4_K_M.gguf)

`disk`: page cache dropped first, so the model is read from EBS. `page_cache`: files already in memory.
`start_to_health_s`: systemctl start until /health answers. `first_request_s`: a 1-token request right after.

| mode | rep | start to health s | first request s |
|---|---|---|---|
| disk | 1 | 13.720 | 0.221886 |
| disk | 2 | 13.476 | 0.214934 |
| disk | 3 | 13.314 | 0.215223 |
| page_cache | 1 | 2.025 | 0.188747 |
| page_cache | 2 | 2.024 | 0.202265 |
| page_cache | 3 | 2.033 | 0.191694 |

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


## Memory (llama-server, after all tests)

```
VmHWM:	 1615952 kB
VmRSS:	 1143428 kB
               total        used        free      shared  buff/cache   available
Mem:            7606        1206        5039          49        1657        6399
Swap:              0           0           0
```
