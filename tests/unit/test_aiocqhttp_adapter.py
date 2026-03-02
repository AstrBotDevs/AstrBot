"""Unit tests for aiocqhttp platform adapter.

Tests cover:
- AiocqhttpAdapter class initialization and methods
- AiocqhttpMessageEvent class and message handling
- Message conversion for different event types
- Group and private message processing

Note: Uses shared mock fixtures from tests/fixtures/mocks/
"""

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 导入共享的辅助函数
from tests.fixtures.helpers import NoopAwaitable, make_platform_config

# 导入共享的 mock fixture
from tests.fixtures.mocks import mock_aiocqhttp_modules  # noqa: F401


def load_module_from_file(module_name: str, file_path: Path):
    """Load a Python module directly from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Get the path to the aiocqhttp source files
AIOCQHTTP_DIR = (
    Path(__file__).parent.parent.parent
    / "astrbot"
    / "core"
    / "platform"
    / "sources"
    / "aiocqhttp"
)


# ============================================================================
# Fixtures (使用 conftest.py 中的 event_queue 和 platform_settings)
# ============================================================================


@pytest.fixture
def platform_config():
    """Create a platform configuration for testing."""
    return make_platform_config("aiocqhttp")


@pytest.fixture
def mock_bot():
    """Create a mock CQHttp bot instance."""
    bot = MagicMock()
    bot.send = AsyncMock()
    bot.call_action = AsyncMock()
    bot.on_request = MagicMock()
    bot.on_notice = MagicMock()
    bot.on_message = MagicMock()
    bot.on_websocket_connection = MagicMock()
    bot.run_task = MagicMock(return_value=NoopAwaitable())
    return bot


@pytest.fixture
def mock_event_group():
    """Create a mock group message event."""
    event = MagicMock()
    event.__getitem__ = lambda self, key: {
        "post_type": "message",
        "message_type": "group",
        "message": [{"type": "text", "data": {"text": "Hello World"}}],
    }.get(key)
    event.self_id = 12345678
    event.user_id = 98765432
    event.group_id = 11111111
    event.message_id = "msg_123"
    event.sender = {"user_id": 98765432, "nickname": "TestUser", "card": ""}
    event.message = [{"type": "text", "data": {"text": "Hello World"}}]
    event.get = lambda key, default=None: {
        "group_name": "TestGroup",
    }.get(key, default)
    return event


@pytest.fixture
def mock_event_private():
    """Create a mock private message event."""
    event = MagicMock()
    event.__getitem__ = lambda self, key: {
        "post_type": "message",
        "message_type": "private",
        "message": [{"type": "text", "data": {"text": "Private Hello"}}],
    }.get(key)
    event.self_id = 12345678
    event.user_id = 98765432
    event.message_id = "msg_456"
    event.sender = {"user_id": 98765432, "nickname": "TestUser"}
    event.message = [{"type": "text", "data": {"text": "Private Hello"}}]
    event.get = lambda key, default=None: None
    return event


@pytest.fixture
def mock_event_notice():
    """Create a mock notice event."""
    event = MagicMock()
    event.__getitem__ = lambda self, key: {
        "post_type": "notice",
        "sub_type": "poke",
        "target_id": 12345678,
    }.get(key)
    event.self_id = 12345678
    event.user_id = 98765432
    event.group_id = 11111111
    event.get = lambda key, default=None: {
        "group_id": 11111111,
        "sub_type": "poke",
        "target_id": 12345678,
    }.get(key, default)
    return event


@pytest.fixture
def mock_event_request():
    """Create a mock request event."""
    event = MagicMock()
    event.__getitem__ = lambda self, key: {"post_type": "request"}.get(key)
    event.self_id = 12345678
    event.user_id = 98765432
    event.group_id = 11111111
    event.get = lambda key, default=None: {"group_id": 11111111}.get(key, default)
    return event


# ============================================================================
# AiocqhttpAdapter Tests
# ============================================================================


class TestAiocqhttpAdapterInit:
    """Tests for AiocqhttpAdapter initialization."""

    def test_init_basic(self, event_queue, platform_config, platform_settings):
        """Test basic adapter initialization."""
        with patch("aiocqhttp.CQHttp"):
            # Import after patching
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            assert adapter.config == platform_config
            assert adapter.settings == platform_settings
            assert adapter.host == platform_config["ws_reverse_host"]
            assert adapter.port == platform_config["ws_reverse_port"]
            assert adapter.metadata.name == "aiocqhttp"
            assert adapter.metadata.id == "test_aiocqhttp"

    def test_init_metadata(self, event_queue, platform_config, platform_settings):
        """Test adapter metadata is correctly set."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            assert adapter.metadata.name == "aiocqhttp"
            assert "OneBot" in adapter.metadata.description
            assert adapter.metadata.support_streaming_message is False


