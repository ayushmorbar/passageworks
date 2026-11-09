"""Token budget and rate quota management for the Passageworks pipeline.

Enforces client-side sliding-window Tokens-Per-Minute (TPM), Requests-Per-Minute (RPM),
and cumulative daily token/request ceilings to pre-emptively prevent upstream 429 lockouts.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Tuple


@dataclass
class TokenBudgetTracker:
    """Sliding-window token and request quota tracker with pre-admission checks.

    Attributes:
        daily_token_limit: Maximum cumulative tokens permitted per day.
        tpm_token_limit: Maximum rolling 60-second tokens permitted.
        daily_request_limit: Maximum cumulative requests permitted per day.
        rpm_limit: Maximum rolling 60-second requests permitted.
        total_tokens_consumed: Monotonically increasing cumulative token counter.
        total_requests_count: Monotonically increasing cumulative request counter.
    """

    daily_token_limit: int = 500_000
    tpm_token_limit: int = 8_000
    daily_request_limit: int = 1_000
    rpm_limit: int = 30

    total_tokens_consumed: int = 0
    total_requests_count: int = 0

    # Rolling 60-second windows for per-minute rates: store (timestamp, tokens/count)
    _minute_tokens: Deque[Tuple[float, int]] = field(default_factory=deque)
    _minute_requests: Deque[Tuple[float, int]] = field(default_factory=deque)

    def _purge_expired(self, now: float) -> None:
        """Evict items older than 60 seconds from sliding windows.

        Args:
            now: Current monotonic timestamp in seconds.
        """
        cutoff = now - 60.0
        while self._minute_tokens and self._minute_tokens[0][0] < cutoff:
            self._minute_tokens.popleft()
        while self._minute_requests and self._minute_requests[0][0] < cutoff:
            self._minute_requests.popleft()

    def get_current_tpm(self, now: Optional[float] = None) -> int:
        """Calculate tokens expended in the trailing 60-second rolling window.

        Args:
            now: Optional timestamp; defaults to monotonic time.

        Returns:
            Integer sum of tokens recorded in the active rolling window.
        """
        if now is None:
            now = time.perf_counter()
        self._purge_expired(now)
        return sum(item[1] for item in self._minute_tokens)

    def get_current_rpm(self, now: Optional[float] = None) -> int:
        """Calculate requests executed in the trailing 60-second rolling window.

        Args:
            now: Optional timestamp; defaults to monotonic time.

        Returns:
            Integer count of requests initiated in the active rolling window.
        """
        if now is None:
            now = time.perf_counter()
        self._purge_expired(now)
        return sum(item[1] for item in self._minute_requests)

    def check_admission(self, estimated_tokens: int = 800) -> Tuple[bool, Optional[str]]:
        """Pre-emptively verify whether an incoming request can be admitted without breach.

        Args:
            estimated_tokens: Upper-bound heuristic estimate of tokens required for this request.

        Returns:
            Tuple of (admitted: bool, rejection_reason: Optional[str]).
        """
        now = time.perf_counter()
        self._purge_expired(now)

        # 1. Daily ceilings
        if self.total_tokens_consumed + estimated_tokens > self.daily_token_limit:
            return False, "Daily token budget exhausted."
        if self.total_requests_count >= self.daily_request_limit:
            return False, "Daily request limit exhausted."

        # 2. Minute ceilings
        current_tpm = self.get_current_tpm(now)
        if current_tpm + estimated_tokens > self.tpm_token_limit:
            return (
                False,
                f"Per-minute token limit near capacity ({current_tpm}/{self.tpm_token_limit} TPM).",
            )

        current_rpm = self.get_current_rpm(now)
        if current_rpm >= self.rpm_limit:
            return False, f"Per-minute request limit reached ({current_rpm}/{self.rpm_limit} RPM)."

        return True, None

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Commit actual expended tokens and register request completion.

        Args:
            prompt_tokens: Measured input prompt tokens.
            completion_tokens: Measured output completion tokens.
        """
        now = time.perf_counter()
        tokens = prompt_tokens + completion_tokens
        self.total_tokens_consumed += tokens
        self.total_requests_count += 1

        self._minute_tokens.append((now, tokens))
        self._minute_requests.append((now, 1))

    def reset(self) -> None:
        """Reset all counters and clear sliding windows for fresh benchmark scenarios."""
        self.total_tokens_consumed = 0
        self.total_requests_count = 0
        self._minute_tokens.clear()
        self._minute_requests.clear()
