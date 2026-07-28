from typing import Any
from unittest.mock import patch

import httpx
import pytest

import astrbot.core.provider.sources.anthropic_source as anthropic_source
from astrbot.core.provider.sources.minimax_token_plan_source import (
    ProviderMiniMaxTokenPlan,
)


class _FakeAsyncAnthropic:
    """Minimal AsyncAnthropic stand-in for provider construction in tests."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def close(self) -> None:
        return None


def _make_provider(monkeypatch, key=None):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)
    provider_config: dict[str, Any] = {
        "id": "minimax-token-plan-test",
        "type": "minimax_token_plan",
    }
    if key is not None:
        provider_config["key"] = key
    return ProviderMiniMaxTokenPlan(
        provider_config=provider_config, provider_settings={}
    )


@pytest.mark.asyncio
async def test_get_models_returns_fallback_when_no_api_key(monkeypatch):
    provider = _make_provider(monkeypatch, key=[""])
    models = await provider.get_models()
    assert models == ["MiniMax-M3", "MiniMax-M2.7"]


@pytest.mark.asyncio
async def test_get_models_returns_dynamic_list_when_available(monkeypatch):
    provider = _make_provider(monkeypatch, key=["test-key"])
    payload = {
        "data": [{"id": "MiniMax-M3"}, {"id": "MiniMax-M2.7"}, {"id": "MiniMax-M2"}]
    }

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, headers=None, timeout=None):
            return _FakeResponse()

    with patch(
        "astrbot.core.provider.sources.minimax_token_plan_source.httpx.AsyncClient",
        return_value=_FakeClient(),
    ):
        models = await provider.get_models()

    assert models == ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2"]


@pytest.mark.asyncio
async def test_get_models_returns_fallback_on_empty_dynamic_list(monkeypatch):
    provider = _make_provider(monkeypatch, key=["test-key"])

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": []}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, headers=None, timeout=None):
            return _FakeResponse()

    with patch(
        "astrbot.core.provider.sources.minimax_token_plan_source.httpx.AsyncClient",
        return_value=_FakeClient(),
    ):
        models = await provider.get_models()

    assert models == ["MiniMax-M3", "MiniMax-M2.7"]


@pytest.mark.asyncio
async def test_get_models_returns_fallback_on_fetch_error(monkeypatch):
    provider = _make_provider(monkeypatch, key=["test-key"])

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, headers=None, timeout=None):
            raise httpx.ConnectError("connection refused")

    with patch(
        "astrbot.core.provider.sources.minimax_token_plan_source.httpx.AsyncClient",
        return_value=_FakeClient(),
    ):
        models = await provider.get_models()

    assert models == ["MiniMax-M3", "MiniMax-M2.7"]
