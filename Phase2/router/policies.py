"""Routing policies. Each sees only what a real router sees: the request's
features (prompt tokens, image size, task class, max_tokens), what it has
dispatched, and when each request finished with how many output tokens.

  always-<node>   every request to one node
  round-robin     nodes in turn
  JSQ             fewest outstanding requests (the simple load-aware baseline)
  best-idle       node with the lowest idle-node latency for this request's
                  shape (profile only, ignores load)
  SED             shortest expected delay: (outstanding + 1) x idle latency
  ECT             expected completion time: replay each node's queue in the
                  fluid model (nodemodel.Node) with the new request added and
                  pick the earliest finish
  ECT-global      like ECT, but minimizes the total completion time added to
                  all requests on the node, so it counts the delay a long prompt
                  causes to sequences already decoding there
  ECT-oracle      ECT with the true output length and the true node state
                  (an upper bound on what better prediction could buy)

The output length is unknown at routing time. ECT, SED, and best-idle predict it
per task class with an EWMA of finished requests, starting from max_tokens / 2.
"""

import itertools
import random

from nodemodel import Job, Node


class OutputPredictor:
    def __init__(self, alpha=0.1):
        self.alpha, self.mean = alpha, {}

    def predict(self, req):
        return self.mean.get(req["cls"], req["max_tokens"] / 2)

    def observe(self, req, out_tokens):
        m = self.mean.get(req["cls"])
        self.mean[req["cls"]] = out_tokens if m is None else m + self.alpha * (out_tokens - m)


class Policy:
    name = "base"

    def __init__(self, profiles):
        self.names = list(profiles)
        self.profiles = profiles
        self.models = {n: Node(n, profiles[n]) for n in self.names}  # cost functions only
        self.outstanding = {n: 0 for n in self.names}
        self.pred = OutputPredictor()

    def route(self, req, t):
        raise NotImplementedError

    def on_dispatch(self, req, node, t):
        self.outstanding[node] += 1

    def on_complete(self, req, node, t, out_tokens):
        self.outstanding[node] -= 1
        self.pred.observe(req, out_tokens)

    def idle_latency(self, node, req):
        return self.models[node].service_s(req["prompt"], req["px"], self.pred.predict(req))


class Always(Policy):
    def __init__(self, profiles, node):
        super().__init__(profiles)
        self.node, self.name = node, f"always-{node}"

    def route(self, req, t):
        return self.node


class RoundRobin(Policy):
    name = "round-robin"

    def __init__(self, profiles):
        super().__init__(profiles)
        self.cycle = itertools.cycle(self.names)

    def route(self, req, t):
        return next(self.cycle)


class Random(Policy):
    name = "random"

    def __init__(self, profiles, seed=0):
        super().__init__(profiles)
        self.rng = random.Random(seed)

    def route(self, req, t):
        return self.rng.choice(self.names)


class JSQ(Policy):
    name = "JSQ"

    def __init__(self, profiles):
        super().__init__(profiles)
        self.turn = 0

    def route(self, req, t):
        low = min(self.outstanding.values())
        tied = [n for n in self.names if self.outstanding[n] == low]
        self.turn += 1
        return tied[self.turn % len(tied)]


class BestIdle(Policy):
    name = "best-idle"

    def route(self, req, t):
        return min(self.names, key=lambda n: self.idle_latency(n, req))


class SED(Policy):
    name = "SED"

    def route(self, req, t):
        return min(self.names, key=lambda n: (self.outstanding[n] + 1) * self.idle_latency(n, req))


class ECT(Policy):
    """Keeps a shadow fluid model of each node, fed with predicted output
    lengths and corrected whenever a real request finishes."""
    name = "ECT"
    global_cost = False

    def __init__(self, profiles):
        super().__init__(profiles)
        self.shadow = {n: Node(n, profiles[n], sticky_extend=0.25) for n in self.names}

    def state(self, node, t):
        s = self.shadow[node]
        s.advance(t)
        sim = s.copy()
        sim.sticky_extend = None
        return sim

    def new_job(self, req):
        return Job("__new__", req["prompt"], req["px"], self.pred.predict(req))

    def score(self, node, req, t):
        sim = self.state(node, t)
        if not self.global_cost:
            sim.submit(self.new_job(req), t)
            return sim.run_until_done("__new__")
        base = sim.copy()
        before = sum(base.drain().values())
        sim.submit(self.new_job(req), t)
        return sum(sim.drain().values()) - before

    def route(self, req, t):
        return min(self.names, key=lambda n: self.score(n, req, t))

    def on_dispatch(self, req, node, t):
        super().on_dispatch(req, node, t)
        self.shadow[node].submit(Job(req["rid"], req["prompt"], req["px"],
                                     self.pred.predict(req)), t)

    def on_complete(self, req, node, t, out_tokens):
        super().on_complete(req, node, t, out_tokens)
        self.shadow[node].advance(t)
        self.shadow[node].remove(req["rid"])


class ECTGlobal(ECT):
    name = "ECT-global"
    global_cost = True


class ECTOracle(ECT):
    """Sees the real nodes and the true output length (simulation only)."""
    name = "ECT-oracle"

    def __init__(self, profiles, real_nodes):
        super().__init__(profiles)
        self.real = real_nodes

    def state(self, node, t):
        sim = self.real[node].copy()
        sim.advance(t)
        return sim

    def new_job(self, req):
        return Job("__new__", req["prompt"], req["px"], req["out"])


POLICIES = ["round-robin", "random", "JSQ", "best-idle", "SED", "ECT", "ECT-global", "ECT-oracle"]


def build(name, profiles, real_nodes, seed=0):
    """A fresh policy by name; 'always-<node>' for the single-node baselines."""
    if name.startswith("always-"):
        return Always(profiles, name[len("always-"):])
    cls = {"round-robin": RoundRobin, "JSQ": JSQ, "best-idle": BestIdle, "SED": SED,
           "ECT": ECT, "ECT-global": ECTGlobal}
    if name == "random":
        return Random(profiles, seed)
    if name == "ECT-oracle":
        return ECTOracle(profiles, real_nodes)
    return cls[name](profiles)
