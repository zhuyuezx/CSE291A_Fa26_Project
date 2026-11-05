"""Compare config-only (theoretical) estimates with the E1/E4 measurements.

For each measured model it reports theory vs. measurement for prefill
throughput, decode throughput, resident memory, and cold-start load time,
and the efficiency ratio (measured / theoretical throughput, or theoretical /
measured time). It then tests whether config + one device calibration is
enough for a *new* model: leave one model out, calibrate the efficiency on the
others (median ratio), and predict the held-out model from its config.
Finally it predicts the configured-but-unmeasured models.

    python Phase1/harness/compare_theory.py
"""

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from common import FIG_DIR, PHASE1, RAW_DIR, SUMMARY_DIR, read_jsonl  # noqa: E402
from theory import estimate, load_configs  # noqa: E402

# metric: (measured column, theoretical column, higher is better)
METRICS = {
    "prefill_tps": ("prefill_tps", True),
    "decode_tps": ("decode_tps", True),
    "memory_gb": ("memory_gb", False),
    "load_s": ("load_s", False),
}


def measured_points(models):
    """One row per (model, prompt length) with measured and theoretical values."""
    df = pd.DataFrame(read_jsonl(RAW_DIR / "e1_profile.jsonl"))
    df = df[df.ok & df.model.isin(models)]
    cold = df[df.kind == "cold_start"].groupby("model").agg(
        load_s=("load_s", "median"),
        memory_gb=("resident", lambda r: np.nanmedian([x["size_gb"] for x in r if x])))
    text = df[df.kind == "text"]
    rows = []
    for (model, target), g in text.groupby(["model", "target_prompt_tokens"]):
        long_out = g[g.target_output_tokens == g.target_output_tokens.max()]
        rows.append({
            "model": model, "target_prompt_tokens": target,
            "prompt_tokens": g.prompt_tokens.median(),
            "output_tokens": long_out.output_tokens.median(),
            "prefill_tps": g.prefill_tps.median(),
            "decode_tps": long_out.decode_tps.median(),
            "memory_gb": cold.loc[model, "memory_gb"],
            "load_s": cold.loc[model, "load_s"],
        })
    return pd.DataFrame(rows)


