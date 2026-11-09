"""Groq API client wrapper with explicit timeouts, rate-limit header extraction, and retries."""

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional

import groq
from groq import AsyncGroq


@dataclass
class LLMCallResult:
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
    """Async client wrapper around Groq / Stand-in service with strict instrumentation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_timeout: float = 15.0,
        max_retries: int = 2,
        backoff_base: float = 1.0,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "dummy-key-for-standin")
        self.base_url = base_url
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base

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
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> LLMCallResult:
        """Execute a streaming chat completion, recording first-token latency, total latency, usage, and headers."""
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
                # Use with_raw_response to inspect HTTP headers
                raw_stream_resp = await self.client.chat.completions.with_raw_response.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )

                # Capture rate limit headers
                for k, v in raw_stream_resp.headers.items():
                    if k.lower().startswith(("x-ratelimit", "retry-after")):
                        response_headers[k.lower()] = v

                stream = raw_stream_resp.parse()
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        if first_chunk_t is None:
                            first_chunk_t = time.perf_counter()
                        collected_text.append(delta)

                    # Extract usage metadata from final chunk if present
                    if hasattr(chunk, "usage") and chunk.usage:
                        p_tokens = chunk.usage.prompt_tokens or p_tokens
                        c_tokens = chunk.usage.completion_tokens or c_tokens

                t_total = time.perf_counter()
                total_ms = (t_total - t0) * 1000.0
                first_token_ms = (
                    ((first_chunk_t - t0) * 1000.0) if first_chunk_t is not None else total_ms
                )
                full_content = "".join(collected_text)

                # Heuristic token fallback if usage chunk was not delivered by stream
                if p_tokens == 0:
                    input_words = sum(len(m.get("content", "").split()) for m in messages)
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
                            retry_after_s = max(float(ra_hdr), retry_after_s)
                        except ValueError:
                            pass
                # Add jitter
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
