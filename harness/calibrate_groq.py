"""Conservative calibration harness to measure real Groq service behavior without blowing quota.

Executes a small, metered sample against the live Groq Cloud API, extracting rate limit
headers, TTFT, throughput, and error response envelopes to calibrate the Stand-in service.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import groq
from groq import AsyncGroq


def load_env_local(env_path: Optional[Path] = None) -> Dict[str, str]:
    """Parse .env.local or .env for credentials without committing or exposing them.

    Args:
        env_path: Optional custom path to environment file.

    Returns:
        Dictionary of key-value environment variables.
    """
    path = env_path or Path(".env.local")
    if not path.exists():
        path = Path(".env")
    env_vars: Dict[str, str] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars


async def calibrate(num_samples: int = 5) -> None:
    """Run empirical calibration against the live Groq Cloud API.

    Args:
        num_samples: Small number of test completions (default 5) to conserve free quota.
    """
    env_vars = load_env_local()
    api_key = env_vars.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[ERROR] GROQ_API_KEY not found in .env.local, .env, or system environment.")
        return

    client = AsyncGroq(api_key=api_key, max_retries=0)
    out_dir = Path("results/calibration")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Step 1: Inspecting live available models on Groq...")
    try:
        models_resp = await client.models.list()
        available_models = [m.id for m in models_resp.data]
        print(f"Found {len(available_models)} models: {available_models[:6]}...")
    except Exception as e:
        print(f"[WARN] Failed to list models: {e}")
        available_models = ["qwen/qwen3.8-27b", "llama-3.3-70b-versatile"]

    # Target active model as of November 2026
    candidate_model = "qwen/qwen3.8-27b"
    if candidate_model not in available_models:
        for m in available_models:
            if "70b" in m or "llama-3" in m or "qwen" in m:
                candidate_model = m
                break

    print(f"\nStep 2: Calibrating against chosen model: {candidate_model}")
    print(f"Running {num_samples} conservative test calls with metered delays...")

    sample_prompts = [
        "What is the core idea of the Transformer in Attention Is All You Need in 2 sentences?",
        "Explain the key architectural difference between Moshi and cascaded speech models.",
        "What is the mathematical definition of scaled dot-product attention?",
        "How does dynamic chunking differ from fixed chunking in sequence models?",
        "Summarize the Mimi neural audio codec used in Moshi in 1 sentence.",
    ]

    telemetry_records: List[Dict[str, Any]] = []

    for i in range(min(num_samples, len(sample_prompts))):
        prompt = sample_prompts[i]
        print(f"[{i + 1}/{num_samples}] Dispatching: '{prompt[:45]}...'")

        t0 = time.perf_counter()
        first_token_time: Optional[float] = None
        collected_chunks: List[str] = []
        captured_headers: Dict[str, str] = {}

        try:
            raw_resp = await client.chat.completions.with_raw_response.create(
                model=candidate_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=250,
                temperature=0.0,
                stream=True,
            )

            # Extract rate limit headers
            for k, v in raw_resp.headers.items():
                if k.lower().startswith(("x-ratelimit", "retry-after")):
                    captured_headers[k.lower()] = v

            stream = await raw_resp.parse()
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    collected_chunks.append(delta)

            t_end = time.perf_counter()
            total_duration_ms = (t_end - t0) * 1000.0
            ttft_ms = (
                ((first_token_time - t0) * 1000.0)
                if first_token_time is not None
                else total_duration_ms
            )
            full_text = "".join(collected_chunks)

            record = {
                "sample_index": i + 1,
                "model": candidate_model,
                "prompt": prompt,
                "first_token_ms": round(ttft_ms, 2),
                "total_duration_ms": round(total_duration_ms, 2),
                "words_generated": len(full_text.split()),
                "rate_headers": captured_headers,
                "response_preview": full_text[:120],
            }
            telemetry_records.append(record)
            print(f"    -> TTFT: {ttft_ms:.1f}ms | Total: {total_duration_ms:.1f}ms")

        except groq.RateLimitError as rle:
            print(f"    -> [429 RATE LIMIT]: {rle}")
            telemetry_records.append({"sample_index": i + 1, "error": "429 RateLimitError"})
        except Exception as exc:
            print(f"    -> [ERROR]: {exc}")
            telemetry_records.append({"sample_index": i + 1, "error": str(exc)})

        # Conservative pause between requests to preserve sliding TPM window
        await asyncio.sleep(2.0)

    # Save telemetry file
    out_file = out_dir / "real_groq_telemetry.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
                "model_calibrated": candidate_model,
                "num_samples": len(telemetry_records),
                "records": telemetry_records,
            },
            f,
            indent=2,
        )
    print(f"\nSaved calibration telemetry to {out_file}")


if __name__ == "__main__":
    asyncio.run(calibrate(num_samples=5))
