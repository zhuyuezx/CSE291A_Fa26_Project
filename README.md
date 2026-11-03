# CSE 291A Fall 2026 Project: Adaptive Routing Across Heterogeneous Machines

Option 3. We route text and image requests for [Qwen3.5](https://huggingface.co/collections/Qwen/qwen35) models across AWS CPU instances and Apple-Silicon laptops, served with [llama.cpp](https://github.com/ggml-org/llama.cpp).

**Phase 1 report:** [`Phase1/report/phase1_report.pdf`](Phase1/report/phase1_report.pdf)

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
Phase1/
  req.txt                  # course requirements
  report/
    phase1_report.tex      # Phase 1 report source
    phase1_report.pdf      # Phase 1 report
```

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
