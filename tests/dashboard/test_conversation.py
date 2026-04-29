"""Mock-based unit tests for ConversationRoute in conversation.py.

All tests mock ``request`` and ``g`` at the module level so no Quart app
fixture is required.  The Route base class requires a mock ``app`` on the
context object; register_routes() calls add_url_rule through the mock.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.dashboard.routes.conversation import ConversationRoute
from astrbot.dashboard.routes.route import RouteContext

# Sentinel to distinguish "no conv_mgr argument" from "conv_mgr=None".
_UNSET = object()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_route_context():
    """Return a RouteContext with a mock app and config."""
    return RouteContext(
        app=MagicMock(),
        config=MagicMock(),
    )


def _make_mock_args_getter(values: dict):
    """Build a callable that mimics request.args.get with optional type
    coercion (the pattern used by Quart's MultiDict)."""

    def get(key, default=None, type=None):  # noqa: A002
        val = values.get(key)
        if val is not None and type is not None:
            return type(val)
        return val if val is not None else default

    return get


def _build_route(conv_mgr=_UNSET):
    """Return a (ConversationRoute, mock_db, mock_core_lifecycle) tuple.

    All dependencies are MagicMock based.  Pass ``conv_mgr=None`` to simulate
    an unavailable conversation manager; the default creates a fresh mock.
    """
    ctx = _make_route_context()
    mock_db = MagicMock()
    mock_core = MagicMock()
    if conv_mgr is _UNSET:
        mock_core.conversation_manager = MagicMock()
    else:
        mock_core.conversation_manager = conv_mgr
    route = ConversationRoute(
        context=ctx,
        db_helper=mock_db,
        core_lifecycle=mock_core,
    )
    return route, mock_db, mock_core


# ---------------------------------------------------------------------------
# list_conversations
# ---------------------------------------------------------------------------


class TestListConversations:
    @patch("astrbot.dashboard.routes.conversation.request")
    @patch("astrbot.dashboard.routes.conversation.g")
    @pytest.mark.asyncio
    async def test_default_pagination(self, mock_g, mock_request):
        """Default page/page_size when no query params are supplied."""
        mock_request.args.get.side_effect = _make_mock_args_getter({})
        mock_g.get.return_value = "testuser"

        route, _db, _core = _build_route()
        result = await route.list_conversations()

        assert result["status"] == "ok"
        pag = result["data"]["pagination"]
        assert pag["page"] == 1
        assert pag["page_size"] == 20

    @patch("astrbot.dashboard.routes.conversation.request")
    @patch("astrbot.dashboard.routes.conversation.g")
    @pytest.mark.asyncio
    async def test_custom_pagination(self, mock_g, mock_request):
        """Custom page/page_size passed as query strings."""
        mock_request.args.get.side_effect = _make_mock_args_getter(
            {"page": "3", "page_size": "50"}
        )
        mock_g.get.return_value = "testuser"

        route, _db, _core = _build_route()
        result = await route.list_conversations()

        assert result["status"] == "ok"
        pag = result["data"]["pagination"]
        assert pag["page"] == 3
        assert pag["page_size"] == 50

    @patch("astrbot.dashboard.routes.conversation.request")
    @patch("astrbot.dashboard.routes.conversation.g")
    @pytest.mark.asyncio
    async def test_page_size_clamped_to_max_100(self, mock_g, mock_request):
        """page_size beyond 100 is clamped."""
        mock_request.args.get.side_effect = _make_mock_args_getter(
            {"page_size": "999"}
        )
        mock_g.get.return_value = "testuser"

        route, _db, _core = _build_route()
        result = await route.list_conversations()

        assert result["status"] == "ok"
        assert result["data"]["pagination"]["page_size"] == 100

    @patch("astrbot.dashboard.routes.conversation.request")
    @patch("astrbot.dashboard.routes.conversation.g")
    @pytest.mark.asyncio
    async def test_page_clamped_to_minimum_1(self, mock_g, mock_request):
        """page below 1 is raised to 1."""
        mock_request.args.get.side_effect = _make_mock_args_getter(
            {"page": "0"}
        )
        mock_g.get.return_value = "testuser"

        route, _db, _core = _build_route()
        result = await route.list_conversations()

        assert result["status"] == "ok"
        assert result["data"]["pagination"]["page"] == 1

    @patch("astrbot.dashboard.routes.conversation.request")
    @patch("astrbot.dashboard.routes.conversation.g")
    @pytest.mark.asyncio
    async def test_filter_params_passed_to_manager(self, mock_g, mock_request):
        """Filter query params are split and forwarded."""
        mock_request.args.get.side_effect = _make_mock_args_getter(
            {
                "platforms": "webchat,discord",
                "message_types": "FriendMessage",
                "search": "hello",
            }
        )
        mock_g.get.return_value = "testuser"

        route, _db, core = _build_route()
        await route.list_conversations()

        core.conversation_manager.get_filtered_conversations.assert_awaited_once_with(
            page=1,
            page_size=20,
            platforms=["webchat", "discord"],
            message_types=["FriendMessage"],
            search_query="hello",
            exclude_ids=[],
            exclude_platforms=[],
        )

    @patch("astrbot.dashboard.routes.conversation.request")
    @patch("astrbot.dashboard.routes.conversation.g")
    @pytest.mark.asyncio
    async def test_error_when_conv_mgr_unavailable(self, mock_g, mock_request):
        """Returns error when conversation_manager is falsy."""
        mock_g.get.return_value = "testuser"

        route, _db, _core = _build_route(conv_mgr=None)
        result = await route.list_conversations()

        assert result["status"] == "error"
        assert "not available" in (result.get("message") or "")

    @patch("astrbot.dashboard.routes.conversation.request")
    @patch("astrbot.dashboard.routes.conversation.g")
    @pytest.mark.asyncio
    async def test_db_query_exception_wrapped(self, mock_g, mock_request):
        """Exception from get_filtered_conversations is caught and returned as error."""
        mock_g.get.return_value = "testuser"

        route, _db, core = _build_route()
        core.conversation_manager.get_filtered_conversations.side_effect = (
            RuntimeError("db connection lost")
        )
        result = await route.list_conversations()

        assert result["status"] == "error"
        assert "数据库查询出错" in str(result.get("message") or "")


# ---------------------------------------------------------------------------
# get_conv_detail
# ---------------------------------------------------------------------------


class TestGetConvDetail:
    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_missing_params_returns_error(self, mock_request):
        mock_request.get_json = AsyncMock(return_value={})
        route, _db, _core = _build_route()
        result = await route.get_conv_detail()

        assert result["status"] == "error"
        assert "缺少必要参数" in str(result.get("message") or "")

    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_conversation_not_found(self, mock_request):
        mock_request.get_json = AsyncMock(
            return_value={"user_id": "user1", "cid": "cid1"}
        )
        route, _db, core = _build_route()
        core.conversation_manager.get_conversation = AsyncMock(return_value=None)
        result = await route.get_conv_detail()

        assert result["status"] == "error"
        assert "不存在" in str(result.get("message") or "")

    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_success_with_valid_params(self, mock_request):
        mock_request.get_json = AsyncMock(
            return_value={"user_id": "user1", "cid": "cid1"}
        )
        route, _db, core = _build_route()
        mock_conv = MagicMock()
        mock_conv.title = "test-title"
        mock_conv.persona_id = "p1"
        mock_conv.history = "[]"
        mock_conv.created_at = "2024-01-01"
        mock_conv.updated_at = "2024-01-02"
        core.conversation_manager.get_conversation = AsyncMock(return_value=mock_conv)
        result = await route.get_conv_detail()

        assert result["status"] == "ok"
        assert result["data"]["title"] == "test-title"
        assert result["data"]["persona_id"] == "p1"


# ---------------------------------------------------------------------------
# upd_conv
# ---------------------------------------------------------------------------


class TestUpdConv:
    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_missing_params_returns_error(self, mock_request):
        mock_request.get_json = AsyncMock(return_value={})
        route, _db, _core = _build_route()
        result = await route.upd_conv()

        assert result["status"] == "error"
        assert "缺少必要参数" in str(result.get("message") or "")

    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_not_found(self, mock_request):
        mock_request.get_json = AsyncMock(
            return_value={"user_id": "user1", "cid": "cid1"}
        )
        route, _db, core = _build_route()
        core.conversation_manager.get_conversation = AsyncMock(return_value=None)
        result = await route.upd_conv()

        assert result["status"] == "error"
        assert "不存在" in str(result.get("message") or "")


# ---------------------------------------------------------------------------
# del_conv  (single + batch)
# ---------------------------------------------------------------------------


class TestDelConv:
    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_single_missing_params(self, mock_request):
        mock_request.get_json = AsyncMock(return_value={})
        route, _db, _core = _build_route()
        result = await route.del_conv()

        assert result["status"] == "error"

    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_batch_delete(self, mock_request):
        mock_request.get_json = AsyncMock(
            return_value={
                "conversations": [
                    {"user_id": "u1", "cid": "c1"},
                    {"user_id": "u2", "cid": "c2"},
                ]
            }
        )
        route, _db, core = _build_route()
        core.conversation_manager.delete_conversation = AsyncMock()
        result = await route.del_conv()

        assert result["status"] == "ok"
        assert result["data"]["deleted_count"] == 2

    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_batch_with_failures(self, mock_request):
        mock_request.get_json = AsyncMock(
            return_value={
                "conversations": [
                    {"user_id": "u1", "cid": "c1"},
                    {"user_id": "", "cid": ""},  # missing params
                ]
            }
        )
        route, _db, core = _build_route()
        core.conversation_manager.delete_conversation = AsyncMock()
        result = await route.del_conv()

        assert result["status"] == "ok"
        assert result["data"]["deleted_count"] == 1
        assert result["data"]["failed_count"] == 1


# ---------------------------------------------------------------------------
# update_history
# ---------------------------------------------------------------------------


class TestUpdateHistory:
    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_missing_user_id_or_cid(self, mock_request):
        mock_request.get_json = AsyncMock(return_value={"history": []})
        route, _db, _core = _build_route()
        result = await route.update_history()

        assert result["status"] == "error"
        assert "缺少必要参数" in str(result.get("message") or "")

    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_missing_history(self, mock_request):
        mock_request.get_json = AsyncMock(
            return_value={"user_id": "u1", "cid": "c1"}
        )
        route, _db, _core = _build_route()
        result = await route.update_history()

        assert result["status"] == "error"
        assert "缺少必要参数" in str(result.get("message") or "")

    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_invalid_json_string_returns_error(self, mock_request):
        mock_request.get_json = AsyncMock(
            return_value={
                "user_id": "u1",
                "cid": "c1",
                "history": "not-json",
            }
        )
        route, _db, _core = _build_route()
        result = await route.update_history()

        assert result["status"] == "error"
        assert "有效的 JSON" in str(result.get("message") or "")

    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_valid_list_history(self, mock_request):
        mock_request.get_json = AsyncMock(
            return_value={
                "user_id": "u1",
                "cid": "c1",
                "history": [{"role": "user", "content": "hello"}],
            }
        )
        route, _db, core = _build_route()
        core.conversation_manager.get_conversation = AsyncMock(
            return_value=MagicMock()
        )
        core.conversation_manager.update_conversation = AsyncMock()
        result = await route.update_history()

        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# export_conversations
# ---------------------------------------------------------------------------


class TestExportConversations:
    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_empty_list_returns_error(self, mock_request):
        mock_request.get_json = AsyncMock(
            return_value={"conversations": []}
        )
        route, _db, _core = _build_route()
        result = await route.export_conversations()

        assert result["status"] == "error"
        assert "不能为空" in str(result.get("message") or "")

    @patch("astrbot.dashboard.routes.conversation.request")
    @patch("astrbot.dashboard.routes.conversation.send_file")
    @pytest.mark.asyncio
    async def test_export_success(self, mock_send_file, mock_request):
        """A valid export request returns a file response via send_file."""
        mock_send_file.return_value = {"status": "ok", "_mock_file": True}
        mock_request.get_json = AsyncMock(
            return_value={
                "conversations": [
                    {"user_id": "u1", "cid": "c1"},
                ]
            }
        )
        route, _db, core = _build_route()
        mock_conv = MagicMock()
        mock_conv.history = "[]"
        mock_conv.title = "t1"
        mock_conv.persona_id = None
        mock_conv.platform_id = "webchat"
        mock_conv.created_at = "2024-01-01"
        mock_conv.updated_at = "2024-01-02"
        core.conversation_manager.get_conversation = AsyncMock(return_value=mock_conv)
        result = await route.export_conversations()

        assert result["_mock_file"] is True
        mock_send_file.assert_awaited_once()

    @patch("astrbot.dashboard.routes.conversation.request")
    @pytest.mark.asyncio
    async def test_export_skips_items_missing_params(self, mock_request):
        """Items without user_id/cid are reported as failures."""
        mock_request.get_json = AsyncMock(
            return_value={
                "conversations": [
                    {"user_id": "u1", "cid": "c1"},
                    {"user_id": "", "cid": ""},  # missing
                ]
            }
        )
        route, _db, core = _build_route()
        core.conversation_manager.get_conversation = AsyncMock(
            side_effect=[
                MagicMock(
                    history="[]",
                    title="t",
                    persona_id=None,
                    platform_id="w",
                    created_at="",
                    updated_at="",
                ),
            ]
        )
        with patch("astrbot.dashboard.routes.conversation.send_file") as mock_sf:
            mock_sf.return_value = {"_mock": True}
            result = await route.export_conversations()

        assert result["_mock"] is True
