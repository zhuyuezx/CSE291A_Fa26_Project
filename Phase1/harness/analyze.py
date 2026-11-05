"""Turn raw JSONL logs into summary CSVs, figures, and results.md.

    python Phase1/harness/analyze.py
"""

import json

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from common import FIG_DIR, PHASE1, RAW_DIR, SUMMARY_DIR, read_jsonl  # noqa: E402


def load(name):
    df = pd.DataFrame(read_jsonl(RAW_DIR / f"{name}.jsonl"))
    return df


def size_b(s):
    """'27.3B' / '852.88M' -> billions, for ordering models by size."""
    s = str(s)
    return float(s[:-1]) / (1000 if s.endswith("M") else 1) if s[-1:] in "BM" else np.nan


def md_table(df, floatfmt=".2f"):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        cells = [(str(int(v)) if float(v).is_integer() else f"{v:{floatfmt}}")
                 if isinstance(v, (float, np.floating)) and not np.isnan(v) else str(v)
                 for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def errors_table(df, name):
    n_fail = int((~df.ok).sum()) if "ok" in df else 0
    return f"{name}: {len(df)} requests, {n_fail} failed or timed out."


def e1(sections):
    df = load("e1_profile")
    if df.empty:
        return
    df["size_b"] = df.parameter_size.map(size_b)
    ok = df[df.ok]

    cold = ok[ok.kind == "cold_start"].groupby(["model", "parameter_size", "quantization"]).agg(
        load_s=("load_s", "median"), cold_ttft_s=("ttft_s", "median"),
        resident_gb=("resident", lambda r: np.nanmedian([x["size_gb"] if x else np.nan for x in r])),
    ).reset_index()

    text = ok[ok.kind == "text"]
    prof = text.groupby(["model", "target_prompt_tokens", "target_output_tokens"]).agg(
        prompt_tokens=("prompt_tokens", "median"), ttft_s=("ttft_s", "median"),
        prefill_tps=("prefill_tps", "median"), decode_tps=("decode_tps", "median"),
        tpot_ms=("tpot_ms", "median"), e2e_s=("e2e_s", "median"),
        cpu_util=("cpu_util", "median"), runs=("ok", "size"),
    ).reset_index()
    prof.to_csv(SUMMARY_DIR / "e1_text_profile.csv", index=False)

    per_model = text.groupby("model").agg(
        params=("parameter_size", "first"), quant=("quantization", "first"),
        prefill_tps=("prefill_tps", "median"), decode_tps=("decode_tps", "median"),
        tpot_ms=("tpot_ms", "median"),
    ).reset_index().merge(cold[["model", "load_s", "resident_gb"]], on="model", how="left")
    per_model["size_b"] = per_model.params.map(size_b)
    per_model = per_model.sort_values("size_b").drop(columns="size_b")
    per_model.to_csv(SUMMARY_DIR / "e1_per_model.csv", index=False)

    img = ok[ok.kind == "image"]
    img_tab = pd.DataFrame()
    if not img.empty:
        img_tab = img.groupby(["model", "image_px"]).agg(
            prompt_tokens=("prompt_tokens", "median"), ttft_s=("ttft_s", "median"),
            prefill_s=("prefill_s", "median"), accuracy=("correct", "mean"),
            runs=("ok", "size"),
        ).reset_index()
        img_tab.to_csv(SUMMARY_DIR / "e1_image_profile.csv", index=False)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    order = per_model.model.tolist()
    for m in order:
        g = prof[prof.model == m].groupby("target_prompt_tokens").agg(
            x=("prompt_tokens", "median"), ttft=("ttft_s", "median"),
            pre=("prefill_tps", "median")).reset_index()
        axes[0].plot(g.x, g.ttft, marker="o", label=m)
        axes[1].plot(g.x, g.pre, marker="o", label=m)
    axes[0].set(xscale="log", yscale="log", xlabel="prompt tokens", ylabel="median TTFT (s)",
                title="TTFT vs prompt length (warm)")
    axes[1].set(xscale="log", xlabel="prompt tokens", ylabel="prefill tokens/s",
                title="Prefill throughput")
    axes[2].bar(per_model.model, per_model.decode_tps, color="#4C72B0")
    axes[2].set(ylabel="decode tokens/s", title="Decode throughput (median)")
    axes[2].tick_params(axis="x", rotation=30)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "e1_profiles.png", dpi=150)
    plt.close(fig)

    if not img_tab.empty:
        fig, ax = plt.subplots(figsize=(5, 3.5))
        for m, g in img_tab.groupby("model"):
            ax.plot(g.image_px, g.ttft_s, marker="o", label=m)
        ax.set(xlabel="image side (px)", ylabel="median TTFT (s)",
               title="Image request TTFT vs resolution")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(FIG_DIR / "e1_image_ttft.png", dpi=150)
        plt.close(fig)

    sections.append("## E1/E4: isolated profiles and cold start\n\n"
                    + errors_table(df, "E1") + "\n\nPer model (medians over all warm text runs; "
                    "load time and resident memory from cold starts):\n\n"
                    + md_table(per_model) + "\n\n![E1](figures/e1_profiles.png)\n")
    if not img_tab.empty:
        sections.append("Image requests (bar-chart question with a known answer):\n\n"
                        + md_table(img_tab) + "\n\n![E1 image](figures/e1_image_ttft.png)\n")


