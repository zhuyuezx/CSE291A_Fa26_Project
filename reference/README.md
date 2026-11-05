# References: related work and usable benchmarks

Survey of existing solutions for our project (Option 3: adaptive routing across heterogeneous machines). Papers are linked rather than stored.

## Where our project sits

Existing work splits into three groups:

- **Query routing** picks *which model* answers a query from its content, but treats every model as a remote API with fixed cost.
- **Heterogeneous serving** decides *where* one model runs across mixed GPUs, but ignores request content and model choice.
- **Edge–cloud collaboration** combines both ideas, but usually with a cloud API as the large model.

We study the combination on a fleet we control: CPU instances plus laptops, text plus images, where model choice, device placement, queueing, and which models are loaded all interact.

## 1. Related work

### Query routing across models (content-based tier selection)

| Work | Venue | Idea | Relevance |
|---|---|---|---|
| [RouteLLM](https://arxiv.org/abs/2406.18665) | arXiv 2024 | Learns a router between a strong and a weak model from preference data. | Template for our R2/R3 routers. |
| [Hybrid LLM](https://arxiv.org/abs/2404.14618) | ICLR 2024 | Routes each query to a small or large model by predicted difficulty, with a tunable quality target; up to 40% fewer large-model calls at no quality drop. | Same small-vs-large decision as our tier selector; its quality knob matches our τ. |
| [FrugalGPT](https://arxiv.org/abs/2305.05176) | arXiv 2023 | LLM cascades: try cheap models first, escalate when a scorer is unsure. | Basis for our R4 cascade. |
| [RouterBench](https://arxiv.org/abs/2403.12031) | ICML 2024 | Benchmark of 405k+ precomputed inference outcomes for evaluating routers on cost and quality. | Offline router evaluation, the same method as our `route_sim.py`. |
| [RouterEval](https://arxiv.org/abs/2503.10657) | arXiv 2025 | 200M+ performance records over 8,500+ LLMs and 12 evaluations; reports that most routers have large headroom. | Extra labeled data for training and testing routers. |
| [LLMRouterBench](https://arxiv.org/abs/2601.07206) | arXiv 2026 | 400k+ instances from 21 datasets and 33 models; finds many routers perform similarly under a unified evaluation. | Warns us to compare against simple baselines (R1). |

### Edge–cloud collaborative inference

| Work | Venue | Idea | Relevance |
|---|---|---|---|
| [Cloud–edge LLM/SLM collaboration survey](https://arxiv.org/abs/2507.16731) | arXiv 2025 | Taxonomy: task assignment, task division, and mixture-based collaboration. | Positions our laptop/AWS split. |
| [Routing across edge and cloud with NSGA-II](https://arxiv.org/abs/2507.15553) | arXiv 2025 | Multi-objective routing of requests between edge and cloud LLM instances; 34.9% lower cost with a slight latency increase. | Closest to our placement problem. |
| [HybridFlow](https://arxiv.org/abs/2512.22137) | arXiv 2025 | Splits queries into subtasks routed to edge or cloud under latency and token budgets. | Finer-grained than our per-request routing. |
| [ConsRoute](https://arxiv.org/abs/2603.21237) | arXiv 2026 | Three-tier device/edge/cloud routing by predicted semantic consistency. | Closest to a laptop-as-device tier. |
| [CE-LSLM](https://arxiv.org/abs/2505.14085) | arXiv 2025 | Cloud LLM + edge SLM, overlapping model loading with decoding. | Related to our model-load cost $L_{i,m}$. |
| [PICE](https://arxiv.org/abs/2501.09367) | arXiv 2025 | Semantic-level cloud–edge serving with dynamic task scheduling. | Related scheduling design. |

### Serving on heterogeneous hardware

| Work | Venue | Idea | Relevance |
|---|---|---|---|
| [Helix](https://arxiv.org/abs/2406.01566) | ASPLOS 2025 | Max-flow / MILP placement and request scheduling over heterogeneous GPUs and networks. | Joint placement + scheduling, but for one model split across GPUs (out of our scope). |
| [HexGen](https://arxiv.org/abs/2311.11514) | ICML 2024 | Asymmetric tensor/pipeline parallelism across heterogeneous GPUs. | Same contrast: model splitting vs. our whole-request routing. |
| [Mélange](https://arxiv.org/abs/2404.14527) | arXiv 2024 | Picks a cost-efficient mix of GPU types from request size and rate. | Request-shape-dependent device choice, like our hypothesis H1. |

### Request scheduling, load balancing, and cache-aware placement

| Work | Venue | Idea | Relevance |
|---|---|---|---|
| [Llumnix](https://arxiv.org/abs/2406.03243) | OSDI 2024 | Live migration of requests and their KV state across instances. | Our session-migration cost $C_i$; when moving a session pays off. |
| [Preble](https://arxiv.org/abs/2407.00023) | ICLR 2025 | Prefix-cache-aware distributed scheduling that trades cache reuse against load. | Our affinity vs. load-balancing trade-off. |
| [Learning to Rank for LLM scheduling](https://arxiv.org/abs/2408.15792) | NeurIPS 2024 | Predicts the *rank* of output lengths to approximate shortest-job-first. | Our output-length predictor ô and SJF queue. |
| [S3](https://arxiv.org/abs/2306.06000) | arXiv 2023 | Predicts output length to size memory and batches. | Another output-length predictor. |
| [vLLM / PagedAttention](https://arxiv.org/abs/2309.06180) | SOSP 2023 | Paged KV cache with continuous batching. | Batching behaviour of the engines we measure. |
| [DistServe](https://arxiv.org/abs/2401.09670) | OSDI 2024 | Disaggregates prefill and decode onto different GPUs. | Prefill vs. decode as separate cost terms. |
| [Splitwise](https://arxiv.org/abs/2311.18677) | ISCA 2024 | Prefill/decode phase splitting across machine types; released Azure traces. | Phase-aware placement on heterogeneous machines. |
| [Mooncake](https://arxiv.org/abs/2407.00079) | FAST 2025 | KV-cache-centric disaggregated serving. | KV transfer vs. recompute. |

### Multimodal serving

| Work | Venue | Idea | Relevance |
|---|---|---|---|
| [EPD disaggregation](https://arxiv.org/abs/2501.05460) | arXiv 2025 | Splits encode, prefill, and decode onto separate resources. | Vision encoding as its own cost term $V_i$. |
| [ModServe](https://arxiv.org/abs/2502.00937) | arXiv 2025 | Modality- and stage-aware disaggregation; 3.3–5.5× throughput under bursty multimodal traffic. | Image requests need modality-aware routing. |

### Local / Apple-Silicon inference

| Work | Venue | Idea | Relevance |
|---|---|---|---|
| [Production-grade local LLM inference on Apple Silicon](https://arxiv.org/abs/2511.05502) | arXiv 2025 | Compares MLX, MLC-LLM, Ollama, llama.cpp and PyTorch MPS on Apple Silicon (throughput and TTFT). | Baseline expectations for our laptop tier. |
| M. Harchol-Balter, *Performance Modeling and Design of Computer Systems* | CUP 2013 | Queueing theory for heterogeneous servers (JSQ, SED, the slow-server problem). | Theory behind our completion-time routing. |

## 2. Benchmarks and datasets we can use

| Benchmark | What it provides | License | Use in our project |
|---|---|---|---|
| [GSM8K](https://github.com/openai/grade-school-math) | 1,319 test math word problems with numeric answers | MIT | **Used now:** E5 tier labels (`Phase1/data/`) |
| [MMLU](https://github.com/hendrycks/test) | Multiple-choice questions over 57 subjects | MIT | More tier labels with short outputs |
| [ChartQA](https://github.com/vis-nlp/ChartQA) / [TextVQA](https://textvqa.org/) | Image QA with exact-match answers | GPL-3.0 / CC BY 4.0 | Image classes M1/M2 with programmatic checks |
| [MMMU](https://mmmu-benchmark.github.io/) | Multi-discipline image QA | Apache-2.0 | Harder image tier labels |
| [ShareGPT](https://huggingface.co/datasets/anon8231489123/ShareGPT_Vicuna_unfiltered) / [LMSYS-Chat-1M](https://huggingface.co/datasets/lmsys/lmsys-chat-1m) | Real conversations: prompt and response lengths | varies / LMSYS license | Length distributions for T1 and multi-turn T4 |
| [BurstGPT](https://github.com/HPMLL/BurstGPT) | 10.31M Azure OpenAI request traces over 213 days: timestamps and request/response token counts | CC BY 4.0 | Replay real bursty arrivals in E2 |
| [Azure LLM inference traces](https://github.com/Azure/AzurePublicDataset) | Timestamps with context and generated token counts | CC BY 4.0 | Alternative arrival and length traces |
| [RouterBench](https://github.com/withmartian/routerbench), [RouterEval](https://arxiv.org/abs/2503.10657), [LLMRouterBench](https://github.com/ynulihao/LLMRouterBench) | Precomputed per-model outcomes on many prompts | see repos | Train and test R2/R3 beyond our own models |

## 3. Benchmarking tools

| Tool | What it does | Use |
|---|---|---|
| [`llama-bench`](https://github.com/ggml-org/llama.cpp) | Prefill and decode microbenchmarks in llama.cpp | E1 on AWS endpoints |
| [vLLM `benchmark_serving.py`](https://github.com/vllm-project/vllm) | Serving benchmark with Poisson/gamma ("burstiness") arrivals | Our `run_load.py` uses the same gamma-arrival idea |
| [GuideLLM](https://github.com/vllm-project/guidellm) | Load-scenario benchmarks against OpenAI-compatible servers | Cross-check our load generator |
| [LLMPerf](https://github.com/ray-project/llmperf) | Throughput and latency benchmarks for hosted APIs | Cross-check |
| [Vidur](https://arxiv.org/abs/2405.05465) | Profile-driven LLM inference simulator (<9% latency error) | Simulating routing policies at larger scale |
