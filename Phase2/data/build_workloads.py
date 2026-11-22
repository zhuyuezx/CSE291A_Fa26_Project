#!/usr/bin/env python3
"""Build the Phase 2 request pool: real prompts from cleaned or verified public
datasets, grouped into request classes with different shapes (prompt length,
expected output length) and an automatic scorer where one exists.

Rows come from the Hugging Face dataset viewer API (or raw files for BFCL),
are filtered, measured with Qwen3.5's tokenizer, and written to
workloads/pool.jsonl plus a quality report, workloads/stats.md. Each item is
assigned to a fixed 'train' or 'test' half by a hash of its id, so a learned
router can be trained on one half and evaluated on the other. The class mixes
are in workloads/mixes.json; pool.py samples traces from them.

    pip install tokenizers
    curl -L -o qwen_tokenizer.json https://huggingface.co/Qwen/Qwen3.5-2B/resolve/main/tokenizer.json
    python3 Phase2/data/build_workloads.py --tokenizer qwen_tokenizer.json

Prompts longer than --max-prompt tokens are dropped: the endpoints share a
16K context across 4 slots, and a 4K prompt already takes 30-70 s to prefill
on the CPU nodes.
"""

import argparse
import hashlib
import json
import random
import statistics
import time
import urllib.parse
import urllib.request
from pathlib import Path

from tokenizers import Tokenizer

HERE = Path(__file__).resolve().parent
OUT = HERE / "workloads"
ROWS_API = "https://datasets-server.huggingface.co/rows"
BFCL = "https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard/resolve/main/"

# Request classes, weights per mix. dev is used to build and tune routers; the
# others shift the class balance and are held out for evaluation.
MIXES = {
    "dev-balanced": {"chat": .25, "multiturn": .05, "math": .12, "rag_short": .06, "rag_multihop": .08,
                     "rag_long": .06, "summ": .08, "code": .10, "instruct": .10, "knowledge": .05,
                     "tool": .05},
    "real-chat": {"chat": .55, "multiturn": .15, "code": .10, "instruct": .10, "math": .05, "summ": .05},
    "rag-enterprise": {"rag_short": .15, "rag_multihop": .20, "rag_long": .20, "summ": .20, "chat": .15,
                       "tool": .10},
    "reasoning": {"math": .35, "code": .30, "instruct": .15, "knowledge": .10, "chat": .10},
    "agent-tools": {"tool": .45, "rag_multihop": .20, "rag_short": .15, "chat": .20},
}


# ---------------------------------------------------------------- fetching

CACHE = None  # directory for fetched pages (--cache), so re-runs do not hit the API again


def get_json(url, tries=8):
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ".json") if CACHE else None
    if path and path.exists():
        return json.loads(path.read_text())
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as f:
                data = json.load(f)
            if path:
                path.write_text(json.dumps(data))
            time.sleep(1.0)
            return data
        except Exception as e:  # rate limits and transient errors: back off and retry
            if k == tries - 1:
                raise
            wait = min(300, 5 * 2 ** k)
            print(f"  retry {k + 1} in {wait} s after {type(e).__name__}: {e}", flush=True)
            time.sleep(wait)


def get_lines(url):
    with urllib.request.urlopen(url, timeout=120) as f:
        return [json.loads(line) for line in f.read().decode().splitlines() if line.strip()]


def rows(dataset, config, split, offsets=None, length=100):
    """Rows from the dataset viewer API: all rows, or 100-row pages at the given offsets.
    Rows with truncated cells are skipped."""
    q = {"dataset": dataset, "config": config, "split": split}
    first = get_json(f"{ROWS_API}?{urllib.parse.urlencode({**q, 'offset': 0, 'length': length})}")
    total = first["num_rows_total"]
    if offsets is None:
        offsets = range(0, total, length)
    out = []
    for off in offsets:
        page = first if off == 0 else get_json(
            f"{ROWS_API}?{urllib.parse.urlencode({**q, 'offset': off, 'length': length})}")
        out += [r["row"] for r in page["rows"] if not r.get("truncated_cells")]
    return out, total


# ---------------------------------------------------------------- items

def item(source, cls, local_id, messages, max_tokens, scorer, reference, **meta):
    iid = f"{source}:{local_id}"
    half = "train" if int(hashlib.sha256(iid.encode()).hexdigest(), 16) % 2 == 0 else "test"
    return {"id": iid, "cls": cls, "source": source, "split": half, "messages": messages,
            "max_tokens": max_tokens, "scorer": scorer, "reference": reference, "meta": meta}


def user(text):
    return [{"role": "user", "content": text}]


