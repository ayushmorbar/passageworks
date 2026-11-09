"""Configuration options for the Passageworks stand-in model service.

Provides empirical latency, jitter, rate-limit, and failure injection parameters
calibrated against live Groq API telemetry (November 2026).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_env_float(key: str, default: float) -> float:
    """Helper to extract float from environment variable."""
    val = os.getenv(key)
    if val is not None and val.strip():
        try:
            return float(val.strip())
        except ValueError:
            pass
    return default


def _get_env_int(key: str, default: int) -> int:
    """Helper to extract int from environment variable."""
    val = os.getenv(key)
    if val is not None and val.strip():
        try:
            return int(val.strip())
        except ValueError:
            pass
    return default


@dataclass
class StandinConfig:
    """Configurable runtime parameters for the Stand-in model simulation server.

    Attributes:
        base_ttft_ms: Baseline time-to-first-token delay in milliseconds.
        ttft_jitter_ms: Uniform random jitter (+/-) added to baseline TTFT.
        token_interval_ms: Streaming delay per emitted token (simulates throughput).
        load_slowdown_factor: Factor by which TTFT increases per concurrent in-flight request.
        failure_rate_500: Probability [0.0, 1.0] of returning synthetic 500 Internal Server Error.
        timeout_rate: Probability [0.0, 1.0] of hanging request to trigger client timeout.
        rpm_limit: Sliding 60-second requests-per-minute limit.
        daily_request_limit: Cumulative requests-per-day quota limit.
        daily_token_limit: Cumulative tokens-per-day quota limit.
        halved_limits_active: Boolean toggle halving effective RPM limits for scenario testing.
    """

    base_ttft_ms: float = _get_env_float("STANDIN_BASE_TTFT_MS", 210.0)
    ttft_jitter_ms: float = _get_env_float("STANDIN_TTFT_JITTER_MS", 45.0)
    token_interval_ms: float = _get_env_float("STANDIN_TOKEN_INTERVAL_MS", 3.0)
    load_slowdown_factor: float = _get_env_float("STANDIN_LOAD_SLOWDOWN_FACTOR", 0.15)
    failure_rate_500: float = _get_env_float("STANDIN_FAILURE_RATE_500", 0.0)
    timeout_rate: float = _get_env_float("STANDIN_TIMEOUT_RATE", 0.0)
    rpm_limit: int = _get_env_int("STANDIN_RPM_LIMIT", 30)
    daily_request_limit: int = _get_env_int("STANDIN_DAILY_REQUEST_LIMIT", 1_000)
    daily_token_limit: int = _get_env_int("STANDIN_DAILY_TOKEN_LIMIT", 500_000)
    halved_limits_active: bool = False

    def get_effective_rpm(self) -> int:
        """Compute the currently active RPM limit, accounting for halved limit mode.

        Returns:
            Effective integer requests-per-minute limit.
        """
        return self.rpm_limit // 2 if self.halved_limits_active else self.rpm_limit
