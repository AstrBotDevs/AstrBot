import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from astrbot.core.provider.oauth.openai_oauth_usage import QuotaReader


class Provider:
    base_url = "https://chatgpt.com/backend-api/codex/"

    def __init__(self):
        self.token = "secret-one"
        self.account = "private-account"
        self.provider_config = {"proxy": "http://proxy.example:8080"}

    def _build_backend_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "chatgpt-account-id": self.account,
        }


@pytest.fixture
def harness():
    provider = Provider()
    requests = []
    responses = []
    options = []
    now = [1_700_000_000.0]

    async def handler(request):
        requests.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response(request)
            if asyncio.iscoroutine(response):
                response = await response
        return response

    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs):
        options.append(kwargs)
        return httpx.AsyncClient(transport=transport)

    reader = QuotaReader(client_factory=client_factory, clock=lambda: now[0])
    return provider, reader, responses, requests, options, now


@pytest.mark.asyncio
async def test_success_normalizes_all_windows_and_whitelists_fields(harness):
    provider, reader, responses, requests, options, _ = harness
    responses.append(
        httpx.Response(
            200,
            json={
                "account_id": "private-account",
                "plan_type": "pro",
                "rate_limit": {
                    "limit_reached": False,
                    "primary_window": {
                        "used_percent": 56,
                        "limit_window_seconds": 604800,
                        "reset_at": 1700604800,
                    },
                    "secondary_window": {
                        "used_percent": 10,
                        "limit_window_seconds": 18000,
                        "reset_at": 1700018000,
                    },
                },
                "additional_rate_limits": [
                    {
                        "limit_name": "Luna",
                        "metered_feature": "codex_luna",
                        "rate_limit": {
                            "primary_window": {
                                "used_percent": 25,
                                "limit_window_seconds": 3600,
                                "reset_at": 1700003600,
                            }
                        },
                    }
                ],
                "credits": {"has_credits": True, "unlimited": False, "balance": "4.50"},
                "untrusted": "do-not-emit",
            },
        )
    )
    result = await reader.read(provider)
    assert result == {
        "status": "success",
        "observed_at": datetime.fromtimestamp(1700000000, timezone.utc).isoformat(),
        "cached": False,
        "plan_type": "pro",
        "windows": [
            {
                "bucket": "primary",
                "limit_id": "codex",
                "name": None,
                "used_percent": 56.0,
                "remaining_percent": 44.0,
                "window_seconds": 604800,
                "reset_at": 1700604800,
            },
            {
                "bucket": "secondary",
                "limit_id": "codex",
                "name": None,
                "used_percent": 10.0,
                "remaining_percent": 90.0,
                "window_seconds": 18000,
                "reset_at": 1700018000,
            },
            {
                "bucket": "primary",
                "limit_id": "codex_luna",
                "name": "Luna",
                "used_percent": 25.0,
                "remaining_percent": 75.0,
                "window_seconds": 3600,
                "reset_at": 1700003600,
            },
        ],
        "limit_reached": False,
        "credits": {"has_credits": True, "unlimited": False, "balance": "4.50"},
    }
    assert requests[0].method == "GET"
    assert str(requests[0].url) == "https://chatgpt.com/backend-api/wham/usage"
    assert requests[0].headers["authorization"] == "Bearer secret-one"
    assert requests[0].headers["accept"] == "application/json"
    assert options == [
        {
            "proxy": "http://proxy.example:8080",
            "timeout": 15.0,
            "trust_env": False,
            "follow_redirects": False,
        }
    ]
    assert "private-account" not in repr(result)
    await reader.close()


@pytest.mark.asyncio
async def test_cache_expiry_and_credential_rotation(harness):
    provider, reader, responses, requests, _, now = harness
    responses.extend([httpx.Response(200, json={"plan_type": "pro"}) for _ in range(3)])
    first = await reader.read(provider)
    cached = await reader.read(provider)
    assert cached["cached"] is True
    assert cached["observed_at"] == first["observed_at"]
    assert len(requests) == 1
    provider.token = "secret-two"
    changed = await reader.read(provider)
    assert changed["cached"] is False
    assert len(requests) == 2
    now[0] += 61
    expired = await reader.read(provider)
    assert expired["cached"] is False
    assert len(requests) == 3
    await reader.close()


@pytest.mark.asyncio
async def test_cache_is_immutable_to_caller_and_clock_rewind_refetches(harness):
    provider, reader, responses, requests, _, now = harness
    responses.extend(
        [
            httpx.Response(
                200, json={"rate_limit": {"primary_window": {"used_percent": 2}}}
            )
            for _ in range(2)
        ]
    )
    first = await reader.read(provider)
    first["windows"][0]["used_percent"] = 99
    cached = await reader.read(provider)
    assert cached["windows"][0]["used_percent"] == 2
    cached["windows"].clear()
    now[0] -= 1
    refetched = await reader.read(provider)
    assert refetched["cached"] is False
    assert len(refetched["windows"]) == 1
    assert len(requests) == 2
    await reader.close()