def build_chat_and_multiturn(rng, n_chat, n_multi, tok, max_prompt, report):
    """WildChat-1M (ODC-BY): real user prompts. Only conversation text is kept:
    no IPs, locations, or headers. Near-duplicates (same first 100 characters)
    are kept once, and at most 2 prompts share their first 5 words, so one
    user's repeated template cannot dominate. Turns that are mostly non-ASCII
    are dropped, since the language label covers the whole conversation."""
    total = rows("allenai/WildChat-1M", "default", "train", offsets=[0])[1]
    offsets = sorted(rng.sample(range(0, total - 100), 60))
    got, _ = rows("allenai/WildChat-1M", "default", "train", offsets=offsets)
    seen, opening, chat, multi = set(), {}, [], []
    drops = {"not English": 0, "duplicate template": 0, "too short/long": 0}
    for r in got:
        if r["language"] != "English" or r["toxic"] or r["redacted"]:
            drops["not English"] += 1
            continue
        turns = [m["content"].strip() for m in r["conversation"] if m["role"] == "user"]
        if not turns or not turns[0] or any(sum(ord(ch) > 127 for ch in t) > 0.2 * len(t) for t in turns):
            drops["not English"] += 1
            continue
        key = " ".join(turns[0].lower().split())[:100]
        first5 = " ".join(turns[0].lower().split()[:5])
        if key in seen or opening.get(first5, 0) >= 2:
            drops["duplicate template"] += 1
            continue
        seen.add(key)
        opening[first5] = opening.get(first5, 0) + 1
        lens = [len(tok.encode(t).ids) for t in turns]
        if lens[0] < 3 or lens[0] > max_prompt:
            drops["too short/long"] += 1
            continue
        meta = {"conversation_hash": r["conversation_hash"], "orig_model": r["model"], "turns": len(turns)}
        if 2 <= len(turns) <= 4 and max(lens) <= 1500 and sum(lens) <= max_prompt:
            multi.append(item("allenai/WildChat-1M", "multiturn", r["conversation_hash"], None, 512,
                              "none", None, user_turns=turns, **meta))
        else:
            chat.append(item("allenai/WildChat-1M", "chat", r["conversation_hash"], user(turns[0]), 1024,
                             "none", None, **meta))
    report["allenai/WildChat-1M"] = {"rows read": len(got), **drops,
                                     "kept chat": min(n_chat, len(chat)), "kept multiturn": min(n_multi, len(multi))}
    rng.shuffle(chat)
    rng.shuffle(multi)
    return chat[:n_chat], multi[:n_multi]


def build_mt_bench(report):
    got, _ = rows("HuggingFaceH4/mt_bench_prompts", "default", "train")
    report["HuggingFaceH4/mt_bench_prompts"] = {"rows read": len(got), "kept": len(got)}
    return [item("mt_bench", "multiturn", r["prompt_id"], None, 512, "none", r["reference"] or None,
                 user_turns=r["prompt"], category=r["category"]) for r in got]


def build_math(rng, n, report):
    out = []
    got, _ = rows("madrylab/gsm8k-platinum", "main", "test")
    ok = [r for r in got if r["cleaning_status"] != "rejected"]
    for i, r in enumerate(rng.sample(ok, min(n, len(ok)))):
        q = r["question"] + "\nSolve the problem step by step. End with the final answer on its own line as '#### <number>'."
        out.append(item("madrylab/gsm8k-platinum", "math", hashlib.md5(r["question"].encode()).hexdigest()[:12],
                        user(q), 512, "gsm8k_number", r["answer"].split("####")[-1].strip()))
    report["madrylab/gsm8k-platinum"] = {"rows read": len(got), "kept after cleaning": len(ok), "sampled": min(n, len(ok))}
    got, _ = rows("HuggingFaceH4/MATH-500", "default", "test")
    for r in rng.sample(got, min(n, len(got))):
        q = r["problem"] + "\nSolve the problem step by step and put the final answer in \\boxed{}."
        out.append(item("HuggingFaceH4/MATH-500", "math", r["unique_id"], user(q), 1024, "math_boxed",
                        r["answer"], subject=r["subject"], level=r["level"]))
    report["HuggingFaceH4/MATH-500"] = {"rows read": len(got), "sampled": min(n, len(got))}
    return out


def build_platinum_qa(config, cls, report):
    """Platinum-bench (cleaned labels): drop items the cleaners rejected."""
    got, _ = rows("madrylab/platinum-bench", config, "test")
    ok = [r for r in got if r["cleaning_status"] != "rejected"]
    report[f"madrylab/platinum-bench/{config}"] = {"rows read": len(got), "kept after cleaning": len(ok)}
    return [item(f"platinum-bench/{config}", cls, r["id"], user(r["platinum_prompt_no_cot"]), 64, "qa_em_f1",
                 r["platinum_target"] or r["original_target"], cleaning_status=r["cleaning_status"])
            for r in ok]


