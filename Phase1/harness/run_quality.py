"""E5 tier labels: run the same GSM8K sample on every model tier and record
correctness, output length, and latency per (model, problem).

The smallest model that answers a problem correctly is that problem's tier
label, which route_sim.py uses to evaluate content-based routers. Already
finished (model, problem) pairs are skipped, so the script can be resumed.

    python Phase1/harness/run_quality.py --models qwen3.5:0.8b qwen3.5:2b --n 100
"""

import argparse
import re

from common import RAW_DIR, append_jsonl, chat, read_jsonl, unload, write_meta
from sysmon import OllamaSampler
from workloads import load_gsm8k

PROMPT = ("Solve the following math problem. Reason briefly, then give the final "
          "answer on the last line in the form 'Answer: <number>'.\n\nProblem: {q}")


def parse_answer(text):
    found = re.findall(r"Answer:\s*\**\s*\$?\s*(-?[\d,]*\.?\d+)", text)
    if not found:
        found = re.findall(r"-?\d[\d,]*\.?\d*", text)
    if not found:
        return None
    value = found[-1].replace(",", "").rstrip(".")
    try:
        return float(value)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--out", default=str(RAW_DIR / "e5_gsm8k.jsonl"))
    args = ap.parse_args()

    problems = load_gsm8k(args.n, args.seed)
    done = {(r["model"], r["id"]) for r in read_jsonl(args.out)}
    write_meta(args.out, models=args.models, args=vars(args))
    sampler = OllamaSampler().start()

    for model in args.models:
        for prob in problems:
            if (model, prob["id"]) in done:
                continue
            rec = chat(model, PROMPT.format(q=prob["question"]), num_predict=args.max_tokens)
            pred = parse_answer(rec["text"])
            gold = float(prob["answer"])
            rec.update(sampler.window(rec["t_start"], rec["t_end"]))
            rec.update({"kind": "gsm8k", "id": prob["id"], "pred": pred, "gold": gold,
                        "correct": pred is not None and abs(pred - gold) < 1e-6,
                        "question_words": len(prob["question"].split())})
            append_jsonl(args.out, rec)
            print(f"{model:<18} {prob['id']:<16} correct={rec['correct']} "
                  f"out={rec['output_tokens']} e2e={rec['e2e_s']:.1f}s", flush=True)
        unload(model)

    sampler.stop()


if __name__ == "__main__":
    main()
