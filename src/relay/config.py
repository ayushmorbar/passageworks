"""Central configuration and tunable parameters for Passageworks."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    # Model selections
    primary_model: str = os.getenv("RELAY_PRIMARY_MODEL", "llama-3.3-70b-versatile")
    classifier_model: str = os.getenv("RELAY_CLASSIFIER_MODEL", "llama-3.1-8b-instant")

    # Timeouts and deadlines
    llm_timeout_seconds: float = 15.0
    request_deadline_seconds: float = 30.0

    # Application-level retry policy (SDK retries must be 0)
    max_retries: int = 2
    retry_backoff_base_seconds: float = 1.0

    # Concurrency and queue admission
    max_concurrent_requests: int = 3
    max_queue_depth: int = 50

    # Token budget constraints (Groq Free Tier limits)
    daily_token_budget: int = 95_000  # Conservative safety ceiling under 100k
    tpm_token_budget: int = 5_500  # Conservative ceiling under ~6k TPM

    # Corpus paths
    papers_dir: Path = Path("papers")
    chunks_file: Path = Path("papers/chunks.jsonl")

    # Stand-in service URL
    standin_base_url: str = "http://127.0.0.1:8000/v1"


DEFAULT_CONFIG = PipelineConfig()
