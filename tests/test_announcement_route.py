"""End-to-end HTTP route tests for the announcement endpoint.

These tests exercise the *full* FastAPI request lifecycle, not just the service
layer. They exist to pin the legacy endpoint's URL prefix (``/api/system``)
because the frontend hard-codes it.

Without these tests, a refactor that re-mounts the handler on a router with
the wrong prefix (e.g. ``/api/update``) would silently 404 in the browser.
"""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrbot.dashboard.api.auth import require_dashboard_user
from astrbot.dashboard.api.updates import (
    get_service,
    system_announcement_legacy_router,
)
from astrbot.dashboard.services.update_service import (
    UpdateServiceError,
    UpdateServiceResult,
)


def _build_isolated_app(stub_service: MagicMock) -> FastAPI:
    """Build a minimal FastAPI app with just the announcement router mounted.

    Isolating the router (vs. using the full app) keeps the test fast and
    avoids pulling in services that have nothing to do with announcements.
    """
    app = FastAPI()
    app.include_router(system_announcement_legacy_router)
    app.dependency_overrides[get_service] = lambda: stub_service
    app.dependency_overrides[require_dashboard_user] = lambda: "test_user"
    return app


def test_legacy_announcement_route_lives_at_api_system_announcement() -> None:
    """The legacy path the frontend calls (``/api/system/announcement``) is served.

    Regression guard: previously the handler was mounted on
    ``legacy_router`` (prefix ``/api/update``), making the actual path
    ``/api/update/system/announcement`` and causing 404s in the dashboard UI.
    """
    stub_service = MagicMock()

    async def fake_get_announcement():
        return UpdateServiceResult(
            status="success",
            data={"title": "hi", "content": "body", "enabled": True, "version": 1},
        )

    stub_service.get_announcement = fake_get_announcement
    client = TestClient(_build_isolated_app(stub_service))

    response = client.get("/api/system/announcement")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"] == {
        "title": "hi",
        "content": "body",
        "enabled": True,
        "version": 1,
    }


def test_legacy_announcement_route_passes_through_404() -> None:
    """Upstream "no announcement" (404) bubbles up as 404, not 200.

    The frontend hides the bar on every non-200 response, but the 404 status
    code is also the explicit signal that there is no announcement to show.
    """
    stub_service = MagicMock()

    async def fake_get_announcement():
        raise UpdateServiceError("当前没有公告")

    stub_service.get_announcement = fake_get_announcement
    client = TestClient(_build_isolated_app(stub_service))

    response = client.get("/api/system/announcement")

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "error"
    assert "没有公告" in body["message"]


def test_legacy_announcement_route_maps_other_errors_to_502() -> None:
    """Non-404 errors (network / 5xx / parse) become HTTP 502."""
    stub_service = MagicMock()

    async def fake_get_announcement():
        raise UpdateServiceError("无法连接更新服务器: dns failed")

    stub_service.get_announcement = fake_get_announcement
    client = TestClient(_build_isolated_app(stub_service))

    response = client.get("/api/system/announcement")

    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "error"
    assert "无法连接" in body["message"]


def test_legacy_announcement_route_is_not_under_api_update() -> None:
    """Explicit anti-regression: the route must NOT resolve at /api/update/*.

    If a future refactor re-mounts the handler on legacy_router again, this
    test fires before the dashboard UI can be hit in production.
    """
    stub_service = MagicMock()

    async def fake_get_announcement():
        return UpdateServiceResult(status="success", data={})

    stub_service.get_announcement = fake_get_announcement
    client = TestClient(_build_isolated_app(stub_service))

    # The previous-bug URL must NOT resolve. Anything in the 2xx/4xx/5xx range
    # is fine; we only assert that it isn't a 200 carrying announcement data.
    wrong_path = client.get("/api/update/system/announcement")
    assert wrong_path.status_code != 200 or "data" not in wrong_path.json()
