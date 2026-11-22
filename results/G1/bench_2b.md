| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           pp128 |       743.65 ± 39.99 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           pp512 |       1279.64 ± 2.94 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |          pp2048 |       1302.47 ± 8.16 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |            tg32 |         16.41 ± 0.22 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CUDA       |  99 |           tg128 |         16.56 ± 0.02 |

build: 44c20b1 (1)
