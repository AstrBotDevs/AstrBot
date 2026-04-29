"""Tests for the config route module.

Covers import smoke tests for ``ConfigRoute`` and its helper functions,
plus endpoint smoke tests for config CRUD and listing operations.
"""

import pytest

from astrbot.dashboard.routes.config import (
    ConfigRoute,
    _expect_type,
    _log_computer_config_changes,
    _resolve_path,
    _validate_template_list,
    save_config,
    try_cast,
    validate_config,
)


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

def test_config_route_class():
    assert ConfigRoute is not None


def test_save_config_is_callable():
    assert callable(save_config)


def test_validate_config_is_callable():
    assert callable(validate_config)


def test_try_cast_is_callable():
    assert callable(try_cast)


def test_try_cast_int():
    assert try_cast("42", "int") == 42
    assert try_cast("abc", "int") is None


def test_try_cast_float():
    assert try_cast("3.14", "float") == 3.14
    assert try_cast("abc", "float") is None


def test_expect_type_is_callable():
    assert callable(_expect_type)


def test_expect_type_passes():
    errors: list[str] = []
    result = _expect_type("hello", str, "test.key", errors)
    assert result is True
    assert errors == []


def test_expect_type_fails():
    errors: list[str] = []
    result = _expect_type(42, str, "test.key", errors)
    assert result is False
    assert len(errors) == 1


def test_validate_template_list_is_callable():
    assert callable(_validate_template_list)


def test_log_computer_config_changes_is_callable():
    assert callable(_log_computer_config_changes)


def test_resolve_path_is_callable():
    assert callable(_resolve_path)


# ---------------------------------------------------------------------------
# Endpoint tests - AstrBot config (abconf) CRUD
# ---------------------------------------------------------------------------

class TestAbConfCRUD:
    """CRUD tests for the ``/config/abconf*`` endpoints."""

    @pytest.mark.asyncio
    async def test_get_abconf_list(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/config/abconfs",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")
        if data["status"] == "ok":
            assert "info_list" in data["data"]

    @pytest.mark.asyncio
    async def test_get_default_config(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/config/default",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")
        if data["status"] == "ok":
            assert "config" in data["data"]
            assert "metadata" in data["data"]

    @pytest.mark.asyncio
    async def test_get_abconf_by_id(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/config/abconf?id=nonexistent",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_create_abconf(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/config/abconf/new",
            headers=authenticated_header,
            json={"name": "pytest-conf", "config": {}},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_delete_abconf(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/config/abconf/delete",
            headers=authenticated_header,
            json={"id": "nonexistent"},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_update_abconf(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/config/abconf/update",
            headers=authenticated_header,
            json={"id": "nonexistent", "name": "renamed"},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")


# ---------------------------------------------------------------------------
# Endpoint tests - platform / provider listing
# ---------------------------------------------------------------------------

class TestConfigListingEndpoints:
    """Read-only endpoint tests for platform and provider config."""

    @pytest.mark.asyncio
    async def test_get_platform_list(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/config/platform/list",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")
        if data["status"] == "ok":
            assert "platforms" in data["data"]

    @pytest.mark.asyncio
    async def test_get_provider_template(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/config/provider/template",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")
        if data["status"] == "ok":
            assert "config_schema" in data["data"]
            assert "providers" in data["data"]

    @pytest.mark.asyncio
    async def test_get_umo_abconf_routes(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/config/umo_abconf_routes",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_get_provider_list(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/config/provider/list?provider_type=chat_completion",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_get_provider_sources_models(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/config/provider_sources/models",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")


# ---------------------------------------------------------------------------
# Endpoint tests - UMOP config router
# ---------------------------------------------------------------------------

class TestUCRouteEndpoints:
    """Endpoint tests for the UMOP config router endpoints."""

    @pytest.mark.asyncio
    async def test_update_ucr_all_missing_data(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/config/umo_abconf_route/update_all",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_update_ucr_missing_fields(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/config/umo_abconf_route/update",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_delete_ucr_missing_umo(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/config/umo_abconf_route/delete",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"
