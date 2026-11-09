"""FastAPI stand-in model service simulating Groq API behavior under load."""

import asyncio
import json
import random
import time
from collections import deque
from typing import List, Dict, Any, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from relay_standin.config import StandinConfig

app = FastAPI(title="Passageworks Stand-in Model Service")
config = StandinConfig()

# Concurrency and rate limiting state
active_in_flight_requests = 0
request_window = deque()  # (timestamp)
token_window = deque()  # (timestamp, tokens)
daily_request_count = 0
daily_token_count = 0


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = 0.0
    max_tokens: Optional[int] = 800
    stream: Optional[bool] = False


def purge_rate_windows(now: float) -> None:
    cutoff = now - 60.0
    while request_window and request_window[0] < cutoff:
        request_window.popleft()
    while token_window and token_window[0][0] < cutoff:
        token_window.popleft()


def generate_mock_reply(messages: List[Dict[str, Any]]) -> str:
    """Generate realistic responses based on prompt markers (CLASSIFY, DRAFT, VERIFY)."""
    full_prompt = " ".join(str(m.get("content", "")) for m in messages)
    user_query = str(messages[-1].get("content", "")).lower() if messages else ""

    # 1. Classification prompts
    if "scope gatekeeper for Passageworks" in full_prompt or "is_in_scope" in full_prompt:
        # Check if negative/out-of-scope query based strictly on the user query
        negative_triggers = [
            "cooking",
            "recipe",
            "french revolution",
            "mamba",
            "quantum",
            "weather",
            "imagenet",
            "russian",
            "apple m3",
            "rlhf",
        ]
        if any(term in user_query for term in negative_triggers):
            return json.dumps(
                {
                    "is_in_scope": False,
                    "relevant_paper": "none",
                    "reason": "Topic is not covered in the three allowed papers.",
                }
            )
        if any(
            term in user_query
            for term in ["transformer", "attention", "encoder", "decoder", "bleu", "positional"]
        ):
            return json.dumps(
                {
                    "is_in_scope": True,
                    "relevant_paper": "attention",
                    "reason": "Question pertains to Attention Is All You Need.",
                }
            )
        if any(
            term in user_query
            for term in ["moshi", "dialogue", "speech", "mimi", "audio", "full-duplex"]
        ):
            return json.dumps(
                {
                    "is_in_scope": True,
                    "relevant_paper": "moshi",
                    "reason": "Question pertains to Moshi foundation model.",
                }
            )
        if any(term in user_query for term in ["chunking", "dynamic", "hierarchical", "boundary"]):
            return json.dumps(
                {
                    "is_in_scope": True,
                    "relevant_paper": "dynamic_chunking",
                    "reason": "Question pertains to dynamic chunking.",
                }
            )
        return json.dumps(
            {
                "is_in_scope": True,
                "relevant_paper": "attention",
                "reason": "Question relevant to library papers.",
            }
        )

    # 2. Verification prompts
    if "Fact Verification Auditor" in full_prompt:
        return json.dumps(
            {
                "is_valid": True,
                "unsupported_claims": [],
                "suggested_revisions": "",
            }
        )

    # 3. Drafting prompts
    if "EVIDENCE EXCERPTS:" in full_prompt:
        if "moshi" in full_prompt.lower():
            return (
                "Moshi operates as a speech-text foundation model utilizing the Mimi neural audio codec "
                "[Moshi: a speech-text foundation model for real-time dialogue, 3 Architecture, p.5]. "
                "The system achieves a theoretical conversational latency of 160ms with full-duplex communication "
                "[Moshi: a speech-text foundation model for real-time dialogue, 1 Introduction, p.2]."
            )
        if "chunking" in full_prompt.lower() or "dynamic" in full_prompt.lower():
            return (
                "Dynamic chunking segments token sequences dynamically based on boundary prediction "
                "[Dynamic Chunking for End-to-End Hierarchical Sequence Modeling, 3 Methodology, p.4]. "
                "This achieves linear complexity across sequence length while preserving boundary accuracy "
                "[Dynamic Chunking for End-to-End Hierarchical Sequence Modeling, 4 Experiments, p.7]."
            )
        # Default Attention
        return (
            "The Transformer architecture uses scaled dot-product attention computed as "
            "Attention(Q, K, V) = softmax(QK^T / sqrt(d_k))V "
            "[Attention Is All You Need, 3.2.1 Scaled Dot-Product Attention, p.4]. "
            "Multi-head attention allows the model to jointly attend to information from different representation subspaces "
            "[Attention Is All You Need, 3.2.2 Multi-Head Attention, p.5]."
        )

    # General fallback
    return (
        "The models in the restricted library demonstrate sequence processing mechanisms "
        "[Attention Is All You Need, 1 Introduction, p.1]."
    )


