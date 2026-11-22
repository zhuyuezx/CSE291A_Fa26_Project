"""Routing service: an OpenAI-compatible proxy in front of the llama-server endpoints.

Each POST /v1/chat/completions is forwarded, streaming or not, to the
endpoint the routing policy picks. The router counts requests in flight per
endpoint (its view of each queue) and logs one JSON line per request.

    /opt/fleet/venv/bin/python router.py --endpoints C1 C2 --policy least_outstanding \
        --log router.jsonl

HTTP API:
  POST /v1/chat/completions   routed request (same body as llama-server)
  GET  /health                router liveness
  GET  /stats                 policy and per-endpoint in-flight / completed / error counts
  POST /admin/policy          {"policy": "round_robin"}: switch policy without restarting
Response headers: X-Routed-To, X-Router-Policy, X-Router-Decision-Us.
A client may send X-Request-Id; it is copied into the log so router and client
records can be joined. Listens on 127.0.0.1 by default: clients run on the router host.
"""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import aiohttp
from aiohttp import web

from policies import POLICY_NAMES, Endpoint, RequestInfo, make_policy

# Characters per token for GSM8K-style English text in Qwen3.5's tokenizer:
# 512 characters measured as ~202 tokens on every node.
CHARS_PER_TOKEN_EST = 2.5


def request_info(payload):
    chars = images = 0
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
    max_tokens = payload.get("max_tokens") or payload.get("n_predict") or -1
    return RequestInfo(prompt_chars=chars, est_prompt_tokens=int(chars / CHARS_PER_TOKEN_EST),
                       max_tokens=max_tokens, n_images=images, stream=bool(payload.get("stream")))


async def handle_chat(request):
    app = request.app
    body = await request.read()
    try:
        payload = json.loads(body)
    except ValueError:
        return web.json_response({"error": "request body is not valid JSON"}, status=400)
    info = request_info(payload)
    eps = app["endpoints"]
    policy = app["policy"]

    t_arrival = time.time()
    snapshot = {e.name: e.in_flight for e in eps}
    t0 = time.perf_counter()
    ep = policy.choose(info, eps)
    decision_us = (time.perf_counter() - t0) * 1e6
    rec = {"id": request.headers.get("X-Request-Id"), "t_arrival": t_arrival,
           "policy": policy.name, "endpoint": ep.name, "in_flight_at_decision": snapshot,
           "decision_us": decision_us, **asdict(info)}

    ep.in_flight += 1
    resp = None
    try:
        rec["t_up_send"] = time.time()
        async with app["session"].post(f"{ep.url}/v1/chat/completions", data=body,
                                       headers={"Content-Type": "application/json"}) as up:
            resp = web.StreamResponse(status=up.status, headers={
                "Content-Type": up.headers.get("Content-Type", "application/json"),
                "X-Routed-To": ep.name,
                "X-Router-Policy": policy.name,
                "X-Router-Decision-Us": f"{decision_us:.1f}",
            })
            await resp.prepare(request)
            n_bytes = 0
            async for chunk in up.content.iter_any():
                if n_bytes == 0:
                    rec["t_up_first_byte"] = time.time()
                n_bytes += len(chunk)
                await resp.write(chunk)
            await resp.write_eof()
            rec.update(status=up.status, bytes=n_bytes)
    except Exception as e:  # recorded, never dropped
        rec["error"] = f"{type(e).__name__}: {e}"
        ep.errors += 1
        if resp is None:
            resp = web.json_response({"error": rec["error"], "endpoint": ep.name}, status=502)
    finally:
        ep.in_flight -= 1
        ep.completed += 1
        rec["t_done"] = time.time()
        app["log"].write(json.dumps(rec) + "\n")
        app["log"].flush()
    return resp


async def handle_health(request):
    return web.json_response({"status": "ok", "policy": request.app["policy"].name})


async def handle_stats(request):
    app = request.app
    return web.json_response({"policy": app["policy"].name,
                              "endpoints": [asdict(e) for e in app["endpoints"]]})


async def handle_policy(request):
    app = request.app
    spec = (await request.json()).get("policy", "")
    try:
        app["policy"] = make_policy(spec, [e.name for e in app["endpoints"]], seed=app["seed"])
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    return web.json_response({"policy": app["policy"].name})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="/opt/fleet/endpoints.json")
    ap.add_argument("--endpoints", nargs="+", help="endpoint names to route across (default: all)")
    ap.add_argument("--policy", default="round_robin", help=f"one of {POLICY_NAMES}")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--log", required=True, help="JSONL file, one line per routed request")
    args = ap.parse_args()

    cfg = {e["name"]: e for e in json.loads(Path(args.config).read_text())["endpoints"]}
    names = args.endpoints or list(cfg)
    eps = [Endpoint(name=n, url=f"http://{cfg[n]['private_ip']}:{cfg[n]['port']}",
                    kind=cfg[n].get("kind", "")) for n in names]

    app = web.Application(client_max_size=64 * 2**20)  # image requests carry base64 data
    app["endpoints"] = eps
    app["seed"] = args.seed
    app["policy"] = make_policy(args.policy, names, seed=args.seed)
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
    print(f"router: policy={app['policy'].name} endpoints="
          f"{', '.join(f'{e.name}={e.url}' for e in eps)} listening on {args.host}:{args.port}", flush=True)
    web.run_app(app, host=args.host, port=args.port, access_log=None, print=None)


if __name__ == "__main__":
    main()
