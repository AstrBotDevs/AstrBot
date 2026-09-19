import asyncio
import json

import pytest

import astrbot.api  # noqa: F401
from astrbot.core.provider.sources.azure_tts_source import (
    AzureNativeProvider,
    AzureTTSProvider,
    OTTSProvider,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["native", "otts"])
@pytest.mark.parametrize("outcome", ["success", "error", "cancel"])
async def test_overlapping_synthesis_keeps_clients_alive_and_closes_them(
    monkeypatch, backend, outcome
):
    key = "A" * 32
    if backend == "otts":
        key = (
            "other["
            + json.dumps(
                {
                    "OTTS_SKEY": "dummy",
                    "OTTS_URL": "https://example.com/tts",
                    "OTTS_AUTH_TIME": "https://example.com/time",
                }
            )
            + "]"
        )
    provider = AzureTTSProvider({"azure_tts_subscription_key": key}, {})
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    clients = []

    async def synthesize(instance, text, *args):
        client = instance.client
        clients.append(client)
        if text == "first":
            first_started.set()
            await release_first.wait()
            if outcome == "error":
                raise ValueError("synthesis failed")
        assert instance.client is client
        assert not client.is_closed
        return text

    monkeypatch.setattr(
        AzureNativeProvider if backend == "native" else OTTSProvider,
        "get_audio",
        synthesize,
    )
    first = asyncio.create_task(provider.get_audio("first"))
    await asyncio.wait_for(first_started.wait(), timeout=5)
    second = asyncio.create_task(provider.get_audio("second"))
    await asyncio.sleep(0)
    if outcome == "cancel":
        first.cancel()
    release_first.set()
    try:
        results = await asyncio.wait_for(
            asyncio.gather(first, second, return_exceptions=True), timeout=5
        )
        assert results[1] == "second"
        if outcome == "success":
            assert results[0] == "first"
        elif outcome == "error":
            assert isinstance(results[0], ValueError)
        else:
            assert isinstance(results[0], asyncio.CancelledError)
        assert len(clients) == 2
        assert clients[0] is not clients[1]
        assert all(client.is_closed for client in clients)
    finally:
        for client in clients:
            await client.aclose()
