"""E2 load curves: open-loop arrivals at several offered rates against one model.

Requests are drawn from a mix of classes (T1 short chat, T2 long prompt,
T3 long output) and sent at precomputed arrival times, so queueing delay shows
up in TTFT instead of being hidden by a closed loop. `poisson` uses
exponential inter-arrival times; `bursty` uses gamma inter-arrival times with
the same mean and coefficient of variation `--cv` (as in vLLM's benchmark).

    python Phase1/harness/run_load.py --model qwen3.5:2b --rates 0.25 0.5 1 --n 40
"""

import argparse
import random
import time
from concurrent.futures import ThreadPoolExecutor

from common import RAW_DIR, append_jsonl, chat, nonce, unload, write_meta
from sysmon import OllamaSampler
from workloads import length_prompt, load_gsm8k

CLASSES = {
    # name: (prompt builder, num_predict)
    "T1": (lambda rng, qs: f"[{nonce()}] {rng.choice(qs)}", 64),
    "T2": (lambda rng, qs: length_prompt(2048, seed=rng.randrange(10**6), task="summary"), 32),
    "T3": (lambda rng, qs: f"[{nonce()}] Write a long, detailed story about a city on Mars.", 256),
}


def arrivals(n, rate, pattern, cv, rng):
    t, out = 0.0, []
    for _ in range(n):
        if pattern == "poisson":
            t += rng.expovariate(rate)
        else:
            shape = 1.0 / cv ** 2
            t += rng.gammavariate(shape, 1.0 / (rate * shape))
        out.append(t)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--rates", nargs="+", type=float, default=[0.25, 0.5, 1.0])
    ap.add_argument("--patterns", nargs="+", default=["poisson", "bursty"])
    ap.add_argument("--cv", type=float, default=3.0)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--mix", nargs=3, type=float, default=[0.5, 0.25, 0.25],
                    metavar=("T1", "T2", "T3"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(RAW_DIR / "e2_load.jsonl"))
    args = ap.parse_args()

    questions = [r["question"] for r in load_gsm8k()]
    write_meta(args.out, models=[args.model], args=vars(args))
    sampler = OllamaSampler().start()
    chat(args.model, f"[{nonce()}] Reply with OK.", num_predict=1)  # warm up

    for pattern in args.patterns:
        for rate in args.rates:
            rng = random.Random(args.seed)
            times = arrivals(args.n, rate, pattern, args.cv, rng)
            reqs = []
            for t in times:
                cls = rng.choices(list(CLASSES), weights=args.mix)[0]
                build, num_predict = CLASSES[cls]
                reqs.append((t, cls, build(rng, questions), num_predict))

            t0 = time.time()

            def send(req):
                t_arrival, cls, prompt, num_predict = req
                time.sleep(max(0.0, t0 + t_arrival - time.time()))
                rec = chat(args.model, prompt, num_predict=num_predict)
                rec.update({"kind": "load", "pattern": pattern, "rate": rate,
                            "cls": cls, "arrival_s": t_arrival,
                            "send_s": rec["t_start"] - t0})
                rec.update(sampler.window(rec["t_start"], rec["t_end"]))
                rec["text"] = rec["text"][:200]
                return rec

            with ThreadPoolExecutor(max_workers=args.n) as pool:
                for rec in pool.map(send, reqs):
                    append_jsonl(args.out, rec)
            print(f"{pattern} rate={rate}: done in {time.time() - t0:.0f}s", flush=True)

    unload(args.model)
    sampler.stop()


if __name__ == "__main__":
    main()
