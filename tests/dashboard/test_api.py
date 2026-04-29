"""Comprehensive API smoke tests covering every registered route.

Each endpoint is hit once — the test only checks that it does not crash
(no 500 / no hang).  Created after a merge broke routes silently.
"""

import pytest
import pytest_asyncio
from _pytest.mark.structures import ParameterSet
from quart import Quart


def _p(method: str, path: str, body: dict | None = None) -> ParameterSet:
    """Shorthand to build a parametrize row with readable id."""
    name = path.replace("/", "_").replace("?", "_").replace("=", "_")
    return pytest.param(method, path, body, id=f"{method.upper()}_{name}".rstrip("_"))


ROUTES = [
    # -- auth --
    _p("POST", "/api/auth/login", {"username": "astrbot", "password": "astrbot"}),
    # -- chat --
    _p("GET", "/api/chat/sessions"),
    _p("POST", "/api/chat/new_session"),
    _p("POST", "/api/chat/stop"),
    _p("POST", "/api/chat/send", {"command": "test", "text": "ping"}),
    _p("GET", "/api/chat/get_session?conversation_id=0"),
    _p("GET", "/api/chat/delete_session?conversation_id=0"),
    _p("POST", "/api/chat/batch_delete_sessions", {"session_ids": []}),
    _p("POST", "/api/chat/update_session_display_name", {"conversation_id": "0", "name": "t"}),
    _p("GET", "/api/chat/get_file?filename=nonexistent"),
    _p("POST", "/api/chat/post_file"),
    _p("GET", "/api/chat/get_attachment?attachment_id=0"),
    # -- conversation --
    _p("GET", "/api/conversation/list"),
    _p("GET", "/api/conversation/detail?id=0"),
    # -- config —
    _p("POST", "/api/config/get", {"keys": []}),
    _p("GET", "/api/config/default"),
    _p("GET", "/api/config/abconfs"),
    _p("POST", "/api/config/abconf/new", {"name": "t", "config": {}}),
    _p("GET", "/api/config/abconf?id=0"),
    _p("POST", "/api/config/abconf/delete", {"id": 0}),
    _p("POST", "/api/config/abconf/update", {"id": 0, "config": {}}),
    _p("GET", "/api/config/umo_abconf_routes"),
    _p("GET", "/api/config/provider/list"),
    _p("GET", "/api/config/provider/template"),
    _p("GET", "/api/config/platform/list"),
    _p("POST", "/api/config/platform/delete", {"id": 0}),
    _p("GET", "/api/config/provider_sources/models"),
    # -- persona —
    _p("GET", "/api/persona/list"),
    _p("POST", "/api/persona/create", {"name": "t", "prompt": "test"}),
    _p("GET", "/api/persona/detail?id=0"),
    _p("POST", "/api/persona/delete", {"id": 0}),
    # -- cron —
    _p("GET", "/api/cron/jobs"),
    # -- api key —
    _p("GET", "/api/apikey/list"),
    _p("POST", "/api/apikey/create", {"name": "t", "scopes": ["chat:read"]}),
    _p("POST", "/api/apikey/delete", {"id": 0}),
    # — platform —
    _p("GET", "/api/platform/list"),
    _p("GET", "/api/platform/stats"),
    # — knowledge base —
    _p("GET", "/api/kb/list"),
    _p("POST", "/api/kb/create", {"name": "t"}),
    _p("GET", "/api/kb/get?id=0"),
    _p("GET", "/api/kb/stats"),
    # — skills —
    _p("POST", "/api/skills/upload"),
    # — tools / MCP —
    _p("GET", "/api/tools/list"),
    _p("GET", "/api/tools/mcp/servers"),
    _p("POST", "/api/tools/toggle-tool", {"tool_name": "test", "enabled": False}),
    # — chatui project —
    _p("GET", "/api/chatui_project/list"),
    _p("POST", "/api/chatui_project/create", {"title": "t"}),
    _p("GET", "/api/chatui_project/get"),
    _p("POST", "/api/chatui_project/delete", {"id": 0}),
    # — stat —
    _p("GET", "/api/stat/get"),
    _p("GET", "/api/stat/version"),
    _p("GET", "/api/stat/storage"),
    _p("GET", "/api/stat/changelog"),
    # — update —
    _p("GET", "/api/update/check"),
    _p("GET", "/api/update/releases"),
    # — subagent —
    _p("GET", "/api/subagent/config"),
    # — session management —
    _p("GET", "/api/session/groups"),
    _p("POST", "/api/session/group/create", {"name": "t"}),
    # — backup —
    _p("GET", "/api/backup/list"),
    _p("GET", "/api/backup/progress"),
    _p("GET", "/api/backup/check"),
    # — commands —
    _p("GET", "/api/commands/conflicts"),
    _p("GET", "/api/commands/permission"),
    # — live-log —
    _p("GET", "/api/log-history"),
]


class TestAllRoutes:
    """Hit every registered route and assert no 500 / no crash."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,path,body", ROUTES)
    async def test_route_returns_no_500(
        self,
        method: str,
        path: str,
        body: dict | None,
        app: Quart,
        authenticated_header: dict,
    ):
        client = app.test_client()
        headers = {**authenticated_header}
        if body is not None:
            resp = await client.open(path, method=method, headers=headers, json=body)
        else:
            resp = await client.open(path, method=method, headers=headers, json=None)
        assert resp.status_code != 500, f"{method} {path} returned 500"

    # Live-log SSE — just check the response status code
    @pytest.mark.asyncio
    async def test_live_log_sse(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/live-log", headers=authenticated_header)
        assert resp.status_code == 200
