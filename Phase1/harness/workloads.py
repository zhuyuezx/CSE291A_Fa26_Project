"""Workload builders: a fixed GSM8K sample, length-controlled text prompts,
and synthetic bar-chart images with a known answer."""

import base64
import io
import json
import random

import matplotlib
import requests

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from common import DATA_DIR, nonce  # noqa: E402

GSM8K_URL = ("https://raw.githubusercontent.com/openai/grade-school-math/"
             "master/grade_school_math/data/test.jsonl")
CHARS_PER_TOKEN = 4.0  # rough; the actual prompt token count is recorded


def load_gsm8k(n=100, seed=0):
    """A fixed random sample of the GSM8K test split, cached in data/."""
    path = DATA_DIR / f"gsm8k_test_n{n}_seed{seed}.jsonl"
    if not path.exists():
        lines = requests.get(GSM8K_URL, timeout=60).text.splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
        idx = sorted(random.Random(seed).sample(range(len(rows)), n))
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for i in idx:
                answer_text = rows[i]["answer"]
                f.write(json.dumps({
                    "id": f"gsm8k-test-{i}",
                    "question": rows[i]["question"],
                    "answer": answer_text.split("####")[-1].strip().replace(",", ""),
                    "answer_text": answer_text,
                }) + "\n")
    return [json.loads(line) for line in path.read_text().splitlines()]


def length_prompt(target_tokens, seed=0, task="story"):
    """A document prompt of roughly target_tokens tokens built from GSM8K
    problem text, followed by a task that sets the output shape."""
    questions = [r["question"] for r in load_gsm8k()]
    random.Random(seed).shuffle(questions)
    header = f"[request {nonce()}] Below are several word problems.\n\n"
    tail = {
        "story": "\nTask: Write a long, detailed, multi-paragraph story inspired by these problems.",
        "summary": "\nTask: In one sentence, say what the first problem is about.",
    }[task]
    body, i = "", 0
    while len(header) + len(body) + len(tail) < target_tokens * CHARS_PER_TOKEN:
        body += f"Problem {i + 1}: {questions[i % len(questions)]}\n\n"
        i += 1
    return header + body + tail


def chart_image(size_px, seed=0):
    """A bar chart with one clearly tallest bar. Returns (png_base64, label)
    and saves the PNG under data/images/ for reproducibility."""
    rng = random.Random(seed)
    labels = ["A", "B", "C", "D", "E"]
    values = rng.sample(range(2, 20), len(labels))
    answer = labels[values.index(max(values))]

    fig = plt.figure(figsize=(size_px / 100, size_px / 100), dpi=100)
    plt.bar(labels, values, color="#4C72B0")
    plt.title("Values by category")
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    png = buf.getvalue()

    out = DATA_DIR / "images" / f"chart_{size_px}px_seed{seed}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    return base64.b64encode(png).decode(), answer
