from types import SimpleNamespace

import pytest

from astrbot.core.provider.entities import ProviderType
from astrbot.dashboard.routes.chat import ChatRoute


class _ProviderManager:
    def __init__(self, provider):
        self.provider = provider
        self.calls = []

    def get_using_provider(self, provider_type, umo=None):
        self.calls.append((provider_type, umo))
        return self.provider


def _make_route(
    *,
    tts_enabled: bool = True,
    provider=object(),
    trigger_probability=1,
) -> ChatRoute:
    route = ChatRoute.__new__(ChatRoute)
    route.core_lifecycle = SimpleNamespace(
        astrbot_config={
            "provider_tts_settings": {
                "enable": tts_enabled,
                "trigger_probability": trigger_probability,
            }
        },
        provider_manager=_ProviderManager(provider),
    )
    return route


def _allow_session_tts(monkeypatch, *, enabled: bool = True):
    seen = {}

    async def fake_is_tts_enabled(umo: str) -> bool:
        seen["umo"] = umo
        return enabled

    monkeypatch.setattr(
        "astrbot.dashboard.routes.chat.SessionServiceManager.is_tts_enabled_for_session",
        fake_is_tts_enabled,
    )
    return seen


def test_build_webchat_umo_matches_adapter_session_id():
    route = _make_route()

    assert (
        route._build_webchat_umo("astrbot", "session-1")
        == "webchat:FriendMessage:webchat!astrbot!session-1"
    )


def test_thread_umo_reuses_webchat_umo_builder():
    route = _make_route()

    assert route._build_thread_unified_msg_origin(
        "astrbot", "thread-1"
    ) == route._build_webchat_umo("astrbot", "thread-1")


@pytest.mark.asyncio
async def test_webchat_tts_enabled_disables_streaming(monkeypatch):
    route = _make_route()
    seen = _allow_session_tts(monkeypatch)

    enabled, reason = await route._resolve_webchat_tts("astrbot", "session-1")

    assert (enabled, reason) == (True, None)
    assert seen["umo"] == "webchat:FriendMessage:webchat!astrbot!session-1"
    assert route.core_lifecycle.provider_manager.calls == [
        (
            ProviderType.TEXT_TO_SPEECH,
            "webchat:FriendMessage:webchat!astrbot!session-1",
        )
    ]


@pytest.mark.asyncio
async def test_webchat_tts_disabled_keeps_streaming(monkeypatch):
    route = _make_route(tts_enabled=False)

    async def fail_if_called(_umo: str) -> bool:
        raise AssertionError("session TTS check should not run")

    monkeypatch.setattr(
        "astrbot.dashboard.routes.chat.SessionServiceManager.is_tts_enabled_for_session",
        fail_if_called,
    )

    enabled, reason = await route._resolve_webchat_tts("astrbot", "session-1")

    assert (enabled, reason) == (False, "globally_disabled")
    assert route.core_lifecycle.provider_manager.calls == []


@pytest.mark.asyncio
async def test_webchat_tts_zero_trigger_probability_treated_as_disabled(monkeypatch):
    route = _make_route(trigger_probability=0)

    async def fail_if_called(_umo: str) -> bool:
        raise AssertionError("session TTS check should not run")

    monkeypatch.setattr(
        "astrbot.dashboard.routes.chat.SessionServiceManager.is_tts_enabled_for_session",
        fail_if_called,
    )

    enabled, reason = await route._resolve_webchat_tts("astrbot", "session-1")

    assert (enabled, reason) == (False, "globally_disabled")
    assert route.core_lifecycle.provider_manager.calls == []


@pytest.mark.asyncio
async def test_webchat_tts_session_disabled(monkeypatch):
    route = _make_route()
    _allow_session_tts(monkeypatch, enabled=False)

    enabled, reason = await route._resolve_webchat_tts("astrbot", "session-1")

    assert (enabled, reason) == (False, "session_disabled")
    assert route.core_lifecycle.provider_manager.calls == []


@pytest.mark.asyncio
async def test_webchat_tts_no_provider(monkeypatch):
    route = _make_route(provider=None)
    _allow_session_tts(monkeypatch)

    enabled, reason = await route._resolve_webchat_tts("astrbot", "session-1")

    assert (enabled, reason) == (False, "no_provider")