def e5(sections):
    df = load("e5_gsm8k")
    if df.empty:
        return
    ok = df[df.ok]
    acc = ok.groupby("model").agg(
        params=("parameter_size", "first"), quant=("quantization", "first"),
        accuracy=("correct", "mean"), mean_output_tokens=("output_tokens", "mean"),
        mean_e2e_s=("e2e_s", "mean"), p95_e2e_s=("e2e_s", lambda x: np.percentile(x, 95)),
        n=("correct", "size"),
    ).reset_index()
    acc["size_b"] = acc.params.map(size_b)
    acc = acc.sort_values("size_b")
    tiers = acc.model.tolist()
    acc = acc.drop(columns="size_b")
    acc.to_csv(SUMMARY_DIR / "e5_accuracy.csv", index=False)

    wide = ok.pivot_table(index="id", columns="model", values="correct", aggfunc="first")
    wide = wide[[t for t in tiers if t in wide]].dropna()
    labels = wide.apply(lambda r: next((t for t in tiers if r.get(t)), "none"), axis=1)
    label_counts = labels.value_counts().reindex(tiers + ["none"], fill_value=0)
    label_tab = pd.DataFrame({"smallest_correct_tier": label_counts.index,
                              "problems": label_counts.values})
    label_tab.to_csv(SUMMARY_DIR / "e5_tier_labels.csv", index=False)
    labels.rename("smallest_correct_tier").to_csv(SUMMARY_DIR / "e5_tier_label_per_problem.csv")

    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    ax.scatter(acc.mean_e2e_s, acc.accuracy)
    for _, r in acc.iterrows():
        ax.annotate(r.model, (r.mean_e2e_s, r.accuracy), fontsize=8,
                    xytext=(4, 4), textcoords="offset points")
    ax.set(xlabel="mean end-to-end latency (s)", ylabel="GSM8K accuracy",
           title="Quality vs latency per model tier")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "e5_quality_latency.png", dpi=150)
    plt.close(fig)

    sections.append("## E5: GSM8K tier labels\n\n" + errors_table(df, "E5") + "\n\n"
                    + md_table(acc) + "\n\nSmallest model tier that solves each problem "
                    f"(over {len(wide)} problems answered by every tier):\n\n"
                    + md_table(label_tab) + "\n\n![E5](figures/e5_quality_latency.png)\n")


