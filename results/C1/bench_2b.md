| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           pp128 |        102.84 ± 0.38 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           pp512 |         94.80 ± 1.45 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |          pp2048 |         72.37 ± 0.45 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |            tg32 |         22.57 ± 0.02 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           tg128 |         22.16 ± 0.66 |

build: 44c20b1 (1)
