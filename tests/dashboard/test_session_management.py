"""Tests for the session management route module.

Covers import smoke tests for ``SessionManagementRoute`` and key
session-level CRUD / group endpoints.
"""

import pytest

from astrbot.dashboard.routes.session_management import (
    AVAILABLE_SESSION_RULE_KEYS,
    SessionManagementRoute,
)


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

def test_session_management_route_class():
    assert SessionManagementRoute is not None


def test_available_session_rule_keys():
    assert isinstance(AVAILABLE_SESSION_RULE_KEYS, list)
    assert len(AVAILABLE_SESSION_RULE_KEYS) > 0
    assert "session_service_config" in AVAILABLE_SESSION_RULE_KEYS
    assert "session_plugin_config" in AVAILABLE_SESSION_RULE_KEYS


# ---------------------------------------------------------------------------
# Endpoint tests - session groups
# ---------------------------------------------------------------------------

class TestSessionGroupCRUD:
    """CRUD tests for the ``/session/group/*`` endpoints."""

    GROUP_PAYLOAD = {"name": "pytest-group", "umos": []}

    @pytest.mark.asyncio
    async def test_list_groups(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get("/api/session/groups", headers=authenticated_header)
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")
        if data["status"] == "ok":
            assert "groups" in data["data"]

    @pytest.mark.asyncio
    async def test_create_group(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/session/group/create",
            headers=authenticated_header,
            json=self.GROUP_PAYLOAD,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_update_group(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/session/group/update",
            headers=authenticated_header,
            json={"id": "nonexistent", "name": "renamed-group"},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_delete_group(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/session/group/delete",
            headers=authenticated_header,
            json={"id": "nonexistent"},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_create_group_empty_name(self, app, authenticated_header):
        """Creating a group with an empty name should produce a non-500 error."""
        client = app.test_client()
        resp = await client.post(
            "/api/session/group/create",
            headers=authenticated_header,
            json={"name": "", "umos": []},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# Endpoint tests - session rules
# ---------------------------------------------------------------------------

class TestSessionRuleEndpoints:
    """Endpoint tests for the ``/session/*-rule`` endpoints."""

    @pytest.mark.asyncio
    async def test_list_session_rules(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/session/list-rule",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")
        if data["status"] == "ok":
            assert "rules" in data["data"]
            assert "available_rule_keys" in data["data"]
            assert "available_personas" in data["data"]
            assert "available_chat_providers" in data["data"]

    @pytest.mark.asyncio
    async def test_update_rule_missing_umo(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/session/update-rule",
            headers=authenticated_header,
            json={"rule_key": "session_service_config", "rule_value": {}},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_update_rule_invalid_key(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/session/update-rule",
            headers=authenticated_header,
            json={
                "umo": "test:private:123",
                "rule_key": "invalid_key_xyz",
                "rule_value": {},
            },
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_delete_rule(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/session/delete-rule",
            headers=authenticated_header,
            json={"umo": "test:private:999"},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_batch_delete_rule_missing_params(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/session/batch-delete-rule",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# Endpoint tests - session status / UMOS
# ---------------------------------------------------------------------------

class TestSessionStatusEndpoints:
    """Endpoint tests for session status and UMO listing endpoints."""

    @pytest.mark.asyncio
    async def test_active_umos(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/session/active-umos",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_list_all_with_status(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/session/list-all-with-status",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")
        if data["status"] == "ok":
            assert "sessions" in data["data"]
            assert "total" in data["data"]

    @pytest.mark.asyncio
    async def test_batch_update_service_missing_params(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/session/batch-update-service",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_batch_update_provider_missing_params(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/session/batch-update-provider",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"
