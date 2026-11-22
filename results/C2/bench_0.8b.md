| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |           pp128 |        291.00 ± 0.86 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |           pp512 |        307.48 ± 9.56 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |          pp2048 |        289.09 ± 0.50 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |            tg32 |         23.82 ± 0.02 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       2 |           tg128 |         23.71 ± 0.04 |

build: 44c20b1 (1)
