# CSE 291A Fall 2026 Project: Adaptive Routing Across Heterogeneous Machines

Option 3. We route text and image requests for [Qwen3.5](https://huggingface.co/collections/Qwen/qwen35) models across AWS CPU instances and Apple-Silicon laptops, served with [llama.cpp](https://github.com/ggml-org/llama.cpp).

- **Phase 1 report:** [`Phase1/report/phase1_report.pdf`](Phase1/report/phase1_report.pdf)
- **Phase 1 results:** [`Phase1/results/findings.md`](Phase1/results/findings.md) (key findings), [`Phase1/results/results.md`](Phase1/results/results.md) (all tables and figures)
- **Related work and benchmarks:** [`reference/README.md`](reference/README.md)

## Team

| Name | Email |
|---|---|
| Jason Zhu | jaz019@ucsd.edu |
| Fengfei Yu | fey006@ucsd.edu |
| Hanyu Li | hal209@ucsd.edu |
| Mengyao Ma | mem032@ucsd.edu |
| Zavier Zhao | zhz214@ucsd.edu |

## Repository layout

```
reference/                 # related work and usable benchmarks
Phase1/
  req.txt                  # course requirements
  report/                  # Phase 1 report (.tex and .pdf)
  configs/                 # model architecture configs and device specs for cost estimation
  harness/                 # measurement code (see below)
  data/                    # GSM8K sample and generated chart images
  results/
    raw/                   # per-request JSONL logs and run metadata
    summary/               # CSV summaries
    figures/               # plots
    results.md             # summary tables and figures
  run_all.sh               # runs every experiment, then the analysis
```

## Running the Phase 1 experiments

Needs Python 3.10+ and a local [Ollama](https://ollama.com) server.

```bash
pip install -r Phase1/requirements.txt
ollama pull qwen3.5:0.8b    # and the other models listed in run_all.sh; missing ones are skipped
Phase1/run_all.sh
```

| Script (`Phase1/harness/`) | Experiment |
|---|---|
| `run_profile.py` | E1 prefill/decode/TTFT vs. prompt and output length, image requests; E4 cold-start load time |
| `run_load.py` | E2 open-loop load test (Poisson and bursty arrivals) |
| `run_quality.py` | E5 GSM8K accuracy per model, giving each problem's smallest correct model |
| `route_sim.py` | Offline evaluation of routing policies on the E5 data |
| `analyze.py` | Writes `results/summary/`, `results/figures/`, and `results/results.md` |
| `theory.py` | Config-only roofline estimates of prefill, decode, memory, and load time |
| `compare_theory.py` | Compares those estimates with the measurements; writes `results/theory.md` |

## Building the report

```bash
cd Phase1/report
latexmk -pdf phase1_report.tex
```

## Timeline

| Dates | Stage |
|---|---|
| Nov 3–8 | Environment setup |
| Nov 6–18 | Configuration testing and expectation setup |
| Nov 16–28 | Router development |
| Nov 25–Dec 10 | Experiments and analysis |

## License

[MIT](LICENSE)
