"""E1 isolated profiles and E4 cold-start load time, one model at a time.

For each model: unload it and time a 1-token request (cold start), then run
text requests over a prompt-length x output-length grid, then (for vision
models) image requests at several resolutions. The model is unloaded at the
end so the next model starts cold.

    python Phase1/harness/run_profile.py --models qwen3.5:0.8b qwen3.5:2b
"""

import argparse
import re

from common import RAW_DIR, append_jsonl, chat, loaded_models, model_info, nonce, unload, write_meta
from sysmon import OllamaSampler
from workloads import chart_image, length_prompt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--prompt-tokens", nargs="+", type=int, default=[128, 512, 2048])
    ap.add_argument("--output-tokens", nargs="+", type=int, default=[32, 256])
    ap.add_argument("--image-sizes", nargs="+", type=int, default=[256, 512, 1024])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--cold-reps", type=int, default=2)
    ap.add_argument("--out", default=str(RAW_DIR / "e1_profile.jsonl"))
    args = ap.parse_args()

    write_meta(args.out, models=args.models, args=vars(args))
    sampler = OllamaSampler().start()

    def record(rec, **fields):
        rec.update(fields)
        rec.update(sampler.window(rec["t_start"], rec["t_end"]))
        rec["text"] = rec["text"][:200]
        append_jsonl(args.out, rec)
        status = "ok" if rec["ok"] else rec.get("error")
        print(f"{rec['model']:<18} {fields} ttft={rec['ttft_s']} "
              f"prefill_tps={rec['prefill_tps']} decode_tps={rec['decode_tps']} {status}",
              flush=True)

    for model in args.models:
        info = model_info(model)

        for k in range(args.cold_reps):
            unload(model)
            rec = chat(model, f"[{nonce()}] Reply with OK.", num_predict=1)
            rec["resident"] = loaded_models().get(model)
            record(rec, kind="cold_start", rep=k)

        for p in args.prompt_tokens:
            for o in args.output_tokens:
                for k in range(args.reps):
                    rec = chat(model, length_prompt(p, seed=k), num_predict=o)
                    record(rec, kind="text", target_prompt_tokens=p,
                           target_output_tokens=o, rep=k)

        if "vision" in info["capabilities"]:
            for size in args.image_sizes:
                for k in range(args.reps):
                    b64, answer = chart_image(size, seed=k)
                    prompt = (f"[{nonce()}] Which bar in this chart is the tallest? "
                              "Reply with the letter only.")
                    rec = chat(model, prompt, num_predict=8, images=[b64])
                    letters = re.findall(r"\b([A-E])\b", rec["text"])
                    record(rec, kind="image", image_px=size, rep=k, answer=answer,
                           correct=bool(letters) and letters[0] == answer)

        unload(model)

    sampler.stop()


if __name__ == "__main__":
    main()
