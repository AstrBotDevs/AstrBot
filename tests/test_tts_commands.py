"""TTS commands persist a session override without changing the shared profile."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.builtin_stars.builtin_commands.commands import tts as tts_module


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_tts_toggle_is_scoped_to_the_current_session(
    monkeypatch, enabled: bool
) -> None:
    config = {"provider_tts_settings": {"enable": enabled}}
    context = SimpleNamespace(get_config=Mock(return_value=config))
    event = SimpleNamespace(
        unified_msg_origin="test:FriendMessage:alice", set_result=Mock()
    )
    persist = AsyncMock()
    monkeypatch.setattr(tts_module, "update_overrides", persist)
    await tts_module.TTSCommand(context).tts(event)
    context.get_config.assert_called_once_with(umo=event.unified_msg_origin)
    persist.assert_awaited_once_with(
        event.unified_msg_origin, {"provider_tts_settings.enable": not enabled}
    )
    assert config["provider_tts_settings"]["enable"] is enabled
    assert event.set_result.call_args.args[0].chain[0].text


@pytest.mark.asyncio
async def test_tts_does_not_report_success_after_persistence_failure(
    monkeypatch,
) -> None:
    event = SimpleNamespace(
        unified_msg_origin="test:FriendMessage:alice", set_result=Mock()
    )
    context = SimpleNamespace(
        get_config=Mock(return_value={"provider_tts_settings": {"enable": False}})
    )
    monkeypatch.setattr(
        tts_module,
        "update_overrides",
        AsyncMock(side_effect=RuntimeError("storage unavailable")),
    )
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await tts_module.TTSCommand(context).tts(event)
    event.set_result.assert_not_called()
