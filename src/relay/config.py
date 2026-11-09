"""Central configuration and tunable parameters for Passageworks."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    # Model selections (calibrated from live Groq account November 2026)
    primary_model: str = os.getenv("RELAY_PRIMARY_MODEL", "qwen/qwen3.8-27b")
    classifier_model: str = os.getenv("RELAY_CLASSIFIER_MODEL", "qwen/qwen3.8-27b")

    # Timeouts and deadlines
    llm_timeout_seconds: float = 15.0
    request_deadline_seconds: float = 30.0

    # Application-level retry policy (SDK retries must be 0)
    max_retries: int = 2
    retry_backoff_base_seconds: float = 1.0

    # Concurrency and queue admission
    max_concurrent_requests: int = 3
    max_queue_depth: int = 50

    # Token budget constraints (Groq Free Tier measured limits)
    daily_token_budget: int = 450_000  # Conservative safety ceiling under 500k TPD
    tpm_token_budget: int = 7_500  # Conservative ceiling under measured 8,000 TPM

    # Corpus paths
    papers_dir: Path = Path("papers")
    chunks_file: Path = Path("papers/chunks.jsonl")

    # Stand-in service URL
    standin_base_url: str = "http://127.0.0.1:8000/v1"


DEFAULT_CONFIG = PipelineConfig()
