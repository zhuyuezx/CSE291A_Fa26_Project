| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       1 |           pp512 |         77.19 ± 0.11 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       1 |           tg128 |          5.38 ± 0.01 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           pp512 |        154.51 ± 0.56 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           tg128 |         10.25 ± 0.06 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           pp512 |        179.18 ± 0.34 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           tg128 |         12.60 ± 0.09 |

build: 44c20b1 (1)