def build_musique(rng, n, tok, max_prompt, report):
    got, total = rows("dgslibisey/MuSiQue", "default", "validation")
    cands, too_long = [], 0
    for r in got:
        if not r["answerable"]:
            continue
        paras = "\n\n".join(f"Paragraph {p['idx'] + 1}: {p['title']}\n{p['paragraph_text']}" for p in r["paragraphs"])
        text = ("Answer the question using the information in the paragraphs. Reply with the answer only.\n\n"
                f"{paras}\n\nQuestion: {r['question']}")
        if len(tok.encode(text).ids) > max_prompt:
            too_long += 1
            continue
        cands.append(item("dgslibisey/MuSiQue", "rag_long", r["id"], user(text), 64, "qa_em_f1",
                          [r["answer"]] + r["answer_aliases"], hops=r["id"].split("__")[0]))
    report["dgslibisey/MuSiQue"] = {"rows read": len(got), "answerable, fits": len(cands),
                                    "too long": too_long, "sampled": min(n, len(cands))}
    return rng.sample(cands, min(n, len(cands)))


def build_cnn(rng, n, tok, report):
    total = rows("abisee/cnn_dailymail", "3.0.0", "test", offsets=[0])[1]
    got, _ = rows("abisee/cnn_dailymail", "3.0.0", "test", offsets=sorted(rng.sample(range(0, total - 100), 6)))
    cands = []
    for r in got:
        text = "Summarize the following news article in 3 to 4 sentences.\n\n" + r["article"]
        if len(tok.encode(text).ids) <= 2000:
            cands.append(item("abisee/cnn_dailymail", "summ", r["id"], user(text), 256, "rouge_l", r["highlights"]))
    report["abisee/cnn_dailymail"] = {"rows read": len(got), "<= 2000 tokens": len(cands), "sampled": min(n, len(cands))}
    return rng.sample(cands, min(n, len(cands)))


def build_code(report):
    out = []
    got, _ = rows("google-research-datasets/mbpp", "sanitized", "test")
    for r in got:
        tests = "\n".join(r["test_list"])
        q = (f"{r['prompt']}\nYour code should pass these tests:\n{tests}\n"
             "Reply with only the Python code in one code block.")
        out.append(item("mbpp-sanitized", "code", r["task_id"], user(q), 512, "mbpp_tests",
                        {"test_list": r["test_list"], "test_imports": r["test_imports"]}))
    report["google-research-datasets/mbpp (sanitized)"] = {"rows read": len(got), "kept": len(got)}
    got, _ = rows("openai/openai_humaneval", "openai_humaneval", "test")
    for r in got:
        q = ("Complete the following Python function. Reply with the whole function in one code block.\n\n"
             + r["prompt"])
        out.append(item("openai/openai_humaneval", "code", r["task_id"], user(q), 512, "humaneval_tests",
                        {"test": r["test"], "entry_point": r["entry_point"]}))
    report["openai/openai_humaneval"] = {"rows read": len(got), "kept": len(got)}
    return out


def build_ifeval(rng, n, report):
    got, _ = rows("google/IFEval", "default", "train")
    report["google/IFEval"] = {"rows read": len(got), "sampled": min(n, len(got))}
    return [item("google/IFEval", "instruct", r["key"], user(r["prompt"]), 1024, "ifeval",
                 {"instruction_id_list": r["instruction_id_list"],
                  "kwargs": [{k: v for k, v in kw.items() if v is not None} for kw in r["kwargs"]]})
            for r in rng.sample(got, min(n, len(got)))]


def build_mmlu_redux(rng, per_subject, report):
    """MMLU-Redux 2.0: MMLU re-annotated by hand; keep only questions marked 'ok'."""
    subjects = sorted({s["config"] for s in get_json(
        "https://datasets-server.huggingface.co/splits?dataset=edinburgh-dawg/mmlu-redux-2.0")["splits"]})
    out, n_read, n_ok = [], 0, 0
    for s in subjects:
        got, _ = rows("edinburgh-dawg/mmlu-redux-2.0", s, "test")
        ok = [r for r in got if r["error_type"] == "ok"]
        n_read, n_ok = n_read + len(got), n_ok + len(ok)
        for r in rng.sample(ok, min(per_subject, len(ok))):
            opts = "\n".join(f"{'ABCD'[i]}. {c}" for i, c in enumerate(r["choices"]))
            q = f"{r['question']}\n\n{opts}\n\nAnswer with the letter of the correct option only."
            out.append(item("mmlu-redux-2.0", "knowledge", f"{s}:{hashlib.md5(r['question'].encode()).hexdigest()[:10]}",
                            user(q), 8, "mc_letter", "ABCD"[r["answer"]], subject=s))
    report["edinburgh-dawg/mmlu-redux-2.0"] = {"rows read": n_read, "marked ok": n_ok, "sampled": len(out)}
    return out


