"""Conservative calibration harness to measure real Groq service behavior without blowing quota."""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List

import groq
from groq import AsyncGroq


def load_env_local(env_path: Path = Path(".env.local")) -> Dict[str, str]:
    """Parse .env.local for credentials without committing or exposing them."""
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars


async def calibrate(num_samples: int = 5):
    env_vars = load_env_local()
    api_key = env_vars.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[ERROR] GROQ_API_KEY not found in .env.local or environment.")
        return

    client = AsyncGroq(api_key=api_key, max_retries=0)
    out_dir = Path("results/calibration")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Step 1: Inspecting live available models on Groq...")
    try:
        models_resp = await client.models.list()
        available_models = [m.id for m in models_resp.data]
        print(f"Available models count: {len(available_models)}")
        target_models = [
            m
            for m in available_models
            if any(k in m for k in ["llama-3.3-70b", "llama-3.1-8b", "qwen", "gpt-oss"])
        ]
        print(f"Target candidate models found: {target_models}")
    except Exception as exc:
        print(f"[WARN] Could not fetch models list: {exc}")
        available_models = []

    # Qwen 3.8 27B is direct chat completion without internal reasoning preamble
    calib_model = (
        "qwen/qwen3.8-27b" if "qwen/qwen3.8-27b" in available_models else "openai/gpt-oss-20b"
    )

    print(f"\nStep 2: Sending {num_samples} sample calibration requests to '{calib_model}'...")
    samples: List[Dict[str, Any]] = []

    prompt = "State one sentence on how multi-head attention functions in transformers."

    for i in range(num_samples):
        print(f"  Sampling request {i + 1}/{num_samples}...")
        t0 = time.perf_counter()
        first_token_t = None
        collected_tokens = []
        captured_headers = {}

        try:
            raw_resp = await client.chat.completions.with_raw_response.create(
                model=calib_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.0,
                stream=True,
            )

            for k, v in raw_resp.headers.items():
                if k.lower().startswith(("x-ratelimit", "retry-after")):
                    captured_headers[k.lower()] = v

            stream = await raw_resp.parse()
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    if first_token_t is None:
                        first_token_t = time.perf_counter()
                    collected_tokens.append(delta)

            t_end = time.perf_counter()
            ttft_ms = (first_token_t - t0) * 1000.0 if first_token_t else None
            total_ms = (t_end - t0) * 1000.0

            sample_data = {
                "sample_idx": i + 1,
                "model": calib_model,
                "status": 200,
                "ttft_ms": round(ttft_ms, 2) if ttft_ms else None,
                "total_ms": round(total_ms, 2),
                "content_preview": "".join(collected_tokens)[:80],
                "headers": captured_headers,
            }
            samples.append(sample_data)
            print(
                f"    -> TTFT: {sample_data['ttft_ms']}ms | Total: {sample_data['total_ms']}ms | Remaining tokens: {captured_headers.get('x-ratelimit-remaining-tokens')}"
            )

        except groq.RateLimitError as rle:
            t_end = time.perf_counter()
            sample_data = {
                "sample_idx": i + 1,
                "model": calib_model,
                "status": 429,
                "error": str(rle),
                "total_ms": round((t_end - t0) * 1000.0, 2),
            }
            samples.append(sample_data)
            print(f"    -> Rate limited (429): {rle}")

        except Exception as err:
            t_end = time.perf_counter()
            sample_data = {
                "sample_idx": i + 1,
                "model": calib_model,
                "status": "error",
                "error": str(err),
                "total_ms": round((t_end - t0) * 1000.0, 2),
            }
            samples.append(sample_data)
            print(f"    -> Error: {err}")

        # Sleep between requests to protect quota
        if i < num_samples - 1:
            await asyncio.sleep(2.0)

    # Save summary report
    report_file = out_dir / "real_groq_telemetry.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "available_models": available_models,
                "tested_model": calib_model,
                "samples": samples,
            },
            f,
            indent=2,
        )

    print(f"\nCalibration complete. Telemetry saved to {report_file}")


if __name__ == "__main__":
    asyncio.run(calibrate(num_samples=5))
