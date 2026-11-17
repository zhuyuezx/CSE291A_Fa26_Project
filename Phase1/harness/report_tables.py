"""Write the LaTeX tables for the report's results appendix (Appendix B) from
results/summary/, so the numbers in the PDF always match the data.

    python Phase1/harness/report_tables.py
"""

import re

import pandas as pd

from common import PHASE1, SUMMARY_DIR

OUT = PHASE1 / "report" / "tables"
EXCLUDED = "qwen3-vl:4b"  # ignores think=false in Ollama 0.40.14; marked with a dagger


def model(m):
    return rf"\texttt{{{m}}}" + (r"$^\dagger$" if m == EXCLUDED else "")


def params(s):
    """'852.88M' -> '0.85B', '36.0B' -> '36B'."""
    v = float(s[:-1]) / (1000 if s.endswith("M") else 1)
    out = f"{v:.2g}"
    return (out + ".0" if "." not in out and v < 10 else out) + "B"


def quant(q):
    return "MXFP8" if q.lower() == "mxfp8" else q.replace("_", r"\_")


def pct(x):
    return f"{100 * x:.0f}"


def write(name, colspec, header, rows):
    lines = [rf"\begin{{tabular}}{{{colspec}}}", r"\toprule", *header, r"\midrule"]
    lines += [r if r.startswith((r"\midrule", r"\cmidrule")) else r + r" \\" for r in rows]
    lines += [r"\bottomrule", r"\end{tabular}"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("\n".join(lines) + "\n")


def e1_models():
    df = pd.read_csv(SUMMARY_DIR / "e1_per_model.csv")
    rows = [f"{model(r.model)} & {params(r.params)} & {quant(r.quant)} & {r.prefill_tps:,.0f} & "
            f"{r.decode_tps:.0f} & {r.tpot_ms:.1f} & {r.load_s:.2f} & {r.resident_gb:.1f}"
            for r in df.itertuples()]
    write("e1_models.tex", "@{}lllrrrrr@{}",
          [r"Model & Params & Quant. & Prefill (tok/s) & Decode (tok/s) & TPOT (ms) "
           r"& Cold load (s) & Resident (GB) \\"], rows)


def e1_image():
    df = pd.read_csv(SUMMARY_DIR / "e1_image_profile.csv")
    cols = ["qwen3.5:0.8b", "qwen3.5:2b", "qwen3.5:35b"]
    ttft = df.pivot(index="image_px", columns="model", values="ttft_s")
    tokens = df[df.model == cols[0]].set_index("image_px").prompt_tokens
    rows = [f"{px:.0f} & {tokens[px]:.0f} & " + " & ".join(f"{ttft.loc[px, c]:.2f}" for c in cols)
            for px in ttft.index]
    write("e1_image.tex", "@{}rrrrr@{}",
          [r"Image side & Prompt & \multicolumn{3}{c}{TTFT (s)} \\",
           r"\cmidrule(l){3-5}",
           r"(px) & tokens & 0.8B & 2B & 35B-A3B \\"], rows)


def e5():
    acc = pd.read_csv(SUMMARY_DIR / "e5_accuracy.csv")
    labels = pd.read_csv(SUMMARY_DIR / "e5_tier_labels.csv").set_index("smallest_correct_tier").problems
    rows = [f"{model(r.model)} & {params(r.params)} & {pct(r.accuracy)} & {r.mean_output_tokens:.0f} & "
            f"{r.mean_e2e_s:.2f} & {r.p95_e2e_s:.2f} & {labels.get(r.model, 0)}"
            for r in acc.itertuples()]
    rows += [r"\midrule", rf"\multicolumn{{6}}{{@{{}}l}}{{No model correct}} & {labels.get('none', 0)}"]
    write("e5.tex", "@{}llrrrrr@{}",
          [r"Model & Params & Accuracy & Output & \multicolumn{2}{c}{Latency (s)} & Smallest \\",
           r"\cmidrule(lr){5-6}",
           r"& & (\%) & tokens & mean & p95 & correct for \\"], rows)


def policy_label(p):
    fixed = {"always-small": "Always the small model", "always-large": "Always 35B-A3B",
             "random": "Random (50/50)", "oracle": "Oracle (small when it is correct)"}
    if p in fixed:
        return fixed[p]
    if m := re.match(r"R1-length \(>(\d+) words", p):
        return rf"R1 length rule: 35B-A3B if $>${m[1]} words"
    if m := re.match(r"R2-logreg \(tau=([\d.]+)\)", p):
        return rf"R2 TF-IDF + logistic regression, $\tau={m[1]}$"
    return p


def routing():
    pairs = ["qwen3.5-0.8b", "qwen3.5-2b"]
    tabs = [pd.read_csv(SUMMARY_DIR / f"route_sim_{p}__qwen3.5-35b.csv").set_index("policy")
            for p in pairs]
    rows = []
    for policy in tabs[0].index:
        if policy == "R2-logreg (tau=0.9)":  # routes everything to 35B-A3B in both pairs
            continue
        cells = [policy_label(policy)]
        for t in tabs:
            r = t.loc[policy]
            cells += [pct(r.accuracy), f"{r.mean_latency_s:.2f}", pct(r.large_fraction)]
        rows.append(" & ".join(cells))
    write("routing.tex", "@{}lrrrrrr@{}",
          [r" & \multicolumn{3}{c}{0.8B $\rightarrow$ 35B-A3B} & \multicolumn{3}{c}{2B $\rightarrow$ 35B-A3B} \\",
           r"\cmidrule(lr){2-4}\cmidrule(l){5-7}",
           r"Policy & Acc.\ (\%) & Latency (s) & To 35B (\%) & Acc.\ (\%) & Latency (s) & To 35B (\%) \\"],
          rows)


def main():
    for make in (e1_models, e1_image, e5, routing):
        make()
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.tex"))))


if __name__ == "__main__":
    main()