def build_bfcl(rng, n, report):
    qs = get_lines(BFCL + "BFCL_v3_simple.json")
    ans = {a["id"]: a["ground_truth"] for a in get_lines(BFCL + "possible_answer/BFCL_v3_simple.json")}
    out = []
    for r in rng.sample(qs, min(n, len(qs))):
        request = " ".join(m["content"] for turn in r["question"] for m in turn if m["role"] == "user")
        q = ("You have access to the following functions:\n" + json.dumps(r["function"], indent=1) +
             '\n\nTo call a function, reply with only a JSON object: {"name": <function name>, '
             '"arguments": {<argument name>: <value>}}.\n\nRequest: ' + request)
        out.append(item("gorilla-llm/BFCL_v3_simple", "tool", r["id"], user(q), 256, "bfcl_ast", ans[r["id"]]))
    report["gorilla-llm/BFCL_v3_simple"] = {"rows read": len(qs), "sampled": len(out)}
    return out


# ---------------------------------------------------------------- report

def prompt_tokens(it, tok):
    if it["messages"]:
        return [len(tok.encode(it["messages"][0]["content"]).ids)]
    return [len(tok.encode(t).ids) for t in it["meta"]["user_turns"]]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q / 100 * len(xs)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", required=True, help="Qwen3.5 tokenizer.json")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-prompt", type=int, default=3500)
    ap.add_argument("--cache", help="directory to cache fetched pages in")
    args = ap.parse_args()
    global CACHE
    if args.cache:
        CACHE = Path(args.cache)
        CACHE.mkdir(parents=True, exist_ok=True)
    tok = Tokenizer.from_file(args.tokenizer)
    rng = lambda name: random.Random(f"{args.seed}:{name}")  # one stream per source
    report = {}

    items = []
    chat, multi = build_chat_and_multiturn(random.Random(args.seed), 400, 120, tok, args.max_prompt, report)
    items += chat + multi + build_mt_bench(report)
    items += build_math(rng("math"), 200, report)
    items += build_platinum_qa("squad", "rag_short", report)
    items += build_platinum_qa("hotpotqa", "rag_multihop", report)
    items += build_musique(rng("musique"), 200, tok, args.max_prompt, report)
    items += build_cnn(rng("cnn"), 200, tok, report)
    items += build_code(report)
    items += build_ifeval(rng("ifeval"), 300, report)
    items += build_mmlu_redux(rng("mmlu"), 6, report)
    items += build_bfcl(rng("bfcl"), 300, report)

    kept, ids = [], set()
    for it in items:
        if it["id"] in ids:  # WildChat repeats some identical conversations
            continue
        ids.add(it["id"])
        lens = prompt_tokens(it, tok)
        if max(lens) > args.max_prompt:
            continue
        it["prompt_tokens"] = lens[0] if len(lens) == 1 else lens
        kept.append(it)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "pool.jsonl", "w") as f:
        for it in kept:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    (OUT / "mixes.json").write_text(json.dumps(MIXES, indent=2) + "\n")

    lines = ["# Request pool: quality report", "",
             f"Built by `build_workloads.py --seed {args.seed} --max-prompt {args.max_prompt}`. "
             "Prompt tokens are counted with Qwen3.5's tokenizer on the user message (the chat template adds about 10). "
             "Multi-turn rows count the first user turn.", "",
             "## Per class", "",
             "| class | items | train / test | sources | prompt tokens p10 / p50 / p90 / max | max_tokens | scorer |",
             "|---|---|---|---|---|---|---|"]
    for cls in sorted({it["cls"] for it in kept}):
        g = [it for it in kept if it["cls"] == cls]
        p = [it["prompt_tokens"] if isinstance(it["prompt_tokens"], int) else it["prompt_tokens"][0] for it in g]
        tr = sum(it["split"] == "train" for it in g)
        lines.append(f"| {cls} | {len(g)} | {tr} / {len(g) - tr} | {', '.join(sorted({it['source'] for it in g}))} | "
                     f"{pct(p, 10)} / {statistics.median(p):.0f} / {pct(p, 90)} / {max(p)} | "
                     f"{', '.join(str(x) for x in sorted({it['max_tokens'] for it in g}))} | "
                     f"{', '.join(sorted({it['scorer'] for it in g}))} |")
    lines += ["", "## Filtering per source", "", "| source | counts |", "|---|---|"]
    for src, d in report.items():
        lines.append(f"| {src} | {', '.join(f'{k}: {v}' for k, v in d.items())} |")
    (OUT / "stats.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {len(kept)} items to {OUT / 'pool.jsonl'}")


if __name__ == "__main__":
    main()
