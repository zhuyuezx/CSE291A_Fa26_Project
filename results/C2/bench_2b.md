| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           pp128 |        142.53 ± 0.17 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           pp512 |        154.81 ± 0.65 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |          pp2048 |        147.77 ± 0.68 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |            tg32 |         10.34 ± 0.07 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           tg128 |         10.35 ± 0.01 |

build: 44c20b1 (1)
