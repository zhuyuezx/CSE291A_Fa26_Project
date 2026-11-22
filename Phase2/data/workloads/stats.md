# Request pool: quality report

Built by `build_workloads.py --seed 0 --max-prompt 3500`. Prompt tokens are counted with Qwen3.5's tokenizer on the user message (the chat template adds about 10). Multi-turn rows count the first user turn.

## Per class

| class | items | train / test | sources | prompt tokens p10 / p50 / p90 / max | max_tokens | scorer |
|---|---|---|---|---|---|---|
| chat | 400 | 197 / 203 | allenai/WildChat-1M | 9 / 34 / 552 / 3286 | 1024 | none |
| code | 421 | 204 / 217 | mbpp-sanitized, openai/openai_humaneval | 72 / 122 / 237 / 867 | 512 | humaneval_tests, mbpp_tests |
| instruct | 300 | 157 / 143 | google/IFEval | 24 / 41 / 75 / 117 | 1024 | ifeval |
| knowledge | 342 | 157 / 185 | mmlu-redux-2.0 | 49 / 79 / 166 / 553 | 8 | mc_letter |
| math | 400 | 194 / 206 | HuggingFaceH4/MATH-500, madrylab/gsm8k-platinum | 46 / 76 / 131 / 848 | 512, 1024 | gsm8k_number, math_boxed |
| multiturn | 200 | 98 / 102 | allenai/WildChat-1M, mt_bench | 11 / 34 / 310 / 1474 | 512 | none |
| rag_long | 200 | 96 / 104 | dgslibisey/MuSiQue | 1967 / 2526 / 3156 / 3486 | 64 | qa_em_f1 |
| rag_multihop | 181 | 94 / 87 | platinum-bench/hotpotqa | 198 / 278 / 392 / 521 | 64 | qa_em_f1 |
| rag_short | 161 | 87 / 74 | platinum-bench/squad | 184 / 239 / 344 / 811 | 64 | qa_em_f1 |
| summ | 200 | 109 / 91 | abisee/cnn_dailymail | 353 / 789 / 1407 / 1985 | 256 | rouge_l |
| tool | 300 | 159 / 141 | gorilla-llm/BFCL_v3_simple | 209 / 256 / 322 / 416 | 256 | bfcl_ast |

## Filtering per source

| source | counts |
|---|---|
| allenai/WildChat-1M | rows read: 6000, not English: 2651, duplicate template: 1605, too short/long: 34, kept chat: 400, kept multiturn: 120 |
| HuggingFaceH4/mt_bench_prompts | rows read: 80, kept: 80 |
| madrylab/gsm8k-platinum | rows read: 1209, kept after cleaning: 1209, sampled: 200 |
| HuggingFaceH4/MATH-500 | rows read: 500, sampled: 200 |
| madrylab/platinum-bench/squad | rows read: 250, kept after cleaning: 161 |
| madrylab/platinum-bench/hotpotqa | rows read: 250, kept after cleaning: 181 |
| dgslibisey/MuSiQue | rows read: 2417, answerable, fits: 2230, too long: 187, sampled: 200 |
| abisee/cnn_dailymail | rows read: 600, <= 2000 tokens: 586, sampled: 200 |
| google-research-datasets/mbpp (sanitized) | rows read: 257, kept: 257 |
| openai/openai_humaneval | rows read: 164, kept: 164 |
| google/IFEval | rows read: 541, sampled: 300 |
| edinburgh-dawg/mmlu-redux-2.0 | rows read: 5700, marked ok: 5330, sampled: 342 |
| gorilla-llm/BFCL_v3_simple | rows read: 400, sampled: 300 |
