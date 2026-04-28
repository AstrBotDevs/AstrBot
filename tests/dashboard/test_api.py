"""Comprehensive API smoke tests covering every registered route.

Each endpoint is hit once — the test only checks that it does not crash
(no 500).  Created after a merge broke routes silently; this ensures that
regressions are caught before deployment.
"""

import json
import re

import pytest
import pytest_asyncio
from quart import Quart


# ===========================================================================
# Route registry  —  every endpoint the dashboard registers
# ===========================================================================
# (method, path, json_body | None)
# Paths with ``<angle>`` placeholders are skipped (they need runtime IDs).
# Paths that expect a file upload are also skipped (cannot be tested without
# a real file).
ROUTES: list[tuple[str, str, dict | None]] = [
    # -- auth --
    ("POST", "/api/auth/login", {"username": "astrbot", "password": "astrbot"}),
    # -- chat --
    ("GET", "/api/chat/sessions", None),
    ("POST", "/api/chat/new_session", None),
    ("POST", "/api/chat/stop", None),
    ("POST", "/api/chat/send", {"command": "test", "text": "ping"}),
    ("GET", "/api/chat/get_session?conversation_id=0", None),
    ("GET", "/api/chat/delete_session?conversation_id=0", None),
    ("POST", "/api/chat/batch_delete_sessions", {"session_ids": []}),
    ("POST", "/api/chat/update_session_display_name", {"conversation_id": "0", "name": "t"}),
    ("GET", "/api/chat/get_file?filename=nonexistent", None),
    ("POST", "/api/chat/post_file", None),
    ("GET", "/api/chat/get_attachment?attachment_id=0", None),
    # -- conversation --
    ("GET", "/api/conversation/list", None),
    ("GET", "/api/conversation/detail?id=0", None),
    # -- config —
    ("POST", "/api/config/get", {"keys": []}),
    ("GET", "/api/config/default", None),
    ("GET", "/api/config/abconfs", None),
    ("POST", "/api/config/abconf/new", {"name": "t", "config": {}}),
    ("GET", "/api/config/abconf?id=0", None),
    ("POST", "/api/config/abconf/delete", {"id": 0}),
    ("POST", "/api/config/abconf/update", {"id": 0, "config": {}}),
    ("GET", "/api/config/umo_abconf_routes", None),
    ("GET", "/api/config/provider/list", None),
    ("GET", "/api/config/provider/template", None),
    ("GET", "/api/config/platform/list", None),
    ("POST", "/api/config/platform/delete", {"id": 0}),
    ("GET", "/api/config/provider_sources/models", None),
    # -- persona —
    ("GET", "/api/persona/list", None),
    ("POST", "/api/persona/create", {"name": "t", "prompt": "test"}),
    ("GET", "/api/persona/detail?id=0", None),
    ("POST", "/api/persona/delete", {"id": 0}),
    # -- cron —
    ("GET", "/api/cron/jobs", None),
    # -- api key —
    ("GET", "/api/apikey/list", None),
    ("POST", "/api/apikey/create", {"name": "t", "scopes": ["chat:read"]}),
    ("POST", "/api/apikey/delete", {"id": 0}),
    # — platform —
    ("GET", "/api/platform/list", None),
    ("GET", "/api/platform/stats", None),
    # — knowledge base —
    ("GET", "/api/kb/list", None),
    ("POST", "/api/kb/create", {"name": "t"}),
    ("GET", "/api/kb/get?id=0", None),
    ("GET", "/api/kb/stats", None),
    # — skills —
    ("POST", "/api/skills/upload", None),
    # — tools / MCP —
    ("GET", "/api/tools/list", None),
    ("GET", "/api/tools/mcp/servers", None),
    ("POST", "/api/tools/toggle-tool", {"tool_name": "test", "enabled": False}),
    # — chatui project —
    ("GET", "/api/chatui_project/list", None),
    ("POST", "/api/chatui_project/create", {"title": "t"}),
    ("GET", "/api/chatui_project/get", None),
    ("POST", "/api/chatui_project/delete", {"id": 0}),
    # — stat —
    ("GET", "/api/stat/get", None),
    ("GET", "/api/stat/version", None),
    ("GET", "/api/stat/storage", None),
    ("GET", "/api/stat/changelog", None),
    # — update —
    ("GET", "/api/update/check", None),
    ("GET", "/api/update/releases", None),
    # — subagent —
    ("GET", "/api/subagent/config", None),
    # — session management —
    ("GET", "/api/session/groups", None),
    ("POST", "/api/session/group/create", {"name": "t"}),
    # — backup — (GET only; POST/DELETE need runtime IDs)
    ("GET", "/api/backup/list", None),
    ("GET", "/api/backup/progress", None),
    ("GET", "/api/backup/check", None),
    # — commands —
    ("GET", "/api/commands/conflicts", None),
    ("GET", "/api/commands/permission", None),
    # — live-log —
    ("GET", "/api/log-history", None),
]


def _route_id(params: tuple) -> str:
    """Return a short test-id for each parametrised row."""
    method, path, _ = params
    name = path.replace("/", "_").replace("?", "_").replace("=", "_")
    return f"{method.upper()}_{name}".rstrip("_")


# ===========================================================================
# Tests
# ===========================================================================
class TestAllRoutes:
    """Hit every registered route and assert no 500 / no crash."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,path,body", ROUTES, ids=_route_id)
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
        kwargs = {"headers": headers}

        if body is not None:
            kwargs["json"] = body

        resp = await client.open(path, method=method, **kwargs)
        assert resp.status_code != 500, (
            f"{method} {path} returned 500"
        )

    # ------------------------------------------------------------------
    # Live-log SSE needs a dedicated test (streaming response)
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_live_log_sse(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/live-log", headers=authenticated_header)
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"
