from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.pipeline.pre_ack_emoji import EmojiRef, PreAckEmojiManager


def _make_config(platform: str, enable: bool = True, emojis: list | None = None, auto_remove: bool = True) -> dict:
    """构造包含 platform_specific 的最小配置字典"""
    if emojis is None:
        emojis = ["👍"]
    return {
        "platform_specific": {
            platform: {
                "pre_ack_emoji": {
                    "enable": enable,
                    "emojis": emojis,
                    "auto_remove": auto_remove,
                }
            }
        }
    }


def _make_event(platform: str = "telegram", is_wake: bool = True) -> MagicMock:
    """构造模拟的 AstrMessageEvent"""
    event = MagicMock()
    event.get_platform_name.return_value = platform
    event.is_at_or_wake_command = is_wake
    event.react = AsyncMock(return_value=None)
    event.remove_react = AsyncMock()
    return event


class TestPreAckEmojiAddEmoji:
    """测试贴表情逻辑"""

    @pytest.mark.asyncio
    async def test_disabled_does_not_react(self):
        """功能关闭时不贴表情"""
        cfg = _make_config("telegram", enable=False)
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("telegram")
        result = await mgr.add_emoji(event)
        assert result is None
        event.react.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_emojis_does_not_react(self):
        """emojis 列表为空时不贴表情"""
        cfg = _make_config("telegram", emojis=[])
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("telegram")
        result = await mgr.add_emoji(event)
        assert result is None
        event.react.assert_not_called()

    @pytest.mark.asyncio
    async def test_unsupported_platform_does_not_react(self):
        """非支持平台不贴表情"""
        cfg = _make_config("aiocqhttp", enable=True)
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("aiocqhttp")
        result = await mgr.add_emoji(event)
        assert result is None
        event.react.assert_not_called()

    @pytest.mark.asyncio
    async def test_emoji_chosen_from_config_list(self):
        """选出的 emoji 在配置列表内"""
        emojis = ["👍", "✍️", "🤔"]
        cfg = _make_config("telegram", emojis=emojis)
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("telegram")
        result = await mgr.add_emoji(event)
        assert result is not None
        assert result.emoji in emojis
        event.react.assert_called_once_with(result.emoji)

    @pytest.mark.asyncio
    async def test_react_failure_returns_none(self):
        """贴表情失败时返回 None，不影响主流程"""
        cfg = _make_config("telegram")
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("telegram")
        event.react.side_effect = Exception("API error")
        result = await mgr.add_emoji(event)
        assert result is None

    @pytest.mark.asyncio
    async def test_all_three_platforms_supported(self):
        """telegram、lark、discord 三个平台都支持"""
        for platform in ("telegram", "lark", "discord"):
            cfg = _make_config(platform)
            mgr = PreAckEmojiManager(cfg)
            event = _make_event(platform)
            result = await mgr.add_emoji(event)
            assert result is not None
            assert result.emoji == "👍"
            event.react.assert_called_once_with("👍")

    @pytest.mark.asyncio
    async def test_lark_reaction_id_stored_in_ref(self):
        """飞书平台 react 返回的 reaction_id 保存在 EmojiRef 中"""
        cfg = _make_config("lark")
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("lark")
        event.react.return_value = "lark_reaction_123"
        result = await mgr.add_emoji(event)
        assert result is not None
        assert result.reaction_id == "lark_reaction_123"


class TestPreAckEmojiRemoveEmoji:
    """测试撤回表情逻辑"""

    @pytest.mark.asyncio
    async def test_auto_remove_true_calls_remove_react(self):
        """auto_remove=True 时撤回"""
        cfg = _make_config("telegram", auto_remove=True)
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("telegram")
        ref = EmojiRef(emoji="👍")
        await mgr.remove_emoji(event, ref)
        event.remove_react.assert_called_once_with("👍", reaction_id=None)

    @pytest.mark.asyncio
    async def test_auto_remove_false_does_not_remove(self):
        """auto_remove=False 时不撤回"""
        cfg = _make_config("telegram", auto_remove=False)
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("telegram")
        ref = EmojiRef(emoji="👍")
        await mgr.remove_emoji(event, ref)
        event.remove_react.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_ref_skips_removal(self):
        """ref 为 None 时跳过撤回"""
        cfg = _make_config("telegram")
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("telegram")
        await mgr.remove_emoji(event, None)
        event.remove_react.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_failure_logs_warning(self):
        """撤回失败时记录 warning 日志"""
        cfg = _make_config("telegram")
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("telegram")
        ref = EmojiRef(emoji="👍")
        event.remove_react.side_effect = Exception("API error")
        with patch("astrbot.core.pipeline.pre_ack_emoji.logger") as mock_logger:
            await mgr.remove_emoji(event, ref)
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_lark_reaction_id_passed_to_remove_react(self):
        """飞书平台撤回时传递 reaction_id"""
        cfg = _make_config("lark", auto_remove=True)
        mgr = PreAckEmojiManager(cfg)
        event = _make_event("lark")
        ref = EmojiRef(emoji="Typing", reaction_id="lark_reaction_123")
        await mgr.remove_emoji(event, ref)
        event.remove_react.assert_called_once_with("Typing", reaction_id="lark_reaction_123")
