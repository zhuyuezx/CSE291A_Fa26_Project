"""Fluid model of one llama-server endpoint, built from a fitted profile.

Used twice: as the ground-truth node in the simulator, and inside the ECT
router to predict when a request would finish on each node.

What the model encodes (each item checked against results/<NODE>/server.jsonl):
  - `slots` sequences run at once; later requests wait FIFO for a slot.
  - An image is encoded alone, blocking the node (llama.cpp encodes inside the
    batch loop).
  - Prompts being prefilled share the CPU equally: four 600-token prompts sent
    together all get their first token at the same time, after the sum of their
    single-request prefill times.
  - While any prompt is being prefilled, decoding sequences stall: a decode
    token rides in a batch that is mostly prompt tokens, so it waits for it.
  - Otherwise every decoding sequence advances one token per step, and the step
    grows with the number of decoding sequences (batch_factor) and context.
"""

import json
from pathlib import Path

PROFILES = Path(__file__).resolve().parent / "profiles.json"
EPS = 1e-9


def load_profiles(path=PROFILES):
    return json.loads(Path(path).read_text())


class Job:
    __slots__ = ("rid", "prompt", "px", "out", "stage", "rem", "done_tokens",
                 "t_admit", "t_first", "t_done")

    def __init__(self, rid, prompt, px, out):
        self.rid, self.prompt, self.px, self.out = rid, prompt, px, out
        self.stage = None          # "vision", "prefill", "decode"
        self.rem = 0.0             # seconds of work (vision/prefill) or tokens (decode)
        self.done_tokens = 0.0
        self.t_admit = self.t_first = self.t_done = None

    def copy(self):
        j = Job(self.rid, self.prompt, self.px, self.out)
        j.stage, j.rem, j.done_tokens = self.stage, self.rem, self.done_tokens
        j.t_admit, j.t_first, j.t_done = self.t_admit, self.t_first, self.t_done
        return j


class Node:
    def __init__(self, name, profile, sticky_extend=None):
        self.name, self.p = name, profile
        self.slots = profile["slots"]
        bf = profile["decode"]["batch_factor"]
        self.batch_factor = {int(k): v for k, v in bf.items()}
        self.t = 0.0
        self.queue = []            # waiting for a slot, FIFO
        self.active = []           # in a slot, admission order
        self.finished = []         # jobs completed since the caller last drained them
        # Router-side shadow copies set this: when a predicted output runs out
        # but the real request has not finished, keep decoding a bit longer.
        self.sticky_extend = sticky_extend

    # ---------------------------------------------------------------- costs
    def prefill_s(self, prompt):
        pf = self.p["prefill"]
        return pf["c0"] + pf["a"] * prompt + pf["b"] * prompt * prompt

    def vision_s(self, px):
        return self.p["vision"][str(px)]["seconds"]

    def step_s(self, n_decode, ctx):
        d = self.p["decode"]
        return (d["s0"] + d["g"] * ctx) * self.batch_factor[min(n_decode, self.slots)]

    def service_s(self, prompt, px, out):
        """Latency of one request on an idle node."""
        first = self.vision_s(px) if px else self.prefill_s(prompt)
        return first + out * self.step_s(1, prompt + out / 2)

    # ---------------------------------------------------------------- state
    def outstanding(self):
        return len(self.queue) + len(self.active)

    def submit(self, job, t):
        self.advance(t)
        self.queue.append(job)
        self._admit()

    def remove(self, rid):
        """Drop a job (router shadow: the real request finished)."""
        for lst in (self.active, self.queue):
            for j in lst:
                if j.rid == rid:
                    lst.remove(j)
                    self._admit()
                    return True
        return False

    def copy(self):
        n = Node.__new__(Node)
        n.name, n.p, n.slots, n.batch_factor = self.name, self.p, self.slots, self.batch_factor
        n.t, n.sticky_extend = self.t, self.sticky_extend
        n.queue = [j.copy() for j in self.queue]
        n.active = [j.copy() for j in self.active]
        n.finished = []
        return n

    def _admit(self):
        while self.queue and len(self.active) < self.slots:
            j = self.queue.pop(0)
            j.t_admit = self.t
            if j.px:
                j.stage, j.rem = "vision", self.vision_s(j.px)
            else:
                j.stage, j.rem = "prefill", self.prefill_s(j.prompt)
            self.active.append(j)

    # ---------------------------------------------------------------- dynamics
    def _mode(self):
        """Which work runs now, the jobs progressing, and the seconds until the
        next stage change if nothing new arrives."""
        vis = [j for j in self.active if j.stage == "vision"]
        if vis:
            return "vision", vis[:1], vis[0].rem
        pre = [j for j in self.active if j.stage == "prefill"]
        if pre:
            k = len(pre)
            return "prefill", pre, min(j.rem for j in pre) * k
        dec = [j for j in self.active if j.stage == "decode"]
        if dec:
            ctx = sum(j.prompt + j.done_tokens for j in dec) / len(dec)
            step = self.step_s(len(dec), ctx)
            return "decode", dec, min(j.rem for j in dec) * step
        return None, [], None

    def _progress(self, mode, jobs, dt):
        if mode == "vision":
            jobs[0].rem -= dt
        elif mode == "prefill":
            for j in jobs:
                j.rem -= dt / len(jobs)
        elif mode == "decode":
            ctx = sum(j.prompt + j.done_tokens for j in jobs) / len(jobs)
            tokens = dt / self.step_s(len(jobs), ctx)
            for j in jobs:
                j.rem -= tokens
                j.done_tokens += tokens

    def _transitions(self):
        changed = True
        while changed:
            changed = False
            for j in list(self.active):
                if j.rem > EPS:
                    continue
                if j.stage == "vision":
                    # The image's text part is a few tokens; its prefill is folded into vision_s.
                    j.stage, j.rem = "prefill", 0.0
                    changed = True
                elif j.stage == "prefill":
                    j.t_first = self.t
                    j.stage, j.rem = "decode", float(j.out)
                    changed = True
                elif j.stage == "decode":
                    if self.sticky_extend:
                        j.rem = max(16.0, self.sticky_extend * j.out)
                        j.out = j.out + j.rem
                        continue
                    j.t_done = self.t
                    self.active.remove(j)
                    self.finished.append(j)
                    changed = True
            self._admit()

    def advance(self, t_end):
        """Run the node forward to time t_end."""
        while True:
            self._transitions()
            mode, jobs, dt = self._mode()
            if mode is None:
                self.t = max(self.t, t_end)
                return
            if self.t + dt >= t_end - EPS:
                self._progress(mode, jobs, t_end - self.t)
                self.t = t_end
                self._transitions()
                return
            self._progress(mode, jobs, dt)
            self.t += dt

    def run_until_done(self, rid, limit=1e7):
        """Advance until job rid finishes; return its completion time."""
        while True:
            for j in self.finished:
                if j.rid == rid:
                    return j.t_done
            self._transitions()
            mode, jobs, dt = self._mode()
            if mode is None or self.t > limit:
                return float("inf")
            self._progress(mode, jobs, dt)
            self.t += dt
            self._transitions()

    def drain(self):
        """Run until every job finishes; return {rid: completion time}."""
        while True:
            self._transitions()
            mode, jobs, dt = self._mode()
            if mode is None:
                return {j.rid: j.t_done for j in self.finished}
            self._progress(mode, jobs, dt)
            self.t += dt
