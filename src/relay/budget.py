"""Token budget and rate quota management."""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Tuple, Optional, Deque


@dataclass
class TokenBudgetTracker:
    daily_token_limit: int = 95_000
    tpm_token_limit: int = 5_500
    daily_request_limit: int = 1_000
    rpm_limit: int = 30

    total_tokens_consumed: int = 0
    total_requests_count: int = 0

    # Rolling 60-second windows for per-minute rates: store (timestamp, tokens/count)
    _minute_tokens: Deque[Tuple[float, int]] = field(default_factory=deque)
    _minute_requests: Deque[Tuple[float, int]] = field(default_factory=deque)

    def _purge_expired(self, now: float) -> None:
        """Evict items older than 60 seconds from sliding windows."""
        cutoff = now - 60.0
        while self._minute_tokens and self._minute_tokens[0][0] < cutoff:
            self._minute_tokens.popleft()
        while self._minute_requests and self._minute_requests[0][0] < cutoff:
            self._minute_requests.popleft()

    def get_current_tpm(self, now: Optional[float] = None) -> int:
        if now is None:
            now = time.perf_counter()
        self._purge_expired(now)
        return sum(item[1] for item in self._minute_tokens)

    def get_current_rpm(self, now: Optional[float] = None) -> int:
        if now is None:
            now = time.perf_counter()
        self._purge_expired(now)
        return sum(item[1] for item in self._minute_requests)

    def check_admission(self, estimated_tokens: int = 500) -> Tuple[bool, Optional[str]]:
        """Check whether a new request can be admitted under rate and daily budgets."""
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
        """Record completed tokens and request occurrence."""
        now = time.perf_counter()
        tokens = prompt_tokens + completion_tokens
        self.total_tokens_consumed += tokens
        self.total_requests_count += 1

        self._minute_tokens.append((now, tokens))
        self._minute_requests.append((now, 1))

    def reset(self) -> None:
        """Reset all counters for clean experiment runs."""
        self.total_tokens_consumed = 0
        self.total_requests_count = 0
        self._minute_tokens.clear()
        self._minute_requests.clear()
