"""Configuration options for Passageworks stand-in model service."""

from dataclasses import dataclass


@dataclass
class StandinConfig:
    # Latency model (calibrated from live Groq qwen/qwen3.8-27b telemetry)
    base_ttft_ms: float = 210.0
    ttft_jitter_ms: float = 45.0
    token_interval_ms: float = 3.0  # ~330 tokens/sec streaming throughput on Groq LPU

    # Load-dependent degradation: latency increases by load_factor per concurrent request
    load_slowdown_factor: float = 0.15

    # Injected error rates
    failure_rate_500: float = 0.0
    timeout_rate: float = 0.0

    # Rate limits (calibrated from Groq response headers)
    rpm_limit: int = 30
    daily_request_limit: int = 1_000
    daily_token_limit: int = 500_000

    # Halved mode switch
    halved_limits_active: bool = False

    def get_effective_rpm(self) -> int:
        return self.rpm_limit // 2 if self.halved_limits_active else self.rpm_limit
