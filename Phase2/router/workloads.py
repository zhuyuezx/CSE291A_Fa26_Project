"""Request classes for router experiments.

Text prompts are built exactly like Phase 1's and endpoint_test.py's (GSM8K
problem text, then a task), so their token counts match the single-node
profiles in results/: a 128-token target gives ~202 prompt tokens, and a
512-token target ~609. Images are Phase 1's bar charts.
"""

import base64
import json
import random
import uuid
from pathlib import Path

CHARS_PER_TOKEN = 4.0  # Phase 1's construction constant, kept so lengths match

CLASSES = {
    "T1": {"kind": "text", "prompt": 128, "output": 32,
           "about": "short chat: ~200-token prompt, 32 output tokens"},
    "T2": {"kind": "text", "prompt": 512, "output": 16,
           "about": "prefill-heavy: ~610-token prompt, 16 output tokens"},
    "T3": {"kind": "text", "prompt": 128, "output": 128,
           "about": "decode-heavy: ~200-token prompt, 128 output tokens"},
    # Images are out of scope for now (no endpoint loads a vision projector by
    # default); kept so the class can be turned back on with --mix.
    "M1": {"kind": "image", "px": 256, "output": 8,
           "about": "image: 256 px bar chart, short answer (needs VISION=1 endpoints)"},
}


def load_data(data_dir):
    d = Path(data_dir).expanduser()
    questions = [json.loads(line)["question"]
                 for line in (d / "gsm8k_test_n100_seed0.jsonl").read_text().splitlines() if line.strip()]
    images = {p.name: base64.b64encode(p.read_bytes()).decode()
              for p in (d / "images").glob("chart_*px_seed*.png")}
    return {"questions": questions, "images": images}


def length_prompt(questions, target_tokens, seed):
    qs = questions[:]
    random.Random(seed).shuffle(qs)
    header = f"[request {uuid.uuid4().hex[:8]}] Below are several word problems.\n\n"
    tail = "\nTask: Write a long, detailed, multi-paragraph story inspired by these problems."
    body, i = "", 0
    while len(header) + len(body) + len(tail) < target_tokens * CHARS_PER_TOKEN:
        body += f"Problem {i + 1}: {qs[i % len(qs)]}\n\n"
        i += 1
    return header + body + tail


def build_payload(cls, seed, data):
    """Chat request body for one request of class `cls`. Text classes generate
    exactly `output` tokens (ignore_eos); every request has a random nonce and
    cache_prompt=false, so no request reuses another's prefill."""
    c = CLASSES[cls]
    if c["kind"] == "text":
        content = length_prompt(data["questions"], c["prompt"], seed)
        ignore_eos = True
    else:
        b64 = data["images"][f"chart_{c['px']}px_seed{seed % 3}.png"]
        content = [
            {"type": "text", "text": f"[{uuid.uuid4().hex[:8]}] Which bar in this chart is "
                                     "the tallest? Reply with the letter only."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]
        ignore_eos = False
    return {"messages": [{"role": "user", "content": content}], "max_tokens": c["output"],
            "temperature": 0, "stream": True, "ignore_eos": ignore_eos, "cache_prompt": False,
            "chat_template_kwargs": {"enable_thinking": False}}