def main():
    models, hw = load_configs()
    measured = [m for m, c in models.items() if c["measured"]]
    pts = measured_points(measured)
    for i, r in pts.iterrows():
        est = estimate(models[r.model], hw, int(r.prompt_tokens), int(r.output_tokens))
        for metric in METRICS:
            pts.loc[i, f"theory_{metric}"] = est[metric]
        pts.loc[i, "decode_bound"] = est["decode_bound"]
        pts.loc[i, "prefill_bound"] = est["prefill_bound"]

    # Efficiency: < 1 means reality is slower (or bigger) than the bound.
    for metric, (_, higher_better) in METRICS.items():
        ratio = pts[metric] / pts[f"theory_{metric}"]
        pts[f"eff_{metric}"] = ratio if higher_better else 1 / ratio

    # Leave-one-model-out calibration.
    for metric in METRICS:
        per_model = pts.groupby("model")[f"eff_{metric}"].median()
        for m in measured:
            eta = per_model.drop(m).median()
            mask = pts.model == m
            th = pts.loc[mask, f"theory_{metric}"]
            pts.loc[mask, f"loo_{metric}"] = th * eta if METRICS[metric][1] else th / eta
    for metric in METRICS:
        pts[f"err_theory_{metric}"] = (pts[f"theory_{metric}"] - pts[metric]).abs() / pts[metric]
        pts[f"err_loo_{metric}"] = (pts[f"loo_{metric}"] - pts[metric]).abs() / pts[metric]

    # Decode with a fixed per-token overhead: TPOT = a * theoretical TPOT + b,
    # fitted on the other models (leave-one-out).
    tpot_th, tpot = 1000 / pts.theory_decode_tps, 1000 / pts.decode_tps
    for m in measured:
        train = pts.model != m
        a, b = np.polyfit(tpot_th[train], tpot[train], 1)
        pts.loc[~train, "loo_affine_decode_tps"] = 1000 / (a * tpot_th[~train] + b)
    pts["err_loo_affine_decode_tps"] = ((pts.loo_affine_decode_tps - pts.decode_tps).abs()
                                        / pts.decode_tps)

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    pts.to_csv(SUMMARY_DIR / "theory_vs_measured.csv", index=False)

    per_model = pts.groupby("model").agg(
        **{f"eff_{m}": (f"eff_{m}", "median") for m in METRICS},
        **{f"loo_err_{m}": (f"err_loo_{m}", "median") for m in METRICS},
    ).reindex(measured).reset_index()
    per_model.to_csv(SUMMARY_DIR / "theory_per_model.csv", index=False)
    overall = pd.DataFrame([{
        "metric": m,
        "efficiency_median": per_model[f"eff_{m}"].median(),
        "efficiency_range": f"{per_model[f'eff_{m}'].min():.2f}-{per_model[f'eff_{m}'].max():.2f}",
        "theory_only_error": pts[f"err_theory_{m}"].median(),
        "calibrated_loo_error": pts[f"err_loo_{m}"].median(),
        "calibrated_loo_error_max": pts[f"err_loo_{m}"].max(),
    } for m in METRICS] + [{
        "metric": "decode_tps (slope + per-token overhead)",
        "efficiency_median": np.nan, "efficiency_range": "",
        "theory_only_error": pts.err_theory_decode_tps.median(),
        "calibrated_loo_error": pts.err_loo_affine_decode_tps.median(),
        "calibrated_loo_error_max": pts.err_loo_affine_decode_tps.max(),
    }])
    overall.to_csv(SUMMARY_DIR / "theory_overall.csv", index=False)

    # Predictions for configured models that were never run, using the
    # efficiencies calibrated on all measured models.
    eta = {m: per_model[f"eff_{m}"].median() for m in METRICS}
    preds = []
    for name, cfg in models.items():
        if cfg["measured"]:
            continue
        est = estimate(cfg, hw, 512, 256)
        preds.append({"model": name, "prompt_tokens": 512, "output_tokens": 256,
                      **{f"pred_{m}": est[m] * eta[m] if METRICS[m][1] else est[m] / eta[m]
                         for m in METRICS}})
    pd.DataFrame(preds).to_csv(SUMMARY_DIR / "theory_predictions_unmeasured.csv", index=False)

    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    for ax, metric in zip(axes, METRICS):
        for col, marker, label in ((f"theory_{metric}", "x", "theory only"),
                                   (f"loo_{metric}", "o", "calibrated (leave-one-out)")):
            ax.scatter(pts[metric], pts[col], marker=marker, label=label)
        lo = min(pts[metric].min(), pts[[f"theory_{metric}", f"loo_{metric}"]].min().min())
        hi = max(pts[metric].max(), pts[[f"theory_{metric}", f"loo_{metric}"]].max().max())
        ax.plot([lo, hi], [lo, hi], "k--", lw=1)
        ax.set(xscale="log", yscale="log", xlabel=f"measured {metric}",
               ylabel=f"predicted {metric}", title=metric)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "theory_vs_measured.png", dpi=150)
    plt.close(fig)

    from analyze import md_table
    text = ("# Config-only estimates vs. measurement\n\n"
            "Generated by `harness/compare_theory.py`. Theory: roofline from "
            "`configs/models.json` and `configs/hardware.json` (see `harness/theory.py`). "
            "Efficiency = measured / theoretical throughput (or theoretical / measured for "
            "memory and load time). *Leave-one-out*: calibrate the efficiency on the other "
            "models and predict this one from its config.\n\n"
            "## Summary\n\n" + md_table(overall) + "\n\n"
            "## Per model\n\n" + md_table(per_model) + "\n\n"
            "![theory vs measured](figures/theory_vs_measured.png)\n\n"
            "## Predictions for unmeasured models (prompt 512, output 256)\n\n"
            + md_table(pd.DataFrame(preds)) + "\n")
    (PHASE1 / "results" / "theory.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