class TestAiocqhttpAdapterConvertMessage:
    """Tests for message conversion."""

    @pytest.mark.asyncio
    async def test_convert_group_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_event_group,
    ):
        """Test converting a group message event."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            result = await adapter._convert_handle_message_event(mock_event_group)

            assert result is not None
            assert result.self_id == "12345678"
            assert result.sender.user_id == "98765432"
            assert result.message_str == "Hello World"
            assert len(result.message) == 1

    @pytest.mark.asyncio
    async def test_convert_private_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_event_private,
    ):
        """Test converting a private message event."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.message_type import MessageType
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            result = await adapter._convert_handle_message_event(mock_event_private)

            assert result is not None
            assert result.type == MessageType.FRIEND_MESSAGE
            assert result.sender.user_id == "98765432"

    @pytest.mark.asyncio
    async def test_convert_notice_event(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_event_notice,
    ):
        """Test converting a notice event."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            result = await adapter._convert_handle_notice_event(mock_event_notice)

            assert result is not None
            assert result.raw_message == mock_event_notice

    @pytest.mark.asyncio
    async def test_convert_request_event(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_event_request,
    ):
        """Test converting a request event."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            result = await adapter._convert_handle_request_event(mock_event_request)

            assert result is not None
            assert result.raw_message == mock_event_request

    @pytest.mark.asyncio
    async def test_convert_message_invalid_format(
        self, event_queue, platform_config, platform_settings
    ):
        """Test converting a message with invalid format raises error."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            # Create event with non-list message
            event = MagicMock()
            event.self_id = 12345678
            event.user_id = 98765432
            event.group_id = 11111111
            event.message_id = "msg_123"
            event.sender = {"user_id": 98765432, "nickname": "TestUser"}
            event.message = "not a list"  # Invalid format
            event.__getitem__ = lambda self, key: {
                "message_type": "group",
            }.get(key)
            event.get = lambda key, default=None: None

            with pytest.raises(ValueError) as exc_info:
                await adapter._convert_handle_message_event(event)

            assert "无法识别的消息类型" in str(exc_info.value)


class TestAiocqhttpAdapterMessageComponents:
    """Tests for different message component types."""

    @pytest.mark.asyncio
    async def test_convert_at_message(
        self, event_queue, platform_config, platform_settings
    ):
        """Test converting a message with @ mention."""
        with patch("aiocqhttp.CQHttp") as mock_cqhttp:
            mock_bot_instance = MagicMock()
            mock_bot_instance.call_action = AsyncMock(
                return_value={"card": "AtUser", "nickname": "AtUserNick"}
            )
            mock_cqhttp.return_value = mock_bot_instance

            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            event = MagicMock()
            event.self_id = 12345678
            event.user_id = 98765432
            event.group_id = 11111111
            event.message_id = "msg_123"
            event.sender = {"user_id": 98765432, "nickname": "TestUser", "card": ""}
            event.message = [
                {"type": "at", "data": {"qq": "88888888"}},
                {"type": "text", "data": {"text": "Hello"}},
            ]
            event.__getitem__ = lambda self, key: {
                "message_type": "group",
            }.get(key)
            event.get = lambda key, default=None: None

            result = await adapter._convert_handle_message_event(event)

            assert result is not None
            # Should have At component and text
            assert len(result.message) >= 1

    @pytest.mark.asyncio
    async def test_convert_image_message(
        self, event_queue, platform_config, platform_settings
    ):
        """Test converting a message with image."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            event = MagicMock()
            event.self_id = 12345678
            event.user_id = 98765432
            event.group_id = 11111111
            event.message_id = "msg_123"
            event.sender = {"user_id": 98765432, "nickname": "TestUser"}
            event.message = [
                {"type": "image", "data": {"url": "http://example.com/image.jpg"}},
            ]
            event.__getitem__ = lambda self, key: {
                "message_type": "group",
            }.get(key)
            event.get = lambda key, default=None: None

            result = await adapter._convert_handle_message_event(event)

            assert result is not None
            assert len(result.message) == 1

    @pytest.mark.asyncio
    async def test_convert_empty_text_skipped(
        self, event_queue, platform_config, platform_settings
    ):
        """Test that empty text segments are skipped."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            event = MagicMock()
            event.self_id = 12345678
            event.user_id = 98765432
            event.group_id = 11111111
            event.message_id = "msg_123"
            event.sender = {"user_id": 98765432, "nickname": "TestUser"}
            event.message = [
                {"type": "text", "data": {"text": "   "}},  # Empty/whitespace only
                {"type": "text", "data": {"text": "Hello"}},
            ]
            event.__getitem__ = lambda self, key: {
                "message_type": "group",
            }.get(key)
            event.get = lambda key, default=None: None

            result = await adapter._convert_handle_message_event(event)

            assert result is not None
            assert result.message_str == "Hello"


class TestAiocqhttpAdapterRun:
    """Tests for run method."""

    def test_run_with_config(self, event_queue, platform_config, platform_settings):
        """Test run method with configured host and port."""
        mock_bot_instance = MagicMock()
        mock_bot_instance.run_task = MagicMock(return_value=NoopAwaitable())

        with patch("aiocqhttp.CQHttp", return_value=mock_bot_instance):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            result = adapter.run()

            assert result is not None
            mock_bot_instance.run_task.assert_called_once()

    def test_run_with_default_values(self, event_queue, platform_settings):
        """Test run method uses default values when not configured."""
        mock_bot_instance = MagicMock()
        mock_bot_instance.run_task = MagicMock(return_value=NoopAwaitable())

        with patch("aiocqhttp.CQHttp", return_value=mock_bot_instance):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            config = {"id": "test", "ws_reverse_host": None, "ws_reverse_port": None}
            adapter = AiocqhttpAdapter(config, platform_settings, event_queue)

            adapter.run()

            assert adapter.host == "0.0.0.0"
            assert adapter.port == 6199


class TestAiocqhttpAdapterTerminate:
    """Tests for terminate method."""

    @pytest.mark.asyncio
    async def test_terminate_sets_shutdown_event(
        self, event_queue, platform_config, platform_settings
    ):
        """Test terminate method sets shutdown event."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)
            adapter.shutdown_event = asyncio.Event()

            await adapter.terminate()

            assert adapter.shutdown_event.is_set()


