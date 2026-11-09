"""Centralized configuration for the Passageworks pipeline.

Provides structured, immutable dataclass configuration loaded from environment variables
or sensible defaults, avoiding hardcoded URLs, models, or operational thresholds.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _get_env_str(keys: list[str], default: str) -> str:
    """Retrieve the first non-empty environment variable matching keys, or return default."""
    for key in keys:
        val = os.getenv(key)
        if val is not None and val.strip():
            return val.strip()
    return default


def _get_env_int(keys: list[str], default: int) -> int:
    """Retrieve an integer environment variable with fallback."""
    for key in keys:
        val = os.getenv(key)
        if val is not None and val.strip():
            try:
                return int(val.strip())
            except ValueError:
                pass
    return default


def _get_env_float(keys: list[str], default: float) -> float:
    """Retrieve a float environment variable with fallback."""
    for key in keys:
        val = os.getenv(key)
        if val is not None and val.strip():
            try:
                return float(val.strip())
            except ValueError:
                pass
    return default


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable runtime configuration parameters for Passageworks pipeline components.

    Attributes:
        primary_model: Model used for factual drafting and verification.
        classifier_model: Fast model used for early scope gatekeeping.
        groq_api_key: Optional Groq API key (defaults to os.getenv).
        groq_base_url: Optional API base URL for Groq or Stand-in.
        llm_timeout_seconds: Per-call streaming timeout.
        request_deadline_seconds: Total queue + active execution deadline.
        max_retries: Maximum application-level retries for transient HTTP/rate errors.
        retry_backoff_base_seconds: Base exponential backoff duration.
        fast_fail_lockout_seconds: Lockout duration beyond which retries fast-fail.
        max_concurrent_requests: Maximum concurrency slots in admission queue.
        max_queue_depth: Maximum queue backlog before shedding load with 429.
        daily_token_budget: Daily token quota threshold for client-side pre-emption.
        tpm_token_budget: Tokens-per-minute threshold for token bucket tracker.
        rpm_budget: Requests-per-minute ceiling.
        papers_dir: Directory containing source research PDF documents.
        chunks_file: Path to extracted and indexed chunks JSONL file.
    """

    primary_model: str = "qwen/qwen3.8-27b"
    classifier_model: str = "qwen/qwen3.8-27b"
    groq_api_key: Optional[str] = None
    groq_base_url: Optional[str] = None
    llm_timeout_seconds: float = 15.0
    request_deadline_seconds: float = 25.0
    max_retries: int = 2
    retry_backoff_base_seconds: float = 1.0
    fast_fail_lockout_seconds: float = 10.0
    max_concurrent_requests: int = 3
    max_queue_depth: int = 25
    daily_token_budget: int = 500_000
    tpm_token_budget: int = 8_000
    rpm_budget: int = 30
    papers_dir: Path = Path("papers")
    chunks_file: Path = Path("papers/chunks.jsonl")

    @classmethod
    def from_env(cls) -> PipelineConfig:
        """Instantiate a PipelineConfig instance resolved dynamically from environment variables.

        Returns:
            Configured PipelineConfig instance honoring current environment settings.
        """
        api_key = _get_env_str(["GROQ_API_KEY", "RELAY_GROQ_API_KEY"], "")
        base_url = _get_env_str(
            ["GROQ_BASE_URL", "RELAY_BASE_URL", "STANDIN_URL"], "http://127.0.0.1:8000/v1"
        )
        if not base_url or base_url.lower() == "none":
            resolved_base_url = None
        else:
            resolved_base_url = base_url

        return cls(
            primary_model=_get_env_str(
                ["PASSAGEWORKS_PRIMARY_MODEL", "RELAY_PRIMARY_MODEL"], "qwen/qwen3.8-27b"
            ),
            classifier_model=_get_env_str(
                ["PASSAGEWORKS_CLASSIFIER_MODEL", "RELAY_CLASSIFIER_MODEL"], "qwen/qwen3.8-27b"
            ),
            groq_api_key=api_key or None,
            groq_base_url=resolved_base_url,
            llm_timeout_seconds=_get_env_float(
                ["PASSAGEWORKS_REQUEST_TIMEOUT_S", "LLM_TIMEOUT_SECONDS"], 15.0
            ),
            request_deadline_seconds=_get_env_float(
                ["PASSAGEWORKS_REQUEST_DEADLINE_S", "REQUEST_DEADLINE_SECONDS"], 25.0
            ),
            max_retries=_get_env_int(["PASSAGEWORKS_MAX_RETRIES", "MAX_RETRIES"], 2),
            retry_backoff_base_seconds=_get_env_float(
                ["PASSAGEWORKS_BACKOFF_BASE_S", "RETRY_BACKOFF_BASE_SECONDS"], 1.0
            ),
            fast_fail_lockout_seconds=_get_env_float(
                ["PASSAGEWORKS_FAST_FAIL_LOCKOUT_S", "FAST_FAIL_LOCKOUT_SECONDS"], 10.0
            ),
            max_concurrent_requests=_get_env_int(
                ["PASSAGEWORKS_MAX_CONCURRENT", "MAX_CONCURRENT_REQUESTS"], 3
            ),
            max_queue_depth=_get_env_int(["PASSAGEWORKS_MAX_QUEUE_DEPTH", "MAX_QUEUE_DEPTH"], 25),
            daily_token_budget=_get_env_int(
                ["PASSAGEWORKS_DAILY_TOKEN_LIMIT", "DAILY_TOKEN_BUDGET"], 500_000
            ),
            tpm_token_budget=_get_env_int(["PASSAGEWORKS_TPM_LIMIT", "TPM_TOKEN_BUDGET"], 8_000),
            rpm_budget=_get_env_int(["PASSAGEWORKS_RPM_LIMIT", "RPM_BUDGET"], 30),
            papers_dir=Path(os.getenv("PAPERS_DIR", "papers")),
            chunks_file=Path(os.getenv("CHUNKS_FILE", "papers/chunks.jsonl")),
        )


DEFAULT_CONFIG = PipelineConfig.from_env()
