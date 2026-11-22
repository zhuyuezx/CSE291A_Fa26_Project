"""Routing service: an OpenAI-compatible proxy in front of the llama-server endpoints.

Each POST /v1/chat/completions is forwarded, streaming or not, to the node a
policy from policies.py picks (round-robin, JSQ, SED, ECT-global, ...). The
policy sees what a deployed router sees:

  prompt      estimated prompt tokens: characters / 4 + 15 template tokens
              (the same estimate live.py and the simulator use)
  cls         the task class, from the X-Task-Class header ("default" if absent).
              The output-length predictor learns one running mean per class.
  max_tokens  the X-Max-Tokens header if present, else the body's max_tokens.
              Load generators that force an exact output length with
              ignore_eos use the header to declare the cap a real client would send.

When a request finishes, the router reads its real output token count from the
server's final chunk and reports it to the policy (on_complete), which updates
the predictor and, for ECT, the shadow queue model. Text only: requests with
images are rejected (the fleet serves no vision projector).

    /opt/fleet/venv/bin/python router.py --policy ECT-global --log router.jsonl
    /opt/fleet/venv/bin/python router.py --endpoints C1 C2 --policy JSQ --log router.jsonl

HTTP API:
  POST /v1/chat/completions   routed request (same body as llama-server)
  GET  /health                router liveness and current policy
  GET  /stats                 per-node outstanding / completed / errors, predictor state
  POST /admin/policy          {"policy": "SED"}: switch policy (only while nothing is in flight)
Response headers: X-Routed-To, X-Router-Policy, X-Router-Decision-Us.
A client may send X-Request-Id; it is copied into the log. Listens on
127.0.0.1 by default: clients run on the router host.
"""

import argparse
import json
import time
from pathlib import Path

import aiohttp
from aiohttp import web

from nodemodel import load_profiles
from policies import ECT, POLICIES, build

HERE = Path(__file__).resolve().parent
CHARS_PER_TOKEN = 4.0
TEMPLATE_TOKENS = 15
DEFAULT_MAX_TOKENS = 256  # predictor prior when a request sets no max_tokens
LIVE_POLICIES = [p for p in POLICIES if p != "ECT-oracle"] + ["first-idle", "always-<node>"]


def request_view(payload, headers, rid):
    """What the policy is allowed to see about a request."""
    chars, images = 0, 0
    for m in payload.get("messages", []):
        content = m.get("content")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if part.get("type") == "text":
                    chars += len(part.get("text", ""))
                elif part.get("type") == "image_url":
                    images += 1
    max_tokens = headers.get("X-Max-Tokens") or payload.get("max_tokens") or payload.get("n_predict")
    max_tokens = int(max_tokens) if max_tokens and int(max_tokens) > 0 else DEFAULT_MAX_TOKENS
    view = {"rid": rid, "cls": headers.get("X-Task-Class", "default"), "px": 0,
            "max_tokens": max_tokens, "prompt": int(chars / CHARS_PER_TOKEN) + TEMPLATE_TOKENS}
    return view, images


class OutputCounter:
    """Finds the real output token count in a llama-server reply as it streams
    past: `timings.predicted_n` in the final SSE chunk, or `usage` in a
    non-streaming body."""

    def __init__(self):
        self.buf, self.tokens, self.body = b"", None, b""

    def feed(self, chunk, streaming):
        if not streaming:
            self.body += chunk
            return
        self.buf += chunk
        *lines, self.buf = self.buf.split(b"\n")
        for line in lines:
            self._line(line)

    def _line(self, line):
        line = line.strip()
        if not line.startswith(b"data:") or line[5:].strip() == b"[DONE]":
            return
        try:
            obj = json.loads(line[5:])
        except ValueError:
            return
        self._take(obj)

    def _take(self, obj):
        n = (obj.get("timings") or {}).get("predicted_n") or (obj.get("usage") or {}).get("completion_tokens")
        if n is not None:
            self.tokens = int(n)

    def finish(self, streaming):
        if streaming:
            self._line(self.buf)
        elif self.body:
            try:
                self._take(json.loads(self.body))
            except ValueError:
                pass
        return self.tokens


def now(app):
    return time.monotonic() - app["t0"]