@pytest.mark.asyncio
async def test_concurrent_readers_share_one_request(harness):
    provider, reader, responses, requests, _, _ = harness
    responses.append(
        httpx.Response(
            200, json={"rate_limit": {"primary_window": {"used_percent": 2}}}
        )
    )
    results = await asyncio.gather(*(reader.read(provider) for _ in range(8)))
    assert len(requests) == 1
    assert all(result["windows"][0]["remaining_percent"] == 98 for result in results)
    await reader.close()


@pytest.mark.asyncio
async def test_empty_and_malformed_fields_do_not_turn_into_zero(harness):
    provider, reader, responses, _, _, _ = harness
    responses.append(
        httpx.Response(
            200,
            text=json.dumps(
                {
                    "plan_type": 4,
                    "rate_limit": {
                        "limit_reached": "false",
                        "primary_window": {
                            "used_percent": True,
                            "reset_at": float("nan"),
                        },
                    },
                    "credits": {"has_credits": 1, "balance": {"bad": "value"}},
                }
            ),
        )
    )
    result = await reader.read(provider)
    assert result["plan_type"] is None
    assert result["limit_reached"] is None
    assert result["windows"][0]["used_percent"] is None
    assert result["windows"][0]["remaining_percent"] is None
    assert result["windows"][0]["reset_at"] is None
    assert result["credits"] == {
        "has_credits": None,
        "unlimited": None,
        "balance": None,
    }
    await reader.close()


@pytest.mark.asyncio
async def test_rejects_other_base_url_before_network(harness):
    provider, reader, _, requests, _, _ = harness
    provider.base_url = "https://example.invalid/backend-api/codex"
    result = await reader.read(provider)
    assert result["status"] == "unsupported_endpoint"
    assert requests == []
    await reader.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [
        (401, "reauth_required"),
        (403, "forbidden"),
        (429, "rate_limited"),
        (503, "unavailable"),
    ],
)
async def test_http_errors_are_distinct_and_hide_body(harness, status, code):
    provider, reader, responses, _, _, _ = harness
    responses.append(httpx.Response(status, text="secret-body-token"))
    result = await reader.read(provider)
    assert result["status"] == code
    assert result["http_status"] == status
    assert "secret-body-token" not in repr(result)
    await reader.close()


@pytest.mark.asyncio
async def test_invalid_json_and_network_error_are_distinct(harness):
    provider, reader, responses, _, _, _ = harness
    responses.append(httpx.Response(200, text="secret-body-token"))
    result = await reader.read(provider)
    assert result["status"] == "unparseable"
    assert "secret-body-token" not in repr(result)
    responses.append(httpx.ConnectError("secret-network-url"))
    result = await reader.read(provider)
    assert result["status"] == "unavailable"
    assert "secret-network-url" not in repr(result)
    await reader.close()


@pytest.mark.asyncio
async def test_close_rejects_new_reads(harness):
    provider, reader, _, requests, _, _ = harness
    await reader.close()
    result = await reader.read(provider)
    assert result["status"] == "closed"
    assert requests == []


@pytest.mark.asyncio
async def test_unbound_credentials_never_send_request(harness):
    provider, reader, _, requests, _, _ = harness
    provider.token = ""
    result = await reader.read(provider)
    assert result["status"] == "unbound"
    assert requests == []
    await reader.close()


@pytest.mark.asyncio
async def test_rotation_during_request_discards_old_account_result(harness):
    provider, reader, responses, requests, _, _ = harness

    def rotate(_request):
        provider.account = "new-account"
        return httpx.Response(200, json={"plan_type": "old"})

    responses.extend([rotate, httpx.Response(200, json={"plan_type": "new"})])
    result = await reader.read(provider)
    assert result["plan_type"] == "new"
    assert len(requests) == 2
    assert requests[1].headers["chatgpt-account-id"] == "new-account"
    await reader.close()


@pytest.mark.asyncio
async def test_close_during_request_returns_closed_without_snapshot(harness):
    provider, reader, responses, _, _, _ = harness
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed(_request):
        started.set()
        await release.wait()
        return httpx.Response(200, json={"plan_type": "pro"})

    responses.append(delayed)
    read_task = asyncio.create_task(reader.read(provider))
    await started.wait()
    close_task = asyncio.create_task(reader.close())
    await asyncio.sleep(0)
    release.set()
    assert await read_task == {"status": "closed"}
    await close_task
