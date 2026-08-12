from typing import Any

import httpx
import pytest

from astrbot.core.provider.sources.minimax_token_plan_source import (
    _MINIMAX_TOKEN_PLAN_FALLBACK_MODELS,
    ProviderMiniMaxTokenPlan,
)


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class _FakeClient:
    def __init__(
        self,
        response: _FakeResponse | None = None,
        error: httpx.HTTPError | None = None,
    ) -> None:
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, *_args: Any, **_kwargs: Any) -> _FakeResponse:
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def _provider(api_key: str = "") -> ProviderMiniMaxTokenPlan:
    provider = ProviderMiniMaxTokenPlan.__new__(ProviderMiniMaxTokenPlan)
    provider.chosen_api_key = api_key
    return provider


@pytest.mark.asyncio
async def test_get_models_returns_fallback_without_api_key() -> None:
    models = await _provider().get_models()

    assert models == list(_MINIMAX_TOKEN_PLAN_FALLBACK_MODELS)


@pytest.mark.asyncio
async def test_get_models_prefers_discovered_models(monkeypatch) -> None:
    discovered_models = [*list(_MINIMAX_TOKEN_PLAN_FALLBACK_MODELS), "server-model"]
    client = _FakeClient(
        _FakeResponse({"data": [{"id": m} for m in discovered_models]})
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda: client)

    models = await _provider("test-key").get_models()

    assert models == discovered_models


@pytest.mark.asyncio
async def test_get_models_returns_fallback_for_empty_response(monkeypatch) -> None:
    client = _FakeClient(_FakeResponse({"data": []}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: client)

    models = await _provider("test-key").get_models()

    assert models == list(_MINIMAX_TOKEN_PLAN_FALLBACK_MODELS)


@pytest.mark.asyncio
async def test_get_models_returns_fallback_for_request_error(monkeypatch) -> None:
    client = _FakeClient(error=httpx.ConnectError("connection failed"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: client)

    models = await _provider("test-key").get_models()

    assert models == list(_MINIMAX_TOKEN_PLAN_FALLBACK_MODELS)
