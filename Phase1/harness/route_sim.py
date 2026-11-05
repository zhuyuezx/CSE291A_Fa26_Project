"""Offline evaluation of content-based routing on the E5 measurements.

Every GSM8K problem was answered by every model (run_quality.py), so any
routing policy between a small and a large model can be scored exactly:
accuracy is the chosen model's correctness, and latency is the chosen model's
measured end-to-end latency on this machine (no queueing).

Policies:
  always-small / always-large      single-model baselines
  random                           50/50 coin flip (5 seeds averaged)
  R1-length (threshold t)          large model if the question has > t words
  R2-logreg (threshold tau)        TF-IDF + logistic regression predicts
                                   P(small model is correct); small if >= tau.
                                   Probabilities are out-of-fold (5-fold CV).
  oracle                           small whenever the small model is correct

    python Phase1/harness/route_sim.py --small qwen3.5:2b --large qwen3.5:35b
"""

import argparse

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from common import RAW_DIR, SUMMARY_DIR, read_jsonl
from workloads import load_gsm8k


def outcome(name, use_large, df):
    acc = np.where(use_large, df.correct_large, df.correct_small).mean()
    lat = np.where(use_large, df.e2e_large, df.e2e_small)
    return {"policy": name, "accuracy": acc, "mean_latency_s": lat.mean(),
            "p95_latency_s": np.percentile(lat, 95), "large_fraction": np.mean(use_large)}


def r2_probabilities(df, seed=0):
    """Out-of-fold P(small model correct) from question text."""
    y = df.correct_small.astype(int).values
    p = np.full(len(df), y.mean())
    if y.min() == y.max():
        return p
    folds = StratifiedKFold(n_splits=min(5, np.bincount(y).min()), shuffle=True,
                            random_state=seed)
    for train, test in folds.split(df.question, y):
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        clf = LogisticRegression(max_iter=1000, C=1.0)
        clf.fit(vec.fit_transform(df.question.iloc[train]), y[train])
        p[test] = clf.predict_proba(vec.transform(df.question.iloc[test]))[:, 1]
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--small", required=True)
    ap.add_argument("--large", required=True)
    ap.add_argument("--inp", default=str(RAW_DIR / "e5_gsm8k.jsonl"))
    args = ap.parse_args()

    recs = pd.DataFrame(read_jsonl(args.inp))
    recs = recs[recs.ok]
    questions = {p["id"]: p["question"] for p in load_gsm8k()}
    small = recs[recs.model == args.small].set_index("id")
    large = recs[recs.model == args.large].set_index("id")
    ids = small.index.intersection(large.index)
    df = pd.DataFrame({
        "question": [questions[i] for i in ids],
        "words": [len(questions[i].split()) for i in ids],
        "correct_small": small.loc[ids, "correct"].values,
        "correct_large": large.loc[ids, "correct"].values,
        "e2e_small": small.loc[ids, "e2e_s"].values,
        "e2e_large": large.loc[ids, "e2e_s"].values,
    })

    rows = [outcome("always-small", np.zeros(len(df), bool), df),
            outcome("always-large", np.ones(len(df), bool), df)]
    rand = [outcome("random", np.random.default_rng(s).random(len(df)) < 0.5, df)
            for s in range(5)]
    rows.append({k: (np.mean([r[k] for r in rand]) if k != "policy" else "random")
                 for k in rand[0]})
    for q in (25, 50, 75):
        t = np.percentile(df.words, q)
        rows.append(outcome(f"R1-length (>{t:.0f} words, p{q})", df.words.values > t, df))
    p = r2_probabilities(df)
    for tau in (0.5, 0.7, 0.9):
        rows.append(outcome(f"R2-logreg (tau={tau})", p < tau, df))
    rows.append(outcome("oracle", ~df.correct_small.values, df))

    out = pd.DataFrame(rows)
    out.insert(0, "pair", f"{args.small} -> {args.large}")
    out["n"] = len(df)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{args.small}__{args.large}".replace(":", "-")
    out.to_csv(SUMMARY_DIR / f"route_sim_{tag}.csv", index=False)

    curve = [outcome(f"R2 tau={tau:.2f}", p < tau, df) for tau in np.linspace(0, 1, 41)]
    curve += [outcome(f"R1 t={t}", df.words.values > t, df) for t in sorted(df.words.unique())]
    pd.DataFrame(curve).to_csv(SUMMARY_DIR / f"route_sim_curve_{tag}.csv", index=False)
    print(out.to_string(index=False, float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
