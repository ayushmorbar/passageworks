"""Admission queue and concurrency throttling for Passageworks.

Implements bounded FIFO queueing, semaphore-governed concurrency slots,
hard request deadlines, and load shedding with explicit peak queue tracking.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional


class QueueFullError(Exception):
    """Raised when the admission queue capacity is saturated and cannot accept new requests."""


class RequestTimeoutError(Exception):
    """Raised when request queue wait time exceeds the configured request deadline."""


@dataclass
class QueueSlot:
    """Represents an acquired concurrency slot with queue waiting duration.

    Attributes:
        acquired: Boolean flag indicating successful slot acquisition.
        queue_wait_ms: Duration in milliseconds spent waiting in queue before acquisition.
    """

    acquired: bool
    queue_wait_ms: float


class AdmissionController:
    """Manages active worker concurrency and bounded queue depth with deadline tracking.

    Args:
        max_concurrent: Maximum simultaneous requests actively executing.
        max_queue: Maximum requests allowed to wait in queue before shedding load.
        deadline_s: Maximum permissible queue wait time in seconds before timing out.
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        max_queue: int = 25,
        deadline_s: float = 25.0,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self.deadline_s = deadline_s

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._current_queued = 0
        self._lock = asyncio.Lock()
        self._peak_queue_length = 0

    @property
    def peak_queue_length(self) -> int:
        """Return the highest queue length observed since initialization or last reset."""
        return self._peak_queue_length

    async def acquire_slot(self, timeout_override: Optional[float] = None) -> QueueSlot:
        """Attempt to join the admission queue and wait for an active execution slot.

        Args:
            timeout_override: Optional custom deadline in seconds.

        Returns:
            QueueSlot instance recording acquisition status and wait latency.

        Raises:
            QueueFullError: If current queue backlog equals or exceeds max_queue.
            RequestTimeoutError: If the slot could not be acquired within the deadline.
        """
        deadline = timeout_override or self.deadline_s
        queued_start = time.perf_counter()

        async with self._lock:
            if self._current_queued >= self.max_queue:
                raise QueueFullError(
                    f"Queue saturated ({self._current_queued}/{self.max_queue} waiting)"
                )
            self._current_queued += 1
            if self._current_queued > self._peak_queue_length:
                self._peak_queue_length = self._current_queued

        try:
            time_spent_waiting = time.perf_counter() - queued_start
            remaining = max(0.01, deadline - time_spent_waiting)

            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=remaining)
            except asyncio.TimeoutError:
                raise RequestTimeoutError(
                    f"Request timed out in queue after {time.perf_counter() - queued_start:.2f}s"
                )

            acquired_time = time.perf_counter()
            wait_ms = (acquired_time - queued_start) * 1000.0
            return QueueSlot(acquired=True, queue_wait_ms=wait_ms)

        finally:
            async with self._lock:
                self._current_queued -= 1

    def release_slot(self) -> None:
        """Release the concurrency semaphore slot when pipeline execution completes."""
        self._semaphore.release()

    def reset_stats(self) -> None:
        """Reset the peak queue counter for a new load scenario."""
        self._peak_queue_length = 0
