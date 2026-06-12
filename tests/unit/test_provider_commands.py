import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from astrbot.builtin_stars.builtin_commands.commands.provider import ProviderCommands
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.provider.entities import ProviderType

@pytest.mark.asyncio
async def test_provider_reset_chat_completion():
    context = MagicMock()
    cmd = ProviderCommands(context)
    event = MagicMock(spec=AstrMessageEvent)
    event.unified_msg_origin = "session-123"

    with patch("astrbot.builtin_stars.builtin_commands.commands.provider.sp.session_remove", new_callable=AsyncMock) as mock_remove:
        await cmd.provider(event, idx="reset")
        mock_remove.assert_called_once_with(
            "session-123",
            f"provider_perf_{ProviderType.CHAT_COMPLETION.value}",
        )
        event.set_result.assert_called_once()
        res = event.set_result.call_args[0][0]
        assert "reset Chat Completion provider" in res.get_plain_text()

@pytest.mark.asyncio
async def test_provider_reset_tts():
    context = MagicMock()
    cmd = ProviderCommands(context)
    event = MagicMock(spec=AstrMessageEvent)
    event.unified_msg_origin = "session-123"

    with patch("astrbot.builtin_stars.builtin_commands.commands.provider.sp.session_remove", new_callable=AsyncMock) as mock_remove:
        await cmd.provider(event, idx="tts", idx2="reset")
        mock_remove.assert_called_once_with(
            "session-123",
            f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}",
        )
        event.set_result.assert_called_once()
        res = event.set_result.call_args[0][0]
        assert "reset TTS provider" in res.get_plain_text()

@pytest.mark.asyncio
async def test_provider_reset_stt():
    context = MagicMock()
    cmd = ProviderCommands(context)
    event = MagicMock(spec=AstrMessageEvent)
    event.unified_msg_origin = "session-123"

    with patch("astrbot.builtin_stars.builtin_commands.commands.provider.sp.session_remove", new_callable=AsyncMock) as mock_remove:
        await cmd.provider(event, idx="stt", idx2="reset")
        mock_remove.assert_called_once_with(
            "session-123",
            f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}",
        )
        event.set_result.assert_called_once()
        res = event.set_result.call_args[0][0]
        assert "reset STT provider" in res.get_plain_text()
