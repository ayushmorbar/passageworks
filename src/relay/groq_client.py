"""Groq API client wrapper with explicit timeouts, rate-limit header extraction, and retries.

Ensures SDK retries are disabled (max_retries=0) so that all backoff, jitter,
telemetry tracking, and fast-fail behavior remain under application-level control.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import groq
from groq import AsyncGroq


@dataclass
class LLMCallResult:
    """Instrumented result of an LLM completion call.

    Attributes:
        content: Raw generated text completion.
        prompt_tokens: Number of input prompt tokens consumed.
        completion_tokens: Number of output completion tokens produced.
        total_tokens: Sum of prompt and completion tokens.
        first_token_ms: Latency to first streamed token arrival in milliseconds.
        total_call_ms: Total duration of the network call in milliseconds.
        retries_used: Number of backoff retries performed during this call.
        headers: Extracted rate-limit and diagnostic response headers.
        error_message: Optional error string if the call failed or retries exhausted.
    """

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    first_token_ms: float
    total_call_ms: float
    retries_used: int
    headers: Dict[str, str] = field(default_factory=dict)
    error_message: Optional[str] = None


class GroqClientWrapper:
    """Asynchronous client wrapper around Groq Cloud or the Stand-in model service.

    Args:
        api_key: Optional Groq API key (defaults to GROQ_API_KEY environment variable).
        base_url: Optional API endpoint base URL (e.g. http://127.0.0.1:8000/v1 for stand-in).
        default_timeout: Timeout in seconds for individual streaming completion calls.
        max_retries: Maximum application-level retries on rate limits or transient errors.
        backoff_base: Base duration in seconds for exponential backoff calculations.
        fast_fail_lockout_s: Lockout threshold in seconds; if retry-after exceeds this, fail immediately.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_timeout: float = 15.0,
        max_retries: int = 2,
        backoff_base: float = 1.0,
        fast_fail_lockout_s: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "dummy-key-for-standin")
        self.base_url = base_url
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.fast_fail_lockout_s = fast_fail_lockout_s

        # Crucial: set max_retries=0 in SDK so we control retry timing, logging and backoff
        self.client = AsyncGroq(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.default_timeout,
            max_retries=0,
        )

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> LLMCallResult:
        """Execute a streaming chat completion, recording first-token latency and rate headers.

        Args:
            model: Model identifier (e.g. 'qwen/qwen3.8-27b').
            messages: List of message dictionaries with 'role' and 'content'.
            temperature: Sampling temperature (0.0 for factual reproducibility).
            max_tokens: Maximum tokens to generate.

        Returns:
            LLMCallResult containing response content, tokens, latency, and headers.
        """
        retries_attempted = 0
        last_error = None

        while retries_attempted <= self.max_retries:
            t0 = time.perf_counter()
            first_chunk_t: Optional[float] = None
            collected_text: List[str] = []
            response_headers: Dict[str, str] = {}
            p_tokens = 0
            c_tokens = 0

            try:
                # Use with_raw_response to inspect HTTP response headers directly
                raw_stream_resp = await self.client.chat.completions.with_raw_response.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )

                # Capture rate limit headers
                for k, v in raw_stream_resp.headers.items():
                    if k.lower().startswith(("x-ratelimit", "retry-after")):
                        response_headers[k.lower()] = v

                stream = await raw_stream_resp.parse()
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        if first_chunk_t is None:
                            first_chunk_t = time.perf_counter()
                        collected_text.append(delta)

                    # Extract usage metadata from final chunk if delivered by stream
                    if hasattr(chunk, "usage") and chunk.usage:
                        p_tokens = chunk.usage.prompt_tokens or p_tokens
                        c_tokens = chunk.usage.completion_tokens or c_tokens

                t_total = time.perf_counter()
                total_ms = (t_total - t0) * 1000.0
                first_token_ms = (
                    ((first_chunk_t - t0) * 1000.0) if first_chunk_t is not None else total_ms
                )
                full_content = "".join(collected_text)

                # Heuristic token fallback if usage chunk was omitted in stream
                if p_tokens == 0:
                    input_words = sum(len(str(m.get("content", "")).split()) for m in messages)
                    p_tokens = int(input_words * 1.33)
                if c_tokens == 0:
                    c_tokens = int(len(full_content.split()) * 1.33)

                return LLMCallResult(
                    content=full_content,
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    total_tokens=p_tokens + c_tokens,
                    first_token_ms=first_token_ms,
                    total_call_ms=total_ms,
                    retries_used=retries_attempted,
                    headers=response_headers,
                )

            except groq.RateLimitError as rle:
                last_error = rle
                retries_attempted += 1
                if retries_attempted > self.max_retries:
                    break

                # Parse retry-after header if present, or exponential backoff
                retry_after_s = self.backoff_base * (2 ** (retries_attempted - 1))
                if hasattr(rle, "response") and rle.response:
                    ra_hdr = rle.response.headers.get("retry-after")
                    if ra_hdr:
                        try:
                            hdr_val = float(ra_hdr)
                            if hdr_val > self.fast_fail_lockout_s:
                                # Long lockout (e.g. daily quota exhaustion); do not block, fail immediately
                                break
                            retry_after_s = max(hdr_val, retry_after_s)
                        except ValueError:
                            pass
                retry_after_s = min(retry_after_s, 5.0)
                # Add jitter to desynchronize concurrent clients
                jitter = random.uniform(0.1, 0.5)
                await asyncio.sleep(retry_after_s + jitter)

            except (groq.APIConnectionError, groq.InternalServerError) as net_err:
                last_error = net_err
                retries_attempted += 1
                if retries_attempted > self.max_retries:
                    break
                await asyncio.sleep(self.backoff_base * (2 ** (retries_attempted - 1)))

            except Exception as unrecoverable:
                # 400 Bad Request, Auth error, etc. — do not retry
                t_total = time.perf_counter()
                return LLMCallResult(
                    content="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    first_token_ms=0.0,
                    total_call_ms=(t_total - t0) * 1000.0,
                    retries_used=retries_attempted,
                    error_message=str(unrecoverable),
                )

        t_total = time.perf_counter()
        return LLMCallResult(
            content="",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            first_token_ms=0.0,
            total_call_ms=(t_total - t0) * 1000.0,
            retries_used=retries_attempted,
            error_message=f"Exhausted retries: {last_error}",
        )
