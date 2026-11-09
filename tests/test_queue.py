"""Unit tests for concurrency admission queue and timeouts."""

import asyncio

import pytest

from relay.queue import AdmissionController, QueueFullError, RequestTimeoutError


@pytest.mark.asyncio
async def test_queue_concurrency_slots():
    controller = AdmissionController(max_concurrent=2, max_queue=5, deadline_s=5.0)

    # Acquire 2 slots
    slot1 = await controller.acquire_slot()
    slot2 = await controller.acquire_slot()
    assert slot1.acquired is True
    assert slot2.acquired is True

    # Release slots
    controller.release_slot()
    controller.release_slot()


@pytest.mark.asyncio
async def test_queue_full_rejection():
    # max_queue=1: second waiting caller should be rejected immediately
    controller = AdmissionController(max_concurrent=1, max_queue=1, deadline_s=2.0)

    # First occupies concurrent slot
    _ = await controller.acquire_slot()

    # Second caller joins queue and waits
    async def waiter():
        return await controller.acquire_slot()

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0.02)

    # Third caller breaches max_queue=1 -> QueueFullError
    with pytest.raises(QueueFullError):
        await controller.acquire_slot()

    # Clean up
    controller.release_slot()
    slot2 = await task
    controller.release_slot()
    assert slot2.acquired is True


@pytest.mark.asyncio
async def test_queue_deadline_timeout():
    # deadline=0.05s
    controller = AdmissionController(max_concurrent=1, max_queue=5, deadline_s=0.05)
    _ = await controller.acquire_slot()

    with pytest.raises(RequestTimeoutError):
        await controller.acquire_slot()

    controller.release_slot()
