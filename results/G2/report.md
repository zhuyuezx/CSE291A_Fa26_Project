# Endpoint test report: G2

Generated 2026-11-22T01:52:07Z by Phase2/harness/run_node_tests.sh.
Server settings: THREADS=2 NGL=all PARALLEL=4 CTX=16384.

## Node

```
instance_type=g4dn.xlarge
availability_zone=us-west-2c
private_ip=172.31.11.54
arch=x86_64
cpu=Intel(R) Xeon(R) Platinum 8259CL CPU @ 2.50GHz
vcpus=4
physical_cores=2
mem_total_gib=15
gpu=Tesla T4, 15360 MiB, 595.112.07, 7.5
os=Ubuntu 24.04.5 LTS
kernel=7.0.0-1018-aws
compiler=gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
nvcc=Build cuda_13.2.r13.2/compiler.37434383_0
llama_tag=b12617
llama_commit=44c20b1
serve_model=Qwen3.5-2B-Q4_K_M.gguf
serve_model_sha256=aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223
mmproj_sha256=7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7
setup_time=2026-11-22T01:49:19Z
```

## llama-bench: Qwen3.5-2B Q4_K_M (pp = prefill, tg = decode; tokens/s, mean ± sd of 3 runs)

| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           pp128 |     3267.55 ± 124.54 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           pp512 |      4429.68 ± 51.29 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |          pp2048 |       4433.80 ± 2.79 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |            tg32 |        124.26 ± 0.44 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           tg128 |        124.60 ± 0.23 |

build: 44c20b1 (1)

## llama-bench: Qwen3.5-0.8B Q4_K_M

| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           pp128 |     5322.40 ± 339.70 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           pp512 |     7846.77 ± 117.20 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |          pp2048 |      7813.48 ± 30.31 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |            tg32 |        214.09 ± 0.23 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           tg128 |        217.88 ± 0.40 |

build: 44c20b1 (1)

## Cold start (Qwen3.5-2B + vision projector)

`disk`: page cache dropped first, so the model is read from EBS. `page_cache`: files already in memory.
`start_to_health_s`: systemctl start until /health answers. `first_request_s`: a 1-token request right after.

| mode | rep | start to health s | first request s |
|---|---|---|---|
| disk | 1 | 18.204 | 0.126103 |
| disk | 2 | 17.737 | 0.129915 |
| disk | 3 | 17.721 | 0.123252 |
| page_cache | 1 | 1.903 | 0.083591 |
| page_cache | 2 | 1.906 | 0.083405 |
| page_cache | 3 | 1.913 | 0.083126 |

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


## Memory (llama-server, after all tests)

```
VmHWM:	 1744524 kB
VmRSS:	 1469840 kB
               total        used        free      shared  buff/cache   available
Mem:           15783        1818       11837          50        2458       13964
Swap:              0           0           0
```