async def handle_chat(request):
    app = request.app
    body = await request.read()
    try:
        payload = json.loads(body)
    except ValueError:
        return web.json_response({"error": "request body is not valid JSON"}, status=400)
    app["rid"] += 1
    view, images = request_view(payload, request.headers, app["rid"])
    if images:
        return web.json_response({"error": "image input is not served by this fleet (text only)"},
                                 status=400)
    pol = app["policy"]
    streaming = bool(payload.get("stream"))

    t = now(app)
    snapshot = dict(pol.outstanding)
    c0 = time.perf_counter()
    node = pol.route(view, t)
    decision_us = (time.perf_counter() - c0) * 1e6
    pol.on_dispatch(view, node, t)
    # A plain-ECT shadow sees the same dispatches under every policy, so the
    # cost model's predicted latency is logged for every request (as in live.py).
    obs = app["obs"]
    pred_done = obs.score(node, view, t)
    obs.on_dispatch(view, node, t)

    rec = {"id": request.headers.get("X-Request-Id"), "rid": view["rid"], "policy": pol.name,
           "node": node, "cls": view["cls"], "prompt_est": view["prompt"],
           "max_tokens_view": view["max_tokens"], "pred_out": pol.pred.predict(view),
           "pred_e2e_s": pred_done - t,
           "outstanding_at_decision": snapshot, "decision_us": decision_us,
           "t_arrival": time.time()}
    counter, resp, out_tokens = OutputCounter(), None, None
    try:
        rec["t_up_send"] = time.time()
        async with app["session"].post(f"{app['urls'][node]}/v1/chat/completions", data=body,
                                       headers={"Content-Type": "application/json"}) as up:
            resp = web.StreamResponse(status=up.status, headers={
                "Content-Type": up.headers.get("Content-Type", "application/json"),
                "X-Routed-To": node, "X-Router-Policy": pol.name,
                "X-Router-Decision-Us": f"{decision_us:.1f}"})
            await resp.prepare(request)
            n_bytes = 0
            async for chunk in up.content.iter_any():
                if n_bytes == 0:
                    rec["t_up_first_byte"] = time.time()
                n_bytes += len(chunk)
                counter.feed(chunk, streaming)
                await resp.write(chunk)
            await resp.write_eof()
            out_tokens = counter.finish(streaming)
            rec.update(status=up.status, bytes=n_bytes)
            if up.status != 200:
                rec["error"] = f"HTTP {up.status}"
    except Exception as e:  # recorded, never dropped
        rec["error"] = f"{type(e).__name__}: {e}"
        if resp is None:
            resp = web.json_response({"error": rec["error"], "node": node}, status=502)
    finally:
        # A failed request still leaves the node's queue; report the predicted
        # length so the output predictor is not pulled toward zero.
        failed = "error" in rec or out_tokens is None
        t_end = now(app)
        pol.on_complete(view, node, t_end, pol.pred.predict(view) if failed else out_tokens)
        obs.on_complete(view, node, t_end, obs.pred.predict(view) if failed else out_tokens)
        stats = app["stats"][node]
        stats["completed"] += 1
        stats["errors"] += int("error" in rec)
        rec.update(out_tokens=out_tokens, t_done=time.time())
        app["log"].write(json.dumps(rec) + "\n")
        app["log"].flush()
    return resp


async def handle_health(request):
    return web.json_response({"status": "ok", "policy": request.app["policy"].name})


async def handle_stats(request):
    app = request.app
    pol = app["policy"]
    return web.json_response({
        "policy": pol.name,
        "nodes": {n: {"url": app["urls"][n], "outstanding": pol.outstanding[n], **app["stats"][n]}
                  for n in app["urls"]},
        "predicted_output_tokens_by_class": pol.pred.mean,
    })


def make_policy(app, name):
    if name == "ECT-oracle":
        raise ValueError("ECT-oracle needs the true node state; it exists only in simulate.py")
    if name.startswith("always-") and name[len("always-"):] not in app["urls"]:
        raise ValueError(f"{name}: unknown node; nodes are {list(app['urls'])}")
    try:
        return build(name, app["profiles"], None, app["seed"])
    except KeyError:
        raise ValueError(f"unknown policy {name!r}; choose from {LIVE_POLICIES}") from None


async def handle_policy(request):
    app = request.app
    if any(app["policy"].outstanding.values()):
        return web.json_response({"error": "requests in flight; switch policy when idle"}, status=409)
    name = (await request.json()).get("policy", "")
    try:
        app["policy"] = make_policy(app, name)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    app["obs"] = ECT(app["profiles"])
    app["t0"] = time.monotonic()  # fresh clock and predictor for the new policy
    return web.json_response({"policy": app["policy"].name})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="/opt/fleet/endpoints.json",
                    help="fleet endpoint list (deploy/endpoints.json)")
    ap.add_argument("--profiles", default=str(HERE / "profiles.json"))
    ap.add_argument("--endpoints", nargs="+", help="node names (default: every node with a profile)")
    ap.add_argument("--policy", default="JSQ", help=f"one of {LIVE_POLICIES}")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--log", required=True, help="JSONL file, one line per routed request")
    args = ap.parse_args()

    eps = {e["name"]: f"http://{e['private_ip']}:{e['port']}"
           for e in json.loads(Path(args.config).read_text())["endpoints"]}
    profiles = load_profiles(args.profiles)
    names = args.endpoints or [n for n in eps if n in profiles]
    missing = [n for n in names if n not in eps or n not in profiles]
    if missing:
        raise SystemExit(f"no endpoint or no profile for {missing}; run fit_profiles.py first")

    app = web.Application(client_max_size=64 * 2**20)
    app["urls"] = {n: eps[n] for n in names}
    app["profiles"] = {n: profiles[n] for n in names}
    app["seed"] = args.seed
    app["rid"] = 0
    app["t0"] = time.monotonic()
    app["stats"] = {n: {"completed": 0, "errors": 0} for n in names}
    try:
        app["policy"] = make_policy(app, args.policy)
    except ValueError as e:
        raise SystemExit(str(e))
    app["obs"] = ECT(app["profiles"])
    app["log"] = open(args.log, "a")

    async def on_startup(app):
        app["session"] = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=1800),
            connector=aiohttp.TCPConnector(limit=0))

    async def on_cleanup(app):
        await app["session"].close()
        app["log"].close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_post("/v1/chat/completions", handle_chat)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/stats", handle_stats)
    app.router.add_post("/admin/policy", handle_policy)
    print(f"router: policy={app['policy'].name} nodes="
          f"{', '.join(f'{n}={u}' for n, u in app['urls'].items())} on {args.host}:{args.port}", flush=True)
    web.run_app(app, host=args.host, port=args.port, access_log=None, print=None)


if __name__ == "__main__":
    main()
