from types import SimpleNamespace

import pytest

from astrbot.core.streaming_override import (
    STREAMING_OVERRIDE_KEY,
    resolve_streaming_response,
)


class _FakeEvent:
    def __init__(self, umo="webchat:friend:1:bot", extra=None) -> None:
        self.unified_msg_origin = umo
        self._extra = dict(extra or {})

    def get_extra(self, key, default=None):
        return self._extra.get(key, default)

    def set_extra(self, key, value) -> None:
        self._extra[key] = value


class _FakePreferences:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], object] = {}

    async def session_get(self, umo, key, default=None):
        return self.values.get((umo, key), default)

    async def session_put(self, umo, key, value) -> None:
        self.values[(umo, key)] = value

    async def session_remove(self, umo, key) -> None:
        self.values.pop((umo, key), None)

    async def streaming_override(self, umo: str):
        value = await self.session_get(umo, STREAMING_OVERRIDE_KEY, None)
        if value is None:
            return None
        return bool(value)

    async def set_streaming_override(self, umo: str, enabled: bool) -> None:
        await self.session_put(umo, STREAMING_OVERRIDE_KEY, enabled)

    async def clear_streaming_override(self, umo: str) -> None:
        await self.session_remove(umo, STREAMING_OVERRIDE_KEY)


@pytest.mark.asyncio
async def test_unset_follows_global() -> None:
    event = _FakeEvent()
    prefs = _FakePreferences()
    config = {"provider_settings": {"streaming_response": True}}
    assert await resolve_streaming_response(event, config, prefs) is True


@pytest.mark.asyncio
async def test_session_on() -> None:
    event = _FakeEvent()
    prefs = _FakePreferences()
    await prefs.session_put(event.unified_msg_origin, STREAMING_OVERRIDE_KEY, True)
    config = {"provider_settings": {"streaming_response": False}}
    assert await resolve_streaming_response(event, config, prefs) is True


@pytest.mark.asyncio
async def test_session_off() -> None:
    event = _FakeEvent()
    prefs = _FakePreferences()
    await prefs.session_put(event.unified_msg_origin, STREAMING_OVERRIDE_KEY, False)
    config = {"provider_settings": {"streaming_response": True}}
    assert await resolve_streaming_response(event, config, prefs) is False


@pytest.mark.asyncio
async def test_session_unset_follows_changed_global() -> None:
    event = _FakeEvent()
    prefs = _FakePreferences()
    await prefs.session_put(event.unified_msg_origin, STREAMING_OVERRIDE_KEY, True)
    await prefs.session_remove(event.unified_msg_origin, STREAMING_OVERRIDE_KEY)
    config = {"provider_settings": {"streaming_response": False}}
    assert await resolve_streaming_response(event, config, prefs) is False


@pytest.mark.asyncio
async def test_event_extra_overrides_session() -> None:
    event = _FakeEvent(extra={"enable_streaming": True})
    prefs = _FakePreferences()
    await prefs.session_put(event.unified_msg_origin, STREAMING_OVERRIDE_KEY, False)
    config = {"provider_settings": {"streaming_response": False}}
    assert await resolve_streaming_response(event, config, prefs) is True


@pytest.mark.asyncio
async def test_running_request_is_not_changed_mid_flight() -> None:
    event = _FakeEvent()
    prefs = _FakePreferences()
    config = {"provider_settings": {"streaming_response": False}}
    first = await resolve_streaming_response(event, config, prefs)
    await prefs.session_put(event.unified_msg_origin, STREAMING_OVERRIDE_KEY, True)
    second = await resolve_streaming_response(event, config, prefs)
    assert first is False
    assert second is False


@pytest.mark.asyncio
async def test_webchat_and_im_share_resolver() -> None:
    prefs = _FakePreferences()
    config = {"provider_settings": {"streaming_response": False}}
    await prefs.session_put("webchat:friend:1:bot", STREAMING_OVERRIDE_KEY, True)
    await prefs.session_put("telegram:group:2:bot", STREAMING_OVERRIDE_KEY, True)
    web = await resolve_streaming_response(
        _FakeEvent("webchat:friend:1:bot"), config, prefs
    )
    im = await resolve_streaming_response(
        _FakeEvent("telegram:group:2:bot"), config, prefs
    )
    assert web is True
    assert im is True


@pytest.mark.asyncio
async def test_flow_command_writes_and_removes_override() -> None:
    from astrbot.builtin_stars.builtin_commands.commands.flow import FlowCommands

    prefs = _FakePreferences()
    from tests.unit.builtin_command_fakes import FakeI18n

    context = SimpleNamespace(
        preferences=prefs,
        config=SimpleNamespace(
            get=lambda umo=None: {"provider_settings": {"streaming_response": False}}
        ),
        i18n=FakeI18n(),
    )
    commands = FlowCommands(context)
    event = _FakeEvent()
    event.set_result = lambda result: setattr(event, "result", result)
    await commands.set_override(event, True)
    assert prefs.values[(event.unified_msg_origin, STREAMING_OVERRIDE_KEY)] is True
    await commands.set_override(event, False)
    assert prefs.values[(event.unified_msg_origin, STREAMING_OVERRIDE_KEY)] is False
    await commands.unset(event)
    assert (event.unified_msg_origin, STREAMING_OVERRIDE_KEY) not in prefs.values
