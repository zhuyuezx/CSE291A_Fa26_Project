| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           pp128 |       1273.31 ± 6.37 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           pp512 |      2145.49 ± 78.03 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |          pp2048 |       2194.06 ± 2.01 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |            tg32 |         26.78 ± 2.16 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           tg128 |         28.38 ± 0.11 |

build: 44c20b1 (1)
