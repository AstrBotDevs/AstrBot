"""OAuth dashboard aliases must not expose secrets from provider failures."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.dashboard.api.providers import (
    complete_dashboard_alias_provider_source_openai_oauth,
    complete_provider_source_openai_oauth,
    disconnect_dashboard_alias_provider_source_openai_oauth,
    disconnect_provider_source_openai_oauth,
    refresh_dashboard_alias_provider_source_openai_oauth,
    refresh_provider_source_openai_oauth,
    start_dashboard_alias_provider_source_openai_oauth,
    start_provider_source_openai_oauth,
)
from astrbot.dashboard.responses import ApiError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "service_method", "expected_message"),
    [
        (
            start_dashboard_alias_provider_source_openai_oauth,
            "start_provider_source_openai_oauth",
            "OpenAI OAuth authorization could not be started",
        ),
        (
            complete_dashboard_alias_provider_source_openai_oauth,
            "complete_provider_source_openai_oauth",
            "OpenAI OAuth binding failed; check the authorization input",
        ),
        (
            refresh_dashboard_alias_provider_source_openai_oauth,
            "refresh_provider_source_openai_oauth",
            "OpenAI OAuth token refresh failed",
        ),
        (
            disconnect_dashboard_alias_provider_source_openai_oauth,
            "disconnect_provider_source_openai_oauth",
            "OpenAI OAuth disconnect failed",
        ),
    ],
)
async def test_oauth_alias_redacts_provider_value_error(
    handler, service_method, expected_message
):
    secret = "oauth-callback-code-and-token-secret"
    service_call = AsyncMock(side_effect=ValueError(f"Backend rejected {secret}"))
    service = SimpleNamespace(**{service_method: service_call})
    request = SimpleNamespace(
        json=AsyncMock(return_value={"source_id": "oauth", "input": secret})
    )

    result = await handler(request, _auth=None, service=service)

    assert service_call.await_count == 1
    assert result["status"] == "error"
    assert result["message"] == expected_message
    assert secret not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "service_method", "expected_message"),
    [
        (
            start_provider_source_openai_oauth,
            "start_provider_source_openai_oauth",
            "OpenAI OAuth authorization could not be started",
        ),
        (
            complete_provider_source_openai_oauth,
            "complete_provider_source_openai_oauth",
            "OpenAI OAuth binding failed; check the authorization input",
        ),
        (
            refresh_provider_source_openai_oauth,
            "refresh_provider_source_openai_oauth",
            "OpenAI OAuth token refresh failed",
        ),
        (
            disconnect_provider_source_openai_oauth,
            "disconnect_provider_source_openai_oauth",
            "OpenAI OAuth disconnect failed",
        ),
    ],
)
async def test_oauth_openapi_route_redacts_provider_value_error(
    handler, service_method, expected_message
):
    secret = "oauth-callback-code-and-token-secret"
    service_call = AsyncMock(side_effect=ValueError(f"Backend rejected {secret}"))
    service = SimpleNamespace(**{service_method: service_call})
    request = SimpleNamespace(
        json=AsyncMock(return_value={"source_id": "oauth", "input": secret})
    )

    with pytest.raises(ApiError) as raised:
        await handler(request, _auth=None, service=service)

    assert service_call.await_count == 1
    assert raised.value.status_code == 400
    assert raised.value.message == expected_message
    assert secret not in raised.value.message
