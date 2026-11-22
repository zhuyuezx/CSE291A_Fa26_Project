| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |           pp128 |        217.14 ± 0.09 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |           pp512 |        182.94 ± 0.07 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |          pp2048 |        114.27 ± 0.49 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |            tg32 |         47.01 ± 0.04 |
| qwen35 0.8B Q4_K - Medium      | 497.39 MiB |   752.39 M | CPU        |       4 |           tg128 |         46.19 ± 1.05 |

build: 44c20b1 (1)
