# Phase 1 findings (laptop endpoint)

All runs are on one laptop endpoint: Apple M4 Pro, 48 GB, Ollama 0.40.14 (Metal), thinking off. Full tables are in [results.md](results.md); raw per-request logs are in [raw/](raw/).

## Measurements

1. **Model speed (E1).** Decode throughput is 182 tok/s for Qwen3.5-0.8B, 88 for 2B, and 62 for 35B-A3B.
   - The MoE has 16× the 2B model's parameters but decodes at 70% of its speed, because only 3B parameters are active per token.
   - Prefill shows a bigger gap: 4,620, 2,110 and 719 tok/s respectively.
   - So the cost model must use *active* parameters, and prefill-heavy requests penalize the MoE most.
2. **Cold start (E4).** Loading a model takes 0.6 s for 0.8B and 2B, but 9.1 s for 35B-A3B (21 GB resident). Swapping models in and out (dynamic placement) is only worth it when the expected gain exceeds this cost.
3. **Images (E1).** Visual tokens grow with resolution: about 103, 294 and 1,062 tokens at 256, 512 and 1024 px.
   - Image TTFT grows with them: 0.06 s → 0.50 s on 0.8B, and 0.39 s → 2.87 s on 35B-A3B.
   - Every Qwen3.5 model answered the chart question correctly at every resolution.
4. **Quality and tier labels (E5, 100 GSM8K problems).** Accuracy is 47% (0.8B), 76% (2B) and 97% (35B-A3B); gemma3:1b scores 43%.
   - The smallest correct model is 0.8B for 47 problems and the 35B for only 11.
5. **Content-based routing (offline, using single-request latencies on this laptop).**
   - 0.8B ↔ 35B: a perfect router (oracle) reaches 97% accuracy at 2.54 s mean latency, versus 3.11 s for always-35B (18% faster). The R1 length rule reaches 91% at 2.85 s.
   - The R2 TF-IDF classifier, trained on only 100 labels, barely separates easy from hard problems.
   - 2B ↔ 35B: the oracle saves only 9% latency, because the MoE is almost as fast as the 2B here.
6. **Load (E2, 0.8B, mixed T1/T2/T3 requests).**
   - Ollama served one request at a time: peak concurrent decode was 1.
   - Throughput saturates at about 1.4 req/s. p95 TTFT rises from 0.77 s at 0.5 req/s to 11.8 s at 4 req/s.
   - Bursty arrivals (gamma, CV = 3) at the same 0.5 req/s mean give a p95 TTFT of 8.5 s, 11× the steady case.
   - CPU utilization stays at 3–5%: the work runs on the GPU.

7. **Can a model's config predict its cost? ([theory.md](theory.md)).** The roofline estimates in `harness/theory.py` use only `configs/models.json` and `configs/hardware.json`. They are checked by leaving one model out: calibrate on the other four, then predict the fifth from its config, as if it were a new model added at cold start.
   - **Memory:** config alone is enough. Pure theory is within 6% (median); after calibration the held-out error is 4%, at most 14%.
   - **Prefill:** pure theory is 67% off, because Apple's GPU peak FLOP/s is not published and the estimate used is optimistic. But efficiency is stable at 0.53–0.67 across models, so one calibration factor per device brings the held-out error down to 12% (max 40%).
   - **Decode:** efficiency varies more (0.53–0.89), giving a held-out error of 22% (max 57%). It is lowest for the tiny gemma3:1b, where fixed per-token overhead dominates, and for the MoE (0.61). Adding a per-token overhead term reduces the worst case to 43% but not the median (24%).
   - **Load time:** not predictable from file size alone (held-out error 30%, max 154%). It depends on whether the file is already in the OS page cache: the just-downloaded 2B loaded 3.1 GB in 0.6 s, while the 35B took 9.1 s for 23.9 GB.
   - **Takeaway for the router:** a new model can be admitted from its config plus one device calibration, with memory accurate and prefill/decode within roughly 10–25%. The router should then refine the estimate online from the first few real requests (the EWMA in the design), and should measure load time rather than predict it.
   - **Example:** the never-run 27B dense model (`qwen3.8`) is predicted at about 12 tok/s decode, 111 tok/s prefill and 16.7 GB resident.

## What this means for Phase 2

- On a single device, routing to a smaller model saves little latency (9–18%). Queueing under load and bursts costs far more (TTFT ×10 or worse).
- So the router's main lever is spreading load across devices: queue-aware placement plus model tier choice, not tier choice alone. This supports hypothesis H3.
- Content-based tier selection needs more labeled data than 100 problems, for example from RouterBench or RouterEval.

## Caveats

- One laptop only; the AWS CPU endpoints are not measured yet.
- Quantization is not matched: Ollama's default `qwen3.5:0.8b` and `:2b` tags are MXFP8, while the other models are Q4_K_M.
- `qwen3-vl:4b` ignores `think: false` in this Ollama version, so its outputs include hidden reasoning. Its E5 numbers and image runs (no answer within 8 tokens) are not comparable and are excluded from the conclusions above.
- Small samples: 3 repetitions per E1 point, 100 GSM8K problems, 30 requests per load point.
- GPU utilization was not sampled (it needs `sudo powermetrics`).
- The `qwen3.5:2b` download overlapped the first E1/E5 runs of the other models.
