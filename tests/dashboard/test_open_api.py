"""Mock-based unit tests for standalone methods in OpenApiRoute (open_api.py).

Tests cover _resolve_open_username, _get_chat_config_list,
_resolve_chat_config_id, _extract_ws_api_key, _ensure_chat_session, and
_ensure_runtime_ready.  No Quart app fixture required; all external
dependencies (request, websocket, db, core_lifecycle) are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.dashboard.routes.open_api import OpenApiRoute
from astrbot.dashboard.routes.route import RouteContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_route_context():
    """Return a RouteContext with a mock app and config."""
    return RouteContext(app=MagicMock(), config=MagicMock())


def _build_openapi_route(core_lifecycle=None, db=None, chat_route=None):
    """Return an (OpenApiRoute, mock_db, mock_core_lifecycle, mock_chat_route)
    tuple, filling in MagicMock defaults for omitted dependencies.
    """
    ctx = _make_route_context()
    mock_core = core_lifecycle or MagicMock()
    mock_db = db or MagicMock()
    mock_chat = chat_route or MagicMock()
    route = OpenApiRoute(
        context=ctx,
        db=mock_db,
        core_lifecycle=mock_core,
        chat_route=mock_chat,
    )
    return route, mock_db, mock_core, mock_chat


# ---------------------------------------------------------------------------
# _resolve_open_username  (static)
# ---------------------------------------------------------------------------


class TestResolveOpenUsername:
    def test_none_returns_error(self):
        username, err = OpenApiRoute._resolve_open_username(None)
        assert username is None
        assert err == "Missing key: username"

    def test_empty_string_returns_error(self):
        username, err = OpenApiRoute._resolve_open_username("")
        assert username is None
        assert err == "username is empty"

    def test_whitespace_only_returns_error(self):
        username, err = OpenApiRoute._resolve_open_username("   ")
        assert username is None
        assert err == "username is empty"

    def test_valid_username(self):
        username, err = OpenApiRoute._resolve_open_username("alice")
        assert username == "alice"
        assert err is None

    def test_valid_username_trimmed(self):
        username, err = OpenApiRoute._resolve_open_username("  bob  ")
        assert username == "bob"
        assert err is None


# ---------------------------------------------------------------------------
# _get_chat_config_list
# ---------------------------------------------------------------------------


class TestGetChatConfigList:
    def test_returns_empty_when_mgr_is_none(self):
        core = MagicMock()
        core.astrbot_config_mgr = None
        route, *_ = _build_openapi_route(core_lifecycle=core)
        assert route._get_chat_config_list() == []

    def test_returns_config_list(self):
        core = MagicMock()
        core.astrbot_config_mgr.get_conf_list.return_value = [
            {"id": "default", "name": "Default Config", "path": "/cfg1"},
            {"id": "cfg2", "name": "My Config", "path": "/cfg2"},
        ]
        route, *_ = _build_openapi_route(core_lifecycle=core)
        result = route._get_chat_config_list()

        assert len(result) == 2
        assert result[0] == {
            "id": "default",
            "name": "Default Config",
            "path": "/cfg1",
            "is_default": True,
        }
        assert result[1] == {
            "id": "cfg2",
            "name": "My Config",
            "path": "/cfg2",
            "is_default": False,
        }


# ---------------------------------------------------------------------------
# _resolve_chat_config_id
# ---------------------------------------------------------------------------


class TestResolveChatConfigId:
    def test_no_config_id_or_name_returns_none_none(self):
        route, *_ = _build_openapi_route()
        config_id, err = route._resolve_chat_config_id({})
        assert config_id is None
        assert err is None

    def test_config_id_found(self):
        core = MagicMock()
        core.astrbot_config_mgr.get_conf_list.return_value = [
            {"id": "cfg1", "name": "Cfg 1", "path": "/p1"},
        ]
        route, *_ = _build_openapi_route(core_lifecycle=core)
        config_id, err = route._resolve_chat_config_id({"config_id": "cfg1"})
        assert config_id == "cfg1"
        assert err is None

    def test_config_id_not_found(self):
        core = MagicMock()
        core.astrbot_config_mgr.get_conf_list.return_value = []
        route, *_ = _build_openapi_route(core_lifecycle=core)
        config_id, err = route._resolve_chat_config_id({"config_id": "missing"})
        assert config_id is None
        assert "not found" in (err or "")

    def test_config_name_found(self):
        core = MagicMock()
        core.astrbot_config_mgr.get_conf_list.return_value = [
            {"id": "c1", "name": "My Config", "path": "/p1"},
        ]
        route, *_ = _build_openapi_route(core_lifecycle=core)
        config_id, err = route._resolve_chat_config_id(
            {"config_name": "My Config"}
        )
        assert config_id == "c1"
        assert err is None

    def test_config_name_not_found(self):
        core = MagicMock()
        core.astrbot_config_mgr.get_conf_list.return_value = []
        route, *_ = _build_openapi_route(core_lifecycle=core)
        config_id, err = route._resolve_chat_config_id(
            {"config_name": "Nope"}
        )
        assert config_id is None
        assert "not found" in (err or "")

    def test_config_name_ambiguous(self):
        core = MagicMock()
        core.astrbot_config_mgr.get_conf_list.return_value = [
            {"id": "c1", "name": "Same Name", "path": "/p1"},
            {"id": "c2", "name": "Same Name", "path": "/p2"},
        ]
        route, *_ = _build_openapi_route(core_lifecycle=core)
        config_id, err = route._resolve_chat_config_id(
            {"config_name": "Same Name"}
        )
        assert config_id is None
        assert "ambiguous" in (err or "")

    def test_config_name_empty_after_strip_returns_none(self):
        """When config_name is present but only whitespace."""
        core = MagicMock()
        core.astrbot_config_mgr.get_conf_list.return_value = []
        route, *_ = _build_openapi_route(core_lifecycle=core)
        config_id, err = route._resolve_chat_config_id(
            {"config_name": "   "}
        )
        # config_name is stripped to "" -> the method returns (None, "config_name is empty")
        assert config_id is None
        assert err == "config_name is empty"


# ---------------------------------------------------------------------------
# _extract_ws_api_key  (static, uses ``websocket`` from quart)
# ---------------------------------------------------------------------------


class TestExtractWsApiKey:
    @patch("astrbot.dashboard.routes.open_api.websocket")
    def test_from_api_key_arg(self, mock_ws):
        mock_ws.args.get.side_effect = lambda k, default=None: (
            "my-api-key" if k == "api_key" else default
        )
        result = OpenApiRoute._extract_ws_api_key()
        assert result == "my-api-key"

    @patch("astrbot.dashboard.routes.open_api.websocket")
    def test_from_key_arg(self, mock_ws):
        mock_ws.args.get.side_effect = lambda k, default=None: (
            "key-from-arg" if k == "key" else default
        )
        result = OpenApiRoute._extract_ws_api_key()
        assert result == "key-from-arg"

    @patch("astrbot.dashboard.routes.open_api.websocket")
    def test_from_x_api_key_header(self, mock_ws):
        mock_ws.args.get.return_value = None
        mock_ws.headers.get.side_effect = lambda k, default=None: (
            "header-key" if k == "X-API-Key" else default
        )
        result = OpenApiRoute._extract_ws_api_key()
        assert result == "header-key"

    @patch("astrbot.dashboard.routes.open_api.websocket")
    def test_from_bearer_auth(self, mock_ws):
        mock_ws.args.get.return_value = None
        mock_ws.headers.get.side_effect = lambda k, default=None: (
            "Bearer token123" if k == "Authorization" else default
        )
        result = OpenApiRoute._extract_ws_api_key()
        assert result == "token123"

    @patch("astrbot.dashboard.routes.open_api.websocket")
    def test_from_apikey_auth(self, mock_ws):
        mock_ws.args.get.return_value = None
        mock_ws.headers.get.side_effect = lambda k, default=None: (
            "ApiKey api-key-value" if k == "Authorization" else default
        )
        result = OpenApiRoute._extract_ws_api_key()
        assert result == "api-key-value"

    @patch("astrbot.dashboard.routes.open_api.websocket")
    def test_no_key_found_returns_none(self, mock_ws):
        mock_ws.args.get.return_value = None
        mock_ws.headers.get.return_value = ""
        result = OpenApiRoute._extract_ws_api_key()
        assert result is None


# ---------------------------------------------------------------------------
# _ensure_chat_session
# ---------------------------------------------------------------------------


class TestEnsureChatSession:
    @pytest.mark.asyncio
    async def test_session_exists_and_belongs_to_user(self):
        db = MagicMock()
        db.get_platform_session_by_id = AsyncMock(return_value=MagicMock(creator="alice"))
        route, *_ = _build_openapi_route(db=db)
        err = await route._ensure_chat_session("alice", "sid1")
        assert err is None

    @pytest.mark.asyncio
    async def test_session_exists_but_wrong_user(self):
        db = MagicMock()
        db.get_platform_session_by_id = AsyncMock(
            return_value=MagicMock(creator="bob")
        )
        route, *_ = _build_openapi_route(db=db)
        err = await route._ensure_chat_session("alice", "sid1")
        assert err is not None
        assert "belongs to another" in err

    @pytest.mark.asyncio
    async def test_session_does_not_exist_created(self):
        db = MagicMock()
        db.get_platform_session_by_id = AsyncMock(return_value=None)
        db.create_platform_session = AsyncMock()
        route, *_ = _build_openapi_route(db=db)
        err = await route._ensure_chat_session("alice", "new-sid")
        assert err is None
        db.create_platform_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_race_recovered(self):
        """If create_platform_session raises but a concurrent creation
        succeeded for the same user, we recover gracefully."""
        db = MagicMock()
        # First get returns None, create raises
        call_count = 0

        async def get_session(*args, **kwargs):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # first call: not found
            return MagicMock(creator="alice")  # second call: found (race)

        db.get_platform_session_by_id.side_effect = get_session
        db.create_platform_session = AsyncMock(side_effect=Exception("duplicate"))
        route, *_ = _build_openapi_route(db=db)
        err = await route._ensure_chat_session("alice", "race-sid")
        assert err is None  # recovered


# ---------------------------------------------------------------------------
# _send_chat_ws_error  (uses ``websocket`` from quart)
# ---------------------------------------------------------------------------


class TestSendChatWsError:
    @patch("astrbot.dashboard.routes.open_api.websocket")
    @pytest.mark.asyncio
    async def test_sends_error_json(self, mock_ws):
        route, *_ = _build_openapi_route()
        await route._send_chat_ws_error("Something broke", "ERR_CODE")
        mock_ws.send_json.assert_awaited_once_with(
            {"type": "error", "code": "ERR_CODE", "data": "Something broke"}
        )


# ---------------------------------------------------------------------------
# _update_session_config_route
# ---------------------------------------------------------------------------


class TestUpdateSessionConfigRoute:
    @pytest.mark.asyncio
    async def test_no_config_id_returns_none(self):
        route, *_ = _build_openapi_route()
        err = await route._update_session_config_route(
            username="alice",
            session_id="sid1",
            config_id=None,
        )
        assert err is None

    @pytest.mark.asyncio
    async def test_router_not_available(self):
        core = MagicMock()
        core.umop_config_router = None
        route, *_ = _build_openapi_route(core_lifecycle=core)
        err = await route._update_session_config_route(
            username="alice",
            session_id="sid1",
            config_id="cfg1",
        )
        assert err is not None
        assert "not available" in err

    @pytest.mark.asyncio
    async def test_delete_route_for_default(self):
        core = MagicMock()
        core.umop_config_router.delete_route = AsyncMock()
        route, *_ = _build_openapi_route(core_lifecycle=core)
        err = await route._update_session_config_route(
            username="alice",
            session_id="sid1",
            config_id="default",
        )
        assert err is None
        core.umop_config_router.delete_route.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_route_for_custom_config(self):
        core = MagicMock()
        core.umop_config_router.update_route = AsyncMock()
        route, *_ = _build_openapi_route(core_lifecycle=core)
        err = await route._update_session_config_route(
            username="alice",
            session_id="sid1",
            config_id="mycfg",
        )
        assert err is None
        core.umop_config_router.update_route.assert_awaited_once()