class TestAiocqhttpAdapterHandleMsg:
    """Tests for handle_msg method."""

    @pytest.mark.asyncio
    async def test_handle_msg_creates_event(
        self, event_queue, platform_config, platform_settings
    ):
        """Test handle_msg creates AiocqhttpMessageEvent and commits it."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.astrbot_message import AstrBotMessage
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )
            from astrbot.core.platform import MessageType

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            message = AstrBotMessage()
            message.type = MessageType.FRIEND_MESSAGE
            message.message_str = "Test message"
            message.session_id = "test_session"

            await adapter.handle_msg(message)

            # Check that event was committed to queue
            assert event_queue.qsize() == 1


class TestAiocqhttpAdapterMeta:
    """Tests for meta method."""

    def test_meta_returns_metadata(
        self, event_queue, platform_config, platform_settings
    ):
        """Test meta method returns PlatformMetadata."""
        with patch("aiocqhttp.CQHttp"):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            meta = adapter.meta()

            assert meta.name == "aiocqhttp"
            assert meta.id == "test_aiocqhttp"


class TestAiocqhttpAdapterGetClient:
    """Tests for get_client method."""

    def test_get_client_returns_bot(
        self, event_queue, platform_config, platform_settings
    ):
        """Test get_client returns the bot instance."""
        mock_bot_instance = MagicMock()

        with patch("aiocqhttp.CQHttp", return_value=mock_bot_instance):
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )

            adapter = AiocqhttpAdapter(platform_config, platform_settings, event_queue)

            result = adapter.get_client()

            assert result == mock_bot_instance


# ============================================================================
# AiocqhttpMessageEvent Tests
# ============================================================================


class TestAiocqhttpMessageEventInit:
    """Tests for AiocqhttpMessageEvent initialization."""

    def test_init_basic(self):
        """Test basic event initialization."""
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        message_obj = MagicMock()
        message_obj.raw_message = None
        platform_meta = MagicMock()
        bot = MagicMock()

        event = AiocqhttpMessageEvent(
            message_str="Test message",
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id="test_session",
            bot=bot,
        )

        assert event.message_str == "Test message"
        assert event.bot == bot
        assert event.session_id == "test_session"


class TestAiocqhttpMessageEventFromSegmentToDict:
    """Tests for _from_segment_to_dict method."""

    @pytest.mark.asyncio
    async def test_from_segment_plain(self):
        """Test converting Plain segment to dict."""
        from astrbot.core.message.components import Plain
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        plain = Plain(text="Hello")
        result = await AiocqhttpMessageEvent._from_segment_to_dict(plain)

        # Plain component type is "text" in toDict()
        assert result["type"] == "text"
        assert result["data"]["text"] == "Hello"


class TestAiocqhttpMessageEventParseOnebotJson:
    """Tests for _parse_onebot_json method."""

    @pytest.mark.asyncio
    async def test_parse_empty_chain(self):
        """Test parsing empty message chain."""
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        chain = MessageChain(chain=[])
        result = await AiocqhttpMessageEvent._parse_onebot_json(chain)

        assert result == []

    @pytest.mark.asyncio
    async def test_parse_plain_text(self):
        """Test parsing plain text message chain."""
        from astrbot.core.message.components import Plain
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        chain = MessageChain(chain=[Plain(text="Hello World")])
        result = await AiocqhttpMessageEvent._parse_onebot_json(chain)

        assert len(result) == 1
        # Plain component type is "text" in toDict()
        assert result[0]["type"] == "text"


class TestAiocqhttpMessageEventSend:
    """Tests for send method."""

    @pytest.mark.asyncio
    async def test_send_group_message(self):
        """Test sending group message."""
        from astrbot.core.message.components import Plain
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        bot = MagicMock()
        bot.send_group_msg = AsyncMock()

        message_obj = MagicMock()
        message_obj.raw_message = None
        message_obj.group = MagicMock()
        message_obj.group.group_id = "11111111"

        platform_meta = MagicMock()

        event = AiocqhttpMessageEvent(
            message_str="Test",
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id="11111111",
            bot=bot,
        )

        # Mock get_group_id to return group_id
        event.get_group_id = MagicMock(return_value="11111111")
        event.get_sender_id = MagicMock(return_value="98765432")

        with patch.object(
            AiocqhttpMessageEvent,
            "send_message",
            new_callable=AsyncMock,
        ) as mock_send:
            with patch(
                "astrbot.core.platform.astr_message_event.AstrMessageEvent.send",
                new_callable=AsyncMock,
            ):
                chain = MessageChain(chain=[Plain(text="Hello")])
                await event.send(chain)

                mock_send.assert_called_once()


class TestAiocqhttpMessageEventDispatchSend:
    """Tests for _dispatch_send method."""

    @pytest.mark.asyncio
    async def test_dispatch_send_group(self):
        """Test dispatching send to group."""
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        bot = MagicMock()
        bot.send_group_msg = AsyncMock()

        await AiocqhttpMessageEvent._dispatch_send(
            bot=bot,
            event=None,
            is_group=True,
            session_id="11111111",
            messages=[{"type": "text", "data": {"text": "Hello"}}],
        )

        bot.send_group_msg.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_send_private(self):
        """Test dispatching send to private chat."""
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        bot = MagicMock()
        bot.send_private_msg = AsyncMock()

        await AiocqhttpMessageEvent._dispatch_send(
            bot=bot,
            event=None,
            is_group=False,
            session_id="98765432",
            messages=[{"type": "text", "data": {"text": "Hello"}}],
        )

        bot.send_private_msg.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_send_invalid_session(self):
        """Test dispatching send with invalid session raises error."""
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        bot = MagicMock()

        with pytest.raises(ValueError) as exc_info:
            await AiocqhttpMessageEvent._dispatch_send(
                bot=bot,
                event=None,
                is_group=True,
                session_id="invalid",
                messages=[{"type": "text", "data": {"text": "Hello"}}],
            )

        assert "无法发送消息" in str(exc_info.value)


class TestAiocqhttpMessageEventGetGroup:
    """Tests for get_group method."""

    @pytest.mark.asyncio
    async def test_get_group_success(self):
        """Test getting group info successfully."""
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        bot = MagicMock()
        bot.call_action = AsyncMock(
            side_effect=[
                {"group_name": "TestGroup"},  # get_group_info
                [  # get_group_member_list
                    {"user_id": "111", "role": "owner", "nickname": "Owner"},
                    {"user_id": "222", "role": "admin", "nickname": "Admin1"},
                    {"user_id": "333", "role": "member", "nickname": "Member1"},
                ],
            ]
        )

        message_obj = MagicMock()
        message_obj.raw_message = None
        platform_meta = MagicMock()

        event = AiocqhttpMessageEvent(
            message_str="Test",
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id="11111111",
            bot=bot,
        )

        group = await event.get_group(group_id="11111111")

        assert group is not None
        assert group.group_id == "11111111"
        assert group.group_name == "TestGroup"
        assert group.group_owner == "111"
        assert group.group_admins is not None
        assert "222" in group.group_admins

    @pytest.mark.asyncio
    async def test_get_group_no_group_id(self):
        """Test get_group returns None when no group_id available."""
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        bot = MagicMock()
        bot.call_action = AsyncMock()

        message_obj = MagicMock()
        message_obj.raw_message = None
        platform_meta = MagicMock()

        event = AiocqhttpMessageEvent(
            message_str="Test",
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id="private_session",
            bot=bot,
        )

        # Mock get_group_id to return None
        event.get_group_id = MagicMock(return_value=None)

        result = await event.get_group()

        assert result is None


class TestAiocqhttpMessageEventSendStreaming:
    """Tests for send_streaming method."""

    @pytest.mark.asyncio
    async def test_send_streaming_without_fallback(self):
        """Test streaming send without fallback mode."""
        from astrbot.core.message.components import Plain
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
            AiocqhttpMessageEvent,
        )

        bot = MagicMock()

        message_obj = MagicMock()
        message_obj.raw_message = None
        platform_meta = MagicMock()

        event = AiocqhttpMessageEvent(
            message_str="Test",
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id="test_session",
            bot=bot,
        )

        async def mock_generator():
            yield MessageChain(chain=[Plain(text="Hello")])
            yield MessageChain(chain=[Plain(text=" World")])

        with patch.object(event, "send", new_callable=AsyncMock) as mock_send:
            with patch(
                "astrbot.core.platform.astr_message_event.AstrMessageEvent.send_streaming",
                new_callable=AsyncMock,
            ):
                await event.send_streaming(mock_generator(), use_fallback=False)

                # Should call send with combined message
                mock_send.assert_called()
