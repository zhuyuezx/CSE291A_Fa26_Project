| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           pp128 |     5322.40 ± 339.70 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           pp512 |     7846.77 ± 117.20 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |          pp2048 |      7813.48 ± 30.31 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |            tg32 |        214.09 ± 0.23 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CUDA       |  99 |           tg128 |        217.88 ± 0.40 |

build: 44c20b1 (1)
