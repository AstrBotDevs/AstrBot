"""socket_handler 跨会话浏览 action 单元测试

测试 SocketClientHandler 中的 _list_sessions、_list_session_conversations、
_get_session_history 三个方法。使用 mock 替代真实的 ConversationManager。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_handler():
    """创建最小化的 SocketClientHandler 用于测试"""
    from astrbot.core.platform.sources.cli.socket_handler import (
        SocketClientHandler,
    )

    handler = SocketClientHandler(
        token_manager=MagicMock(),
        message_converter=MagicMock(),
        session_manager=MagicMock(),
        platform_meta=MagicMock(),
        output_queue=MagicMock(),
        event_committer=MagicMock(),
    )
    return handler


class TestListSessions:
    """_list_sessions 方法测试"""

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_list_sessions_success(self, mock_get_mgr):
        handler = _make_handler()
        mock_mgr = MagicMock()
        mock_mgr.db.get_session_conversations = AsyncMock(
            return_value=(
                [
                    {
                        "session_id": "cli:FriendMessage:cli_session",
                        "conversation_id": "conv-1",
                        "title": "测试",
                        "persona_id": None,
                        "persona_name": None,
                    }
                ],
                1,
            )
        )
        mock_get_mgr.return_value = mock_mgr

        result = await handler._list_sessions({"page": 1, "page_size": 20}, "req-1")
        data = json.loads(result)

        assert data["status"] == "success"
        assert len(data["sessions"]) == 1
        assert data["total"] == 1
        assert data["sessions"][0]["session_id"] == "cli:FriendMessage:cli_session"

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_list_sessions_with_platform(self, mock_get_mgr):
        handler = _make_handler()
        mock_mgr = MagicMock()
        mock_mgr.db.get_session_conversations = AsyncMock(return_value=([], 0))
        mock_get_mgr.return_value = mock_mgr

        result = await handler._list_sessions(
            {"page": 1, "page_size": 10, "platform": "qq"}, "req-2"
        )
        data = json.loads(result)

        assert data["status"] == "success"
        assert data["sessions"] == []
        assert data["total"] == 0
        mock_mgr.db.get_session_conversations.assert_called_once_with(
            page=1, page_size=10, search_query=None, platform="qq"
        )

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_list_sessions_not_initialized(self, mock_get_mgr):
        handler = _make_handler()
        mock_get_mgr.return_value = None

        result = await handler._list_sessions({}, "req-3")
        data = json.loads(result)

        assert data["status"] == "error"
        assert "未初始化" in data["error"]


class TestListSessionConversations:
    """_list_session_conversations 方法测试"""

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_list_convs_success(self, mock_get_mgr):
        handler = _make_handler()
        mock_mgr = MagicMock()

        # Mock conversation objects
        mock_conv = MagicMock()
        mock_conv.cid = "conv-abc"
        mock_conv.title = "测试对话"
        mock_conv.persona_id = None
        mock_conv.created_at = 1700000000
        mock_conv.updated_at = 1700000000
        mock_conv.token_usage = 150

        mock_mgr.get_conversations = AsyncMock(return_value=[mock_conv])
        mock_mgr.get_curr_conversation_id = AsyncMock(return_value="conv-abc")
        mock_get_mgr.return_value = mock_mgr

        result = await handler._list_session_conversations(
            {"session_id": "cli:FriendMessage:cli_session", "page": 1, "page_size": 20},
            "req-4",
        )
        data = json.loads(result)

        assert data["status"] == "success"
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["cid"] == "conv-abc"
        assert data["conversations"][0]["is_current"] is True
        assert data["current_cid"] == "conv-abc"

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_list_convs_missing_session_id(self, mock_get_mgr):
        handler = _make_handler()
        mock_get_mgr.return_value = MagicMock()

        result = await handler._list_session_conversations({"page": 1}, "req-5")
        data = json.loads(result)

        assert data["status"] == "error"
        assert "session_id" in data["error"]

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_list_convs_pagination(self, mock_get_mgr):
        handler = _make_handler()
        mock_mgr = MagicMock()

        # Create 3 mock conversations
        convs = []
        for i in range(3):
            c = MagicMock()
            c.cid = f"conv-{i}"
            c.title = f"对话 {i}"
            c.persona_id = None
            c.created_at = 1700000000
            c.updated_at = 1700000000
            c.token_usage = 0
            convs.append(c)

        mock_mgr.get_conversations = AsyncMock(return_value=convs)
        mock_mgr.get_curr_conversation_id = AsyncMock(return_value="conv-0")
        mock_get_mgr.return_value = mock_mgr

        # Page 1 with size 2
        result = await handler._list_session_conversations(
            {"session_id": "test", "page": 1, "page_size": 2}, "req-6"
        )
        data = json.loads(result)

        assert data["total"] == 3
        assert data["total_pages"] == 2
        assert len(data["conversations"]) == 2


class TestGetSessionHistory:
    """_get_session_history 方法测试"""

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_get_history_success(self, mock_get_mgr):
        handler = _make_handler()
        mock_mgr = MagicMock()
        mock_mgr.get_curr_conversation_id = AsyncMock(return_value="conv-abc")

        # Mock conversation with raw history
        mock_conv = MagicMock()
        mock_conv.history = json.dumps(
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！"},
            ]
        )
        mock_mgr.get_conversation = AsyncMock(return_value=mock_conv)
        mock_get_mgr.return_value = mock_mgr

        result = await handler._get_session_history(
            {"session_id": "cli:FriendMessage:cli_session", "page": 1},
            "req-7",
        )
        data = json.loads(result)

        assert data["status"] == "success"
        assert len(data["history"]) == 2
        assert data["history"][0]["role"] == "user"
        assert data["history"][0]["text"] == "你好"
        assert data["history"][1]["role"] == "assistant"
        assert data["history"][1]["text"] == "你好！"
        assert data["conversation_id"] == "conv-abc"

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_get_history_with_image(self, mock_get_mgr):
        """图片内容应被替换为 [图片]"""
        handler = _make_handler()
        mock_mgr = MagicMock()

        mock_conv = MagicMock()
        mock_conv.history = json.dumps(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "看这张图"},
                        {"type": "image_url", "image_url": {"url": "http://..."}},
                    ],
                },
                {"role": "assistant", "content": "这是一只猫"},
            ]
        )
        mock_mgr.get_conversation = AsyncMock(return_value=mock_conv)
        mock_get_mgr.return_value = mock_mgr

        result = await handler._get_session_history(
            {"session_id": "test", "conversation_id": "conv-img", "page": 1},
            "req-img",
        )
        data = json.loads(result)

        assert data["status"] == "success"
        assert "[图片]" in data["history"][0]["text"]
        assert "看这张图" in data["history"][0]["text"]

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_get_history_with_tool_calls(self, mock_get_mgr):
        """tool_calls 应被替换为 [调用工具: name]"""
        handler = _make_handler()
        mock_mgr = MagicMock()

        mock_conv = MagicMock()
        mock_conv.history = json.dumps(
            [
                {"role": "user", "content": "查天气"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"function": {"name": "get_weather", "arguments": "{}"}}
                    ],
                },
            ]
        )
        mock_mgr.get_conversation = AsyncMock(return_value=mock_conv)
        mock_get_mgr.return_value = mock_mgr

        result = await handler._get_session_history(
            {"session_id": "test", "conversation_id": "conv-tc", "page": 1},
            "req-tc",
        )
        data = json.loads(result)

        assert data["status"] == "success"
        assert "[调用工具: get_weather]" in data["history"][1]["text"]

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_get_history_with_conv_id(self, mock_get_mgr):
        handler = _make_handler()
        mock_mgr = MagicMock()

        mock_conv = MagicMock()
        mock_conv.history = json.dumps([{"role": "user", "content": "test"}])
        mock_mgr.get_conversation = AsyncMock(return_value=mock_conv)
        mock_get_mgr.return_value = mock_mgr

        result = await handler._get_session_history(
            {
                "session_id": "test_session",
                "conversation_id": "conv-xyz",
                "page": 1,
            },
            "req-8",
        )
        data = json.loads(result)

        assert data["status"] == "success"
        assert data["conversation_id"] == "conv-xyz"
        mock_mgr.get_conversation.assert_called_once_with("test_session", "conv-xyz")

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_get_history_no_active_conversation(self, mock_get_mgr):
        handler = _make_handler()
        mock_mgr = MagicMock()
        mock_mgr.get_curr_conversation_id = AsyncMock(return_value=None)
        mock_get_mgr.return_value = mock_mgr

        result = await handler._get_session_history(
            {"session_id": "no_conv_session", "page": 1}, "req-9"
        )
        data = json.loads(result)

        assert data["status"] == "success"
        assert data["history"] == []
        assert "没有活跃的对话" in data["response"]

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_get_history_missing_session_id(self, mock_get_mgr):
        handler = _make_handler()
        mock_get_mgr.return_value = MagicMock()

        result = await handler._get_session_history({"page": 1}, "req-10")
        data = json.loads(result)

        assert data["status"] == "error"
        assert "session_id" in data["error"]

    @pytest.mark.asyncio
    @patch("astrbot.core.conversation_mgr.get_conversation_manager")
    async def test_get_history_not_initialized(self, mock_get_mgr):
        handler = _make_handler()
        mock_get_mgr.return_value = None

        result = await handler._get_session_history({"session_id": "test"}, "req-11")
        data = json.loads(result)

        assert data["status"] == "error"
        assert "未初始化" in data["error"]
