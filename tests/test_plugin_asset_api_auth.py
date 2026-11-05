"""Plugin asset JWTs must not authenticate general dashboard APIs."""

import time
from types import SimpleNamespace

import jwt
import pytest
from starlette.requests import Request

from astrbot.dashboard.api.auth import require_dashboard_user, require_scope
from astrbot.dashboard.plugin_page_auth import PLUGIN_PAGE_TOKEN_TYPE
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.services.auth_service import DASHBOARD_JWT_COOKIE_NAME


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["bearer", "cookie"])
@pytest.mark.parametrize("dependency", ["dashboard", "scope"])
@pytest.mark.parametrize("asset_token", [True, False])
async def test_resource_token_cannot_authenticate_api(
    transport: str, dependency: str, asset_token: bool
) -> None:
    """Reject correctly signed asset tokens while preserving login JWTs."""
    secret = "test-secret-with-at-least-32-bytes"
    payload = {"username": "admin", "exp": int(time.time()) + 300}
    if asset_token:
        payload.update(
            token_type=PLUGIN_PAGE_TOKEN_TYPE,
            purpose="page_session",
            plugin_name="example",
            page_name="index",
        )
    token = jwt.encode(payload, secret, algorithm="HS256")
    header = (
        (b"authorization", f"Bearer {token}".encode())
        if transport == "bearer"
        else (b"cookie", f"{DASHBOARD_JWT_COOKIE_NAME}={token}".encode())
    )
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/auth/account",
            "query_string": b"",
            "headers": [header],
            "app": SimpleNamespace(state=SimpleNamespace(jwt_secret=secret)),
        }
    )
    if asset_token:
        with pytest.raises(ApiError) as error:
            if dependency == "dashboard":
                await require_dashboard_user(request)
            else:
                await require_scope(request, "system")
        assert error.value.status_code == 401
    elif dependency == "dashboard":
        assert await require_dashboard_user(request) == "admin"
    else:
        context = await require_scope(request, "system")
        assert context.username == "admin"
        assert context.scopes == ["*"]