@app.post("/v1/chat/completions")
@app.post("/v1/openai/v1/chat/completions")
@app.post("/openai/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    global active_in_flight_requests, daily_request_count, daily_token_count
    now = time.perf_counter()
    purge_rate_windows(now)

    effective_rpm = config.get_effective_rpm()
    current_rpm = len(request_window)

    # Check RPM limit
    if current_rpm >= effective_rpm:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "message": f"Rate limit reached for RPM: {effective_rpm}",
                    "type": "tokens_per_minute_exceeded",
                    "code": "rate_limit_exceeded",
                }
            },
            headers={
                "retry-after": "2.5",
                "x-ratelimit-limit-requests": str(effective_rpm),
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "2.5s",
                "x-ratelimit-limit-tokens": "6000",
                "x-ratelimit-remaining-tokens": "0",
                "x-ratelimit-reset-tokens": "2.5s",
            },
        )

    # Check daily limit
    if (
        daily_request_count >= config.daily_request_limit
        or daily_token_count >= config.daily_token_limit
    ):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "message": "Daily budget exhausted.",
                    "type": "daily_limit_exceeded",
                    "code": "daily_quota_exhausted",
                }
            },
            headers={
                "retry-after": "3600",
                "x-ratelimit-limit-requests": str(config.daily_request_limit),
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "3600s",
                "x-ratelimit-limit-tokens": str(config.daily_token_limit),
                "x-ratelimit-remaining-tokens": "0",
            },
        )

    # Inject simulated 500 error if configured
    if config.failure_rate_500 > 0.0 and random.random() < config.failure_rate_500:
        return JSONResponse(
            status_code=500,
            content={"error": {"message": "Internal server error", "type": "server_error"}},
        )

    # Inject simulated timeout if configured
    if config.timeout_rate > 0.0 and random.random() < config.timeout_rate:
        await asyncio.sleep(20.0)

    # Register in-flight and rate limit tracking
    active_in_flight_requests += 1
    request_window.append(now)
    daily_request_count += 1

    reply_content = generate_mock_reply(req.messages)
    words = reply_content.split()
    est_prompt_tokens = sum(len(str(m.get("content", "")).split()) for m in req.messages)
    est_comp_tokens = len(words)
    est_total_tokens = est_prompt_tokens + est_comp_tokens

    token_window.append((now, est_total_tokens))
    daily_token_count += est_total_tokens

    # Compute load-dependent latency
    slowdown_multiplier = 1.0 + (
        config.load_slowdown_factor * max(0, active_in_flight_requests - 1)
    )
    jitter = random.uniform(-config.ttft_jitter_ms, config.ttft_jitter_ms)
    simulated_ttft_s = max(0.02, (config.base_ttft_ms + jitter) / 1000.0) * slowdown_multiplier

    headers = {
        "x-ratelimit-limit-requests": str(effective_rpm),
        "x-ratelimit-remaining-requests": str(max(0, effective_rpm - len(request_window))),
        "x-ratelimit-reset-requests": "1.0s",
        "x-ratelimit-limit-tokens": "6000",
        "x-ratelimit-remaining-tokens": str(max(0, 6000 - sum(t[1] for t in token_window))),
        "x-ratelimit-reset-tokens": "2.0s",
    }

    if not req.stream:
        # Non-streaming mode
        try:
            await asyncio.sleep(simulated_ttft_s + (len(words) * config.token_interval_ms / 1000.0))
            return JSONResponse(
                content={
                    "id": f"chatcmpl-mock-{int(time.time() * 1000)}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": req.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": reply_content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": est_prompt_tokens,
                        "completion_tokens": est_comp_tokens,
                        "total_tokens": est_total_tokens,
                    },
                },
                headers=headers,
            )
        finally:
            active_in_flight_requests -= 1

    # Streaming mode
    async def stream_generator():
        global active_in_flight_requests
        try:
            # TTFT delay
            await asyncio.sleep(simulated_ttft_s)

            for i, word in enumerate(words):
                token_chunk = word + (" " if i < len(words) - 1 else "")
                chunk_data = {
                    "id": f"chatcmpl-mock-{int(time.time() * 1000)}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": req.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": token_chunk},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"
                await asyncio.sleep(config.token_interval_ms / 1000.0)

            # Final chunk with usage metadata
            final_chunk = {
                "id": f"chatcmpl-mock-{int(time.time() * 1000)}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": req.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": est_prompt_tokens,
                    "completion_tokens": est_comp_tokens,
                    "total_tokens": est_total_tokens,
                },
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        finally:
            active_in_flight_requests -= 1

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


@app.get("/health")
async def health_check():
    """Health check endpoint returning server status and active in-flight count."""
    return {"status": "ok", "active_in_flight": active_in_flight_requests}


@app.post("/control/reset")
async def reset_control():
    """Reset all state counters and restore default config for clean scenario execution."""
    global active_in_flight_requests, daily_request_count, daily_token_count, config
    active_in_flight_requests = 0
    daily_request_count = 0
    daily_token_count = 0
    request_window.clear()
    token_window.clear()
    config = StandinConfig()
    return {"status": "reset", "active": 0}


@app.post("/control/configure")
async def update_config(new_cfg: Dict[str, Any]):
    """Update runtime stand-in parameters."""
    for k, v in new_cfg.items():
        if hasattr(config, k):
            setattr(config, k, v)
    return {"status": "configured", "current": config.__dict__}