def route(sections):
    files = [f for f in sorted(SUMMARY_DIR.glob("route_sim_*.csv"))
             if not f.name.startswith("route_sim_curve_")]
    for f in files:
        tab = pd.read_csv(f)
        pair = tab.pair.iloc[0]
        curve = pd.read_csv(f.with_name(f.name.replace("route_sim_", "route_sim_curve_")))
        fig, ax = plt.subplots(figsize=(5.5, 3.8))
        for prefix, style in (("R1", "-"), ("R2", "--")):
            c = curve[curve.policy.str.startswith(prefix)].sort_values("mean_latency_s")
            ax.plot(c.mean_latency_s, c.accuracy, style, label=f"{prefix} sweep")
        for _, r in tab[tab.policy.isin(["always-small", "always-large", "random", "oracle"])].iterrows():
            ax.scatter(r.mean_latency_s, r.accuracy)
            ax.annotate(r.policy, (r.mean_latency_s, r.accuracy), fontsize=8,
                        xytext=(4, -10), textcoords="offset points")
        ax.set(xlabel="mean end-to-end latency (s)", ylabel="accuracy", title=f"Routing: {pair}")
        ax.legend(fontsize=8)
        fig.tight_layout()
        png = f"route_sim_{f.stem.replace('route_sim_', '')}.png"
        fig.savefig(FIG_DIR / png, dpi=150)
        plt.close(fig)
        sections.append(f"## Offline routing simulation: {pair}\n\n"
                        + md_table(tab.drop(columns=["pair"]), ".3f")
                        + f"\n\n![routing](figures/{png})\n")


def e2(sections):
    df = load("e2_load")
    if df.empty:
        return
    df["arrival_to_first_token_s"] = df.ttft_s + (df.send_s - df.arrival_s)
    rows = []
    for (model, pattern, rate), g in df.groupby(["model", "pattern", "rate"]):
        ok = g[g.ok]
        span = (ok.t_end.max() - ok.t_start.min()) if len(ok) else np.nan
        # Largest number of requests decoding at the same moment: shows how
        # many requests the server really runs in parallel.
        events = sorted([(r.t_start + r.ttft_s, 1) for r in ok.itertuples() if r.ttft_s]
                        + [(r.t_end, -1) for r in ok.itertuples() if r.ttft_s])
        cur = peak = 0
        for _, d in events:
            cur += d
            peak = max(peak, cur)
        rows.append({
            "model": model, "pattern": pattern, "offered_rps": rate, "n": len(g),
            "failed": int((~g.ok).sum()), "achieved_rps": len(ok) / span if span else np.nan,
            "output_tps": ok.output_tokens.sum() / span if span else np.nan,
            "p50_ttft_s": ok.ttft_s.median(), "p95_ttft_s": ok.ttft_s.quantile(0.95),
            "p50_e2e_s": ok.e2e_s.median(), "p95_e2e_s": ok.e2e_s.quantile(0.95),
            "median_tpot_ms": ok.tpot_ms.median(), "peak_concurrent_decode": peak,
            "cpu_util": ok.cpu_util.median(),
        })
    tab = pd.DataFrame(rows)
    tab.to_csv(SUMMARY_DIR / "e2_load.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for (model, pattern), g in tab.groupby(["model", "pattern"]):
        axes[0].plot(g.offered_rps, g.p95_ttft_s, marker="o", label=f"{model} {pattern}")
        axes[1].plot(g.offered_rps, g.achieved_rps, marker="o", label=f"{model} {pattern}")
    axes[0].set(xlabel="offered load (req/s)", ylabel="p95 TTFT (s)", yscale="log",
                title="Tail TTFT vs offered load")
    axes[1].set(xlabel="offered load (req/s)", ylabel="achieved req/s", title="Throughput")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "e2_load.png", dpi=150)
    plt.close(fig)
    sections.append("## E2: load curves (open-loop arrivals)\n\n" + errors_table(df, "E2")
                    + "\n\n" + md_table(tab) + "\n\n![E2](figures/e2_load.png)\n")


def main():
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    sections = []
    host = {}
    meta = RAW_DIR / "e1_profile.meta.json"
    if meta.exists():
        host = json.loads(meta.read_text())[0]["host"]
    header = ("# Phase 1 results\n\nGenerated by `harness/analyze.py` from `results/raw/`. "
              f"Host: {host.get('chip')}, {host.get('mem_gb', 0):.0f} GB, "
              f"Ollama {host.get('ollama_version')}.\n")
    for step in (e1, e5, route, e2):
        step(sections)
    (PHASE1 / "results" / "results.md").write_text(header + "\n" + "\n".join(sections))
    print((PHASE1 / "results" / "results.md").read_text())


if __name__ == "__main__":
    main()
