"""Comprehensive API smoke tests for all dashboard routes.

Covers CRUD operations for every registered API endpoint.
Created after a merge broke multiple routes silently — these tests
ensure the server starts and all routes respond without 500 errors.
"""

import pytest
import pytest_asyncio
from quart import Quart


# ===========================================================================
# Chat
# ===========================================================================
class TestChatApi:
    async def _list_sessions(self, app, auth) -> list[dict]:
        client = app.test_client()
        resp = await client.get("/api/chat/sessions", headers=auth)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)
        return data["data"]

    @pytest.mark.asyncio
    async def test_list_sessions(self, app: Quart, authenticated_header: dict):
        sessions = await self._list_sessions(app, authenticated_header)
        assert isinstance(sessions, list)

    @pytest.mark.asyncio
    async def test_new_session(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.post("/api/chat/new_session", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)

    @pytest.mark.asyncio
    async def test_get_session(self, app: Quart, authenticated_header: dict):
        sessions = await self._list_sessions(app, authenticated_header)
        if not sessions:
            pytest.skip("No sessions available")
        sid = sessions[0]["conversation_id"]
        client = app.test_client()
        resp = await client.get(
            f"/api/chat/get_session?conversation_id={sid}",
            headers=authenticated_header,
        )
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)

    @pytest.mark.asyncio
    async def test_stop_session(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.post("/api/chat/stop", headers=authenticated_header)
        data = await resp.get_json()
        # Stop may succeed or be a no-op; should not 500
        assert "status" in data


# ===========================================================================
# Conversation
# ===========================================================================
class TestConversationApi:
    @pytest.mark.asyncio
    async def test_list_conversations(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/conversation/list", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)

    @pytest.mark.asyncio
    async def test_conversation_crud(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        # detail with no id should return error but not 500
        resp = await client.get(
            "/api/conversation/detail", headers=authenticated_header
        )
        assert resp.status_code != 500


# ===========================================================================
# File
# ===========================================================================
class TestFileApi:
    @pytest.mark.asyncio
    async def test_file_post_file(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.post(
            "/api/chat/post_file",
            headers=authenticated_header,
            data={},
        )
        # Expected: missing file returns error (not 500)
        assert resp.status_code != 500

    @pytest.mark.asyncio
    async def test_file_get_file(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get(
            "/api/chat/get_file?filename=nonexistent",
            headers=authenticated_header,
        )
        assert resp.status_code != 500


# ===========================================================================
# Config
# ===========================================================================
class TestConfigApi:
    @pytest.mark.asyncio
    async def test_get_config(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.post(
            "/api/config/get",
            json={"keys": ["provider_settings"]},
            headers=authenticated_header,
        )
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)

    @pytest.mark.asyncio
    async def test_abconf_list(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/config/abconfs", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)


# ===========================================================================
# Persona
# ===========================================================================
class TestPersonaApi:
    @pytest.mark.asyncio
    async def test_list_personas(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/persona/list", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)

    @pytest.mark.asyncio
    async def test_persona_crud(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.post(
            "/api/persona/create",
            json={"name": "test-persona", "prompt": "You are a test assistant."},
            headers=authenticated_header,
        )
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)
        persona_id = data["data"].get("id") or data["data"].get("persona_id")

        if persona_id:
            resp = await client.get(
                f"/api/persona/detail?id={persona_id}",
                headers=authenticated_header,
            )
            data = await resp.get_json()
            assert data["status"] == "ok", str(data)

            resp = await client.post(
                f"/api/persona/delete",
                json={"id": persona_id},
                headers=authenticated_header,
            )
            data = await resp.get_json()
            assert data["status"] == "ok", str(data)


# ===========================================================================
# Cron
# ===========================================================================
class TestCronApi:
    @pytest.mark.asyncio
    async def test_list_cron_jobs(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/cron/jobs", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)


# ===========================================================================
# ApiKey
# ===========================================================================
class TestApiKeyApi:
    @pytest.mark.asyncio
    async def test_apikey_crud(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/apikey/list", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)

        resp = await client.post(
            "/api/apikey/create",
            json={"name": "test-key", "scopes": ["chat:read"]},
            headers=authenticated_header,
        )
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)
        key_id = data["data"].get("id")

        if key_id:
            resp = await client.post(
                "/api/apikey/delete",
                json={"id": key_id},
                headers=authenticated_header,
            )
            data = await resp.get_json()
            assert data["status"] == "ok", str(data)


# ===========================================================================
# Platform
# ===========================================================================
class TestPlatformApi:
    @pytest.mark.asyncio
    async def test_platform_list(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/platform/list", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)


# ===========================================================================
# KnowledgeBase
# ===========================================================================
class TestKnowledgeBaseApi:
    @pytest.mark.asyncio
    async def test_kb_list(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/kb/list", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)

    @pytest.mark.asyncio
    async def test_kb_crud(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.post(
            "/api/kb/create",
            json={"name": "test-kb", "description": "test"},
            headers=authenticated_header,
        )
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)
        kb_id = data["data"].get("id")

        if kb_id:
            resp = await client.get(
                f"/api/kb/get?id={kb_id}",
                headers=authenticated_header,
            )
            data = await resp.get_json()
            assert data["status"] == "ok", str(data)


# ===========================================================================
# Skills
# ===========================================================================
class TestSkillsApi:
    @pytest.mark.asyncio
    async def test_skills_upload_no_file(
        self, app: Quart, authenticated_header: dict
    ):
        client = app.test_client()
        resp = await client.post(
            "/api/skills/upload",
            headers=authenticated_header,
            data={},
        )
        # No file provided — should return error, not 500
        assert resp.status_code != 500


# ===========================================================================
# Tools / MCP
# ===========================================================================
class TestToolsApi:
    @pytest.mark.asyncio
    async def test_tools_list(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/tools/list", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)

    @pytest.mark.asyncio
    async def test_mcp_servers_list(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/tools/mcp/servers", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)


# ===========================================================================
# ChatUI Project
# ===========================================================================
class TestChatUIProjectApi:
    @pytest.mark.asyncio
    async def test_project_list(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get(
            "/api/chatui_project/list", headers=authenticated_header
        )
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)

    @pytest.mark.asyncio
    async def test_project_crud(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.post(
            "/api/chatui_project/create",
            json={"title": "test-project"},
            headers=authenticated_header,
        )
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)
        project_id = data["data"].get("id")

        if project_id:
            resp = await client.get(
                f"/api/chatui_project/get?id={project_id}",
                headers=authenticated_header,
            )
            data = await resp.get_json()
            assert data["status"] == "ok", str(data)


# ===========================================================================
# Live-Log SSE
# ===========================================================================
class TestLiveLogApi:
    @pytest.mark.asyncio
    async def test_live_log_returns_stream(
        self, app: Quart, authenticated_header: dict
    ):
        client = app.test_client()
        resp = await client.get("/api/live-log", headers=authenticated_header)
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"

    @pytest.mark.asyncio
    async def test_log_history(self, app: Quart, authenticated_header: dict):
        client = app.test_client()
        resp = await client.get("/api/log-history", headers=authenticated_header)
        data = await resp.get_json()
        assert data["status"] == "ok", str(data)
