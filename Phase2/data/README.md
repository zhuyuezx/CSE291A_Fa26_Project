# Request pool for Phase 2

3,105 real prompts in 11 request classes, drawn from public datasets. Where a cleaned version exists it is used, and every class except chat and multi-turn has an automatic scorer. The pool replaces the GSM8K-only workload. Its classes differ in the two things that decide where a request should run: prompt length (prefill) and output length (decode).

| File | Contents |
|---|---|
| `workloads/pool.jsonl` | One request per line (schema below) |
| `workloads/stats.md` | Quality report: items, train/test split, prompt-token percentiles per class, and what each filter removed |
| `workloads/mixes.json` | Class weights for the five mixes |
| `pool.py` | `load_pool()`, `load_mixes()`, `sample_mix(pool, mix, n, seed, split)` |
| `build_workloads.py` | Rebuilds everything from the sources |

## Classes and sources

Prompt tokens are counted with Qwen3.5's tokenizer (median shown; see `stats.md` for p10/p90/max).

| class | items | source (license) | prompt tokens, median | shape | scorer |
|---|---|---|---|---|---|
| chat | 400 | [WildChat-1M](https://huggingface.co/datasets/allenai/WildChat-1M) (ODC-BY), English first turns | 34 (p90 552) | real traffic, long tail | none |
| multiturn | 200 | WildChat sessions of 2–4 turns + [MT-Bench](https://huggingface.co/datasets/HuggingFaceH4/mt_bench_prompts) (Apache-2.0) | 34 first turn | context grows each turn | none |
| math | 400 | [GSM8K-Platinum](https://huggingface.co/datasets/madrylab/gsm8k-platinum) (MIT) + [MATH-500](https://huggingface.co/datasets/HuggingFaceH4/MATH-500) | 76 | short in, long reasoning out | final number / `\boxed{}` |
| rag_short | 161 | [Platinum-bench SQuAD2.0](https://huggingface.co/datasets/madrylab/platinum-bench) (CC BY-SA 4.0), includes unanswerable | 239 | paragraph in, short answer | EM / F1 |
| rag_multihop | 181 | Platinum-bench HotpotQA (gold paragraphs only) | 278 | two paragraphs, short answer | EM / F1 |
| rag_long | 200 | [MuSiQue](https://huggingface.co/datasets/dgslibisey/MuSiQue) answerable, all 20 paragraphs | 2,526 | long in, short out | EM / F1 with aliases |
| summ | 200 | [CNN/DailyMail 3.0.0](https://huggingface.co/datasets/abisee/cnn_dailymail) (Apache-2.0), articles ≤ 2K tokens | 789 | long in, ~100 out | ROUGE-L |
| code | 421 | [MBPP sanitized](https://huggingface.co/datasets/google-research-datasets/mbpp) (CC BY 4.0) + [HumanEval](https://huggingface.co/datasets/openai/openai_humaneval) (MIT) | 122 | short in, code out | unit tests |
| instruct | 300 | [IFEval](https://huggingface.co/datasets/google/IFEval) (Apache-2.0) | 41 | output length set by the instruction | IFEval checks |
| knowledge | 342 | [MMLU-Redux 2.0](https://huggingface.co/datasets/edinburgh-dawg/mmlu-redux-2.0) (CC BY 4.0), 6 per subject | 79 | almost prefill only | letter |
| tool | 300 | [BFCL v3 simple](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard) (Apache-2.0) | 256 | function specs in, JSON call out | AST match |

## Quality choices

- **Cleaned labels where they exist.** The original GSM8K test set has label errors in about 5% of items, so math uses GSM8K-Platinum, which drops or fixes them. SQuAD2.0 and HotpotQA come from Platinum-bench with the items its cleaners rejected removed (89 and 69). About 6.5% of MMLU questions are wrong, so knowledge uses MMLU-Redux 2.0 and keeps only questions its annotators marked `ok` (5,330 of 5,700). MBPP uses the hand-verified *sanitized* subset.
- **WildChat filtering.**
  - Kept: English conversations not flagged toxic or redacted.
  - Dropped: turns that are mostly non-ASCII, because the language label covers the whole conversation; near-duplicates (same first 100 characters); and any prompt beyond the second that shares its first 5 words with earlier ones. Without that last cap, one user's template took 16% of the sample.
  - Kept fields: conversation text, model, turn count, and conversation hash. IPs, locations, and request headers are not.
- **Length cap.** Prompts above 3,500 tokens are dropped. The endpoints share a 16K context across 4 slots, and a 4K prompt already takes 30–70 s to prefill on the CPU nodes. This removed 187 MuSiQue items and 14 CNN articles.
- **Train/test split.** Each item is assigned to `train` or `test` by a hash of its id, about 50/50 per class. A learned router trains on `train`, and evaluation uses `test`.

## Mixes

`dev-balanced` is for building and tuning routers. The other four shift the class balance and are held out:

| mix | main classes | prompt tokens p50 / p90 (500 test samples) |
|---|---|---|
| dev-balanced | chat 25%, math 12%, code 10%, instruct 10%, RAG 20% | 104 / 934 |
| real-chat | chat 55%, multiturn 15% | 57 / 655 |
| rag-enterprise | RAG 55%, summ 20% | 313 / 2,485 |
| reasoning | math 35%, code 30%, instruct 15% | 77 / 184 |
| agent-tools | tool 45%, RAG 35% | 248 / 348 |

## Item schema

```json
{"id": "madrylab/gsm8k-platinum:3f2a...", "cls": "math", "source": "madrylab/gsm8k-platinum",
 "split": "train", "messages": [{"role": "user", "content": "..."}], "max_tokens": 512,
 "scorer": "gsm8k_number", "reference": "18", "prompt_tokens": 76, "meta": {}}
```

Multi-turn items have `messages: null` and `meta.user_turns`. They are meant to be replayed turn by turn, with the model's own replies in between. For those items `prompt_tokens` is a list with one entry per turn.

## Not done yet

- **Output lengths for our model.** These are the labels a length predictor or a learned router needs. They depend on the serving model, so they come from running the pool through Qwen3.5-2B (thinking off, our server settings), which is about 1–2 h on G2 while holding the fleet lock.
- **Scorers.** Only the scorer names are recorded. The scoring code (EM/F1, ROUGE-L, sandboxed unit tests, IFEval checks, BFCL AST match) still has to be written.

## Rebuilding

```bash
pip install tokenizers
curl -L -o qwen_tokenizer.json https://huggingface.co/Qwen/Qwen3.5-2B/resolve/main/tokenizer.json
python3 Phase2/data/build_workloads.py --tokenizer qwen_tokenizer.json --cache /tmp/hf-cache
```

The dataset viewer API rate-limits large pulls (WildChat especially). The script backs off and retries, and `--cache` keeps fetched pages so a re-run does not refetch them. The same `--seed` gives the same pool.
