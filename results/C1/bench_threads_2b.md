| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       1 |           pp512 |         28.41 ± 0.01 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       1 |           tg128 |          7.02 ± 0.00 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           pp512 |         52.06 ± 0.01 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       2 |           tg128 |         12.48 ± 0.01 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           pp512 |         94.29 ± 1.16 |
| qwen35 2B Q4_K - Medium        |   1.18 GiB |     1.88 B | CPU        |       4 |           tg128 |         22.58 ± 0.00 |

build: 44c20b1 (1)
