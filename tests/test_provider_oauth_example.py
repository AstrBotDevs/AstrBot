"""Lifecycle checks for the example, without starting AstrBot or calling a supplier."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.fernet import Fernet

pytestmark = pytest.mark.asyncio


@pytest.fixture
def example(monkeypatch):
    from astrbot.core.star import base

    # Importing a Star subclass registers it; keep the example out of global state.
    monkeypatch.setattr(base, "star_map", {})
    monkeypatch.setattr(base, "star_registry", [])
    from examples.astrbot_plugin_oauth_provider import main

    return main


@pytest.mark.parametrize("failure", [None, "oauth", "first", "second", "unregister", "http", "replacement"])
async def test_cleanup_attempts_all_owned_resources(monkeypatch, failure, example):
    events = []

    def record(name):
        events.append(name)
        if name == failure:
            raise RuntimeError(name)

    async def close_auth():
        record("oauth")
        if failure == "replacement":
            # close() can wait for a refresh while hot reload replaces an instance.
            plugin.context.provider_manager.inst_map["first"] = object()

    async def close_http():
        record("http")

    async def terminate_provider(provider_id):
        record(provider_id)

    def unregister(provider_type, provider_class):
        assert provider_type == example.PROVIDER_TYPE
        assert provider_class is plugin.provider_class
        record("unregister")

    plugin = example.OAuthProviderPlugin.__new__(example.OAuthProviderPlugin)
    plugin.provider_class = type("OwnedProvider", (), {})
    plugin.oauth = SimpleNamespace(close=close_auth)
    plugin.http = SimpleNamespace(aclose=close_http)
    plugin.context = SimpleNamespace(provider_manager=SimpleNamespace(
        inst_map={"first": plugin.provider_class(), "second": plugin.provider_class(), "foreign": object()},
        terminate_provider=terminate_provider,
    ))
    monkeypatch.setattr(example, "unregister_provider_adapter", unregister)

    if failure in {None, "replacement"}:
        await plugin.terminate()
    else:
        with pytest.raises(RuntimeError, match=failure):
            await plugin.terminate()
    expected = ["oauth", "first", "second", "unregister", "http"]
    if failure == "replacement":
        expected.remove("first")
    assert events == expected


async def test_initialization_failure_releases_acquired_resources(monkeypatch, example):
    monkeypatch.setenv("ASTRBOT_OAUTH_STORAGE_KEY", Fernet.generate_key().decode())
    http = SimpleNamespace(aclose=AsyncMock())
    session = SimpleNamespace(close=AsyncMock())
    unregister = Mock()
    monkeypatch.setattr(example.httpx, "AsyncClient", Mock(return_value=http))
    monkeypatch.setattr(example, "OAuth2Session", Mock(return_value=session))
    monkeypatch.setattr(example, "register_provider_adapter", lambda *a, **kw: lambda cls: cls)
    monkeypatch.setattr(example, "unregister_provider_adapter", unregister)
    plugin = example.OAuthProviderPlugin.__new__(example.OAuthProviderPlugin)
    plugin.oauth = plugin.http = plugin.provider_class = None
    plugin.config = dict.fromkeys(
        ("client_id", "authorization_endpoint", "token_endpoint", "redirect_uri", "api_base"),
        "unused-by-session-stub",
    )
    plugin.context = SimpleNamespace(
        provider_manager=SimpleNamespace(inst_map={}),
        register_web_api=Mock(side_effect=ValueError("route registration failed")),
    )

    with pytest.raises(ValueError, match="route registration failed"):
        await plugin.initialize()
    session.close.assert_awaited_once()
    http.aclose.assert_awaited_once()
    unregister.assert_called_once_with(example.PROVIDER_TYPE, plugin.provider_class)
