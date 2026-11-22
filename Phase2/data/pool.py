"""Load the request pool (workloads/pool.jsonl) and draw class-mix samples from it.

    from pool import load_pool, load_mixes, sample_mix
    items = sample_mix(load_pool(), load_mixes()["dev-balanced"], n=200, seed=0, split="test")

Each item has `messages` (single request) or `meta.user_turns` (a multi-turn
session, replayed turn by turn with the model's own replies), plus
`max_tokens`, `scorer`, and `reference`. Within a class, items are drawn
without replacement until the class runs out, then the class is reshuffled.
"""

import json
import random
from pathlib import Path

WORKLOADS = Path(__file__).resolve().parent / "workloads"


def load_pool(path=WORKLOADS / "pool.jsonl"):
    return [json.loads(line) for line in Path(path).open()]


def load_mixes(path=WORKLOADS / "mixes.json"):
    return json.loads(Path(path).read_text())


def sample_mix(pool, mix, n, seed=0, split=None):
    """n items whose classes follow the mix weights. split='train' or 'test'
    restricts to that half of the pool."""
    rng = random.Random(seed)
    by_cls = {}
    for it in pool:
        if split is None or it["split"] == split:
            by_cls.setdefault(it["cls"], []).append(it)
    missing = [c for c in mix if c not in by_cls]
    if missing:
        raise ValueError(f"no items for classes {missing}")
    decks = {c: [] for c in mix}
    out = []
    for c in rng.choices(list(mix), weights=list(mix.values()), k=n):
        if not decks[c]:
            decks[c] = by_cls[c][:]
            rng.shuffle(decks[c])
        out.append(decks[c].pop())
    return out
