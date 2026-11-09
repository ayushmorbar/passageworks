"""Integration tests for the Stand-in model service."""

import httpx
import pytest

from relay_standin.server import app


@pytest.fixture(autouse=True)
async def reset_standin():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/control/reset")
        await client.post(
            "/control/configure",
            json={
                "base_ttft_ms": 10.0,
                "ttft_jitter_ms": 2.0,
                "token_interval_ms": 1.0,
                "rpm_limit": 30,
                "daily_request_limit": 1000,
                "daily_token_limit": 100000,
                "failure_rate_500": 0.0,
                "timeout_rate": 0.0,
                "halved_limits_active": False,
            },
        )


@pytest.mark.asyncio
async def test_standin_chat_completion_non_streaming():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "user",
                    "content": "What is the Transformer architecture in Attention Is All You Need?",
                }
            ],
            "stream": False,
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        content = data["choices"][0]["message"]["content"]
        assert "Attention Is All You Need" in content
        assert "x-ratelimit-remaining-requests" in resp.headers


@pytest.mark.asyncio
async def test_standin_chat_completion_streaming():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": "Explain Moshi speech model"}],
            "stream": True,
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        lines = resp.text.split("\n")
        data_lines = [
            line for line in lines if line.startswith("data: ") and not line.endswith("[DONE]")
        ]
        assert len(data_lines) > 2


@pytest.mark.asyncio
async def test_standin_rpm_limit():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/control/configure", json={"rpm_limit": 2})

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": "query"}],
            "stream": False,
        }

        # First 2 succeed
        r1 = await client.post("/v1/chat/completions", json=payload)
        assert r1.status_code == 200
        r2 = await client.post("/v1/chat/completions", json=payload)
        assert r2.status_code == 200

        # 3rd breaches RPM limit -> 429
        r3 = await client.post("/v1/chat/completions", json=payload)
        assert r3.status_code == 429
        assert "retry-after" in r3.headers


@pytest.mark.asyncio
async def test_standin_halved_rpm_scenario():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/control/configure",
            json={"rpm_limit": 4, "halved_limits_active": True},  # Effective RPM becomes 2
        )
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": "query"}],
            "stream": False,
        }
        r1 = await client.post("/v1/chat/completions", json=payload)
        assert r1.status_code == 200
        r2 = await client.post("/v1/chat/completions", json=payload)
        assert r2.status_code == 200

        # 3rd breaches effective RPM of 2
        r3 = await client.post("/v1/chat/completions", json=payload)
        assert r3.status_code == 429
