| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           pp128 |     3267.55 ± 124.54 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           pp512 |      4429.68 ± 51.29 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |          pp2048 |       4433.80 ± 2.79 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |            tg32 |        124.26 ± 0.44 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           tg128 |        124.60 ± 0.23 |

build: 44c20b1 (1)
