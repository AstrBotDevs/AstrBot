import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import astrbot.core.provider.sources.openai_oauth_source as oauth_source
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.oauth.openai_oauth import parse_oauth_credential_json
from astrbot.core.provider.oauth.openai_oauth_shared_state import (
    OpenAIOAuthSharedState,
)
from astrbot.core.provider.sources.openai_oauth_source import ProviderOpenAIOAuth


def _jwt_with_claims(claims: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict) -> str:
        data = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    return f"{encode(header)}.{encode(claims)}."


def _make_provider(
    overrides: dict | None = None,
    *,
    persist_callback=None,
    shared_state: OpenAIOAuthSharedState | None = None,
) -> ProviderOpenAIOAuth:
    provider_config = {
        "id": "test-openai-oauth",
        "type": "openai_oauth_chat_completion",
        "model": "gpt-5.4",
        "oauth_access_token": "test-token",
        "oauth_refresh_token": "test-refresh",
        "oauth_account_id": "test-account",
    }
    if overrides:
        provider_config.update(overrides)
    if persist_callback is not None:
        provider_config["oauth_persist_callback"] = persist_callback
    if shared_state is not None:
        provider_config["oauth_shared_state"] = shared_state
    return ProviderOpenAIOAuth(
        provider_config=provider_config,
        provider_settings={},
    )


def _make_provider_manager_for_oauth_source() -> ProviderManager:
    manager = ProviderManager.__new__(ProviderManager)
    manager.provider_sources_config = [
        {
            "id": "openai_oauth",
            "type": "openai_oauth_chat_completion",
            "provider": "openai",
            "provider_type": "chat_completion",
            "auth_mode": "openai_oauth",
            "api_base": "https://chatgpt.com/backend-api/codex",
            "proxy": "http://source-proxy.local",
            "oauth_access_token": "source-access",
            "oauth_refresh_token": "source-refresh",
            "oauth_expires_at": "2026-07-22T16:58:10+00:00",
            "oauth_account_id": "source-account",
        }
    ]
    manager._openai_oauth_shared_states = {}
    return manager


def test_runtime_configs_share_source_oauth_state_and_credentials():
    manager = _make_provider_manager_for_oauth_source()
    stale_model_fields = {
        "provider_source_id": "openai_oauth",
        "type": "openai_oauth_chat_completion",
        "provider": "openai",
        "provider_type": "chat_completion",
        "enable": True,
        "auth_mode": "manual",
        "api_base": "https://wrong.example/v1",
        "proxy": "http://wrong-proxy.local",
        "oauth_access_token": "stale-access",
        "oauth_refresh_token": "stale-refresh",
    }

    sol = manager.get_merged_provider_config(
        {
            **stale_model_fields,
            "id": "openai_oauth/gpt-5.6-sol",
            "model": "gpt-5.6-sol",
        },
        runtime=True,
    )
    terra = manager.get_merged_provider_config(
        {
            **stale_model_fields,
            "id": "openai_oauth/gpt-5.6-terra",
            "model": "gpt-5.6-terra",
        },
        runtime=True,
    )

    assert sol["oauth_shared_state"] is terra["oauth_shared_state"]
    assert sol["api_base"] == "https://chatgpt.com/backend-api/codex"
    assert sol["proxy"] == "http://source-proxy.local"
    assert sol["oauth_access_token"] == "source-access"
    assert sol["oauth_refresh_token"] == "source-refresh"


def test_oauth_model_config_preserves_model_fields_while_source_credentials_win():
    manager = _make_provider_manager_for_oauth_source()

    merged = manager.get_merged_provider_config(
        {
            "id": "openai_oauth/gpt-future-codex",
            "provider_source_id": "openai_oauth",
            "model": "gpt-future-codex",
            "max_context_tokens": 196000,
            "reasoning": {"effort": "high", "summary": "detailed"},
            "future_model_level_option": {"enabled": True},
            "oauth_access_token": "stale-access",
            "oauth_refresh_token": "stale-refresh",
            "oauth_expires_at": "2000-01-01T00:00:00+00:00",
            "oauth_account_id": "stale-account",
        }
    )

    assert merged["max_context_tokens"] == 196000
    assert merged["reasoning"] == {"effort": "high", "summary": "detailed"}
    assert merged["future_model_level_option"] == {"enabled": True}
    assert merged["oauth_access_token"] == "source-access"
    assert merged["oauth_refresh_token"] == "source-refresh"
    assert merged["oauth_expires_at"] == "2026-07-22T16:58:10+00:00"
    assert merged["oauth_account_id"] == "source-account"


def test_manual_source_cannot_be_overridden_by_stale_model_oauth_fields():
    manager = _make_provider_manager_for_oauth_source()
    manager.provider_sources_config[0].update(
        {
            "auth_mode": "manual",
            "oauth_access_token": "",
            "oauth_refresh_token": "",
            "oauth_expires_at": "",
            "oauth_account_id": "",
        }
    )

    merged = manager.get_merged_provider_config(
        {
            "id": "openai_oauth/gpt-5.6-sol",
            "provider_source_id": "openai_oauth",
            "model": "gpt-5.6-sol",
            "enable": True,
            "auth_mode": "openai_oauth",
            "oauth_access_token": "stale-access",
            "oauth_refresh_token": "stale-refresh",
            "oauth_account_id": "stale-account",
        },
        runtime=True,
    )

    assert merged["auth_mode"] == "manual"
    assert merged["oauth_access_token"] == ""
    assert merged["oauth_refresh_token"] == ""
    assert merged["oauth_account_id"] == ""
    assert "oauth_shared_state" not in merged


def test_replacing_shared_oauth_source_clears_removed_credentials():
    manager = _make_provider_manager_for_oauth_source()
    state = manager.get_openai_oauth_shared_state(
        "openai_oauth",
        manager.provider_sources_config[0],
    )

    manager.replace_openai_oauth_shared_state(
        "openai_oauth",
        {
            "id": "openai_oauth",
            "type": "openai_chat_completion",
            "provider": "openai",
            "provider_type": "chat_completion",
            "auth_mode": "manual",
        },
    )

    snapshot = state.snapshot()
    assert snapshot["auth_mode"] == "manual"
    assert snapshot["oauth_access_token"] == ""
    assert snapshot["oauth_refresh_token"] == ""
    assert snapshot["oauth_expires_at"] == ""
    assert snapshot["oauth_account_id"] == ""


def test_dropping_shared_oauth_source_clears_cached_state():
    manager = _make_provider_manager_for_oauth_source()
    state = manager.get_openai_oauth_shared_state(
        "openai_oauth",
        manager.provider_sources_config[0],
    )

    manager.drop_openai_oauth_shared_state("openai_oauth")

    snapshot = state.snapshot()
    assert snapshot["oauth_access_token"] == ""
    assert snapshot["oauth_refresh_token"] == ""
    assert snapshot["oauth_account_id"] == ""


@pytest.mark.asyncio
async def test_oauth_provider_keeps_access_token_out_of_key_pool():
    provider = _make_provider()
    try:
        assert provider.get_keys() == ["__openai_oauth__"]
        assert provider.get_current_key() == "__openai_oauth__"
        assert provider.provider_config["oauth_access_token"] == "test-token"
        assert provider.chosen_api_key == ""
    finally:
        await provider.terminate()


def test_parse_codex_auth_json_tokens_object():
    access_token = _jwt_with_claims(
        {
            "email": "codex@example.com",
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acc_codex",
            },
        }
    )
    id_token = _jwt_with_claims({"email": "fallback@example.com"})
    raw = json.dumps(
        {
            "tokens": {
                "access_token": access_token,
                "refresh_token": "refresh-token",
                "id_token": id_token,
                "expires_at": "2026-05-07T12:00:00Z",
            }
        }
    )

    parsed = parse_oauth_credential_json(raw)

    assert parsed is not None
    assert parsed["access_token"] == access_token
    assert parsed["refresh_token"] == "refresh-token"
    assert parsed["expires_at"] == "2026-05-07T12:00:00+00:00"
    assert parsed["email"] == "codex@example.com"
    assert parsed["account_id"] == "acc_codex"


@pytest.mark.asyncio
async def test_ensure_fresh_oauth_token_refreshes_and_persists(monkeypatch):
    persisted: list[dict] = []

    async def persist_callback(patch: dict):
        persisted.append(patch)

    async def fake_refresh(refresh_token: str, proxy_url: str = ""):
        assert refresh_token == "test-refresh"
        assert proxy_url == "http://proxy.local"
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "email": "new@example.com",
            "account_id": "new-account",
        }

    monkeypatch.setattr(oauth_source, "refresh_access_token", fake_refresh)
    provider = _make_provider(
        {
            "proxy": "http://proxy.local",
            "oauth_expires_at": (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat(),
        },
        persist_callback=persist_callback,
    )
    try:
        await provider._ensure_fresh_oauth_token()

        assert provider.provider_config["oauth_access_token"] == "new-access"
        assert provider.provider_config["oauth_refresh_token"] == "new-refresh"
        assert provider.account_id == "new-account"
        assert provider.chosen_api_key == ""
        assert persisted == [
            {
                "auth_mode": "openai_oauth",
                "oauth_provider": "openai",
                "oauth_access_token": "new-access",
                "oauth_refresh_token": "new-refresh",
                "oauth_expires_at": provider.provider_config["oauth_expires_at"],
                "oauth_account_email": "new@example.com",
                "oauth_account_id": "new-account",
            }
        ]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_shared_oauth_state_refreshes_once_across_provider_instances(
    monkeypatch,
):
    expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    shared_state = OpenAIOAuthSharedState(
        "openai_oauth",
        {
            "oauth_access_token": "expired-access",
            "oauth_refresh_token": "shared-refresh",
            "oauth_expires_at": expires_at,
            "oauth_account_id": "shared-account",
        },
    )
    calls = {"refresh": 0}

    async def fake_refresh(refresh_token: str, proxy_url: str = ""):
        calls["refresh"] += 1
        assert refresh_token == "shared-refresh"
        await asyncio.sleep(0.05)
        return {
            "access_token": "shared-new-access",
            "refresh_token": "shared-new-refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "email": "shared@example.com",
            "account_id": "shared-account",
        }

    monkeypatch.setattr(oauth_source, "refresh_access_token", fake_refresh)
    sol = _make_provider(
        {"id": "openai_oauth/gpt-5.6-sol", "oauth_expires_at": expires_at},
        shared_state=shared_state,
    )
    terra = _make_provider(
        {"id": "openai_oauth/gpt-5.6-terra", "oauth_expires_at": expires_at},
        shared_state=shared_state,
    )
    try:
        await asyncio.gather(
            sol._ensure_fresh_oauth_token(),
            terra._ensure_fresh_oauth_token(),
        )

        assert calls["refresh"] == 1
        assert sol.provider_config["oauth_access_token"] == "shared-new-access"
        assert terra.provider_config["oauth_access_token"] == "shared-new-access"
        assert terra.provider_config["oauth_refresh_token"] == "shared-new-refresh"
    finally:
        await sol.terminate()
        await terra.terminate()


@pytest.mark.asyncio
async def test_refresh_does_not_overwrite_newer_source_credentials(monkeypatch):
    expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    shared_state = OpenAIOAuthSharedState(
        "openai_oauth",
        {
            "oauth_access_token": "expired-access",
            "oauth_refresh_token": "old-refresh",
            "oauth_expires_at": expires_at,
            "oauth_account_id": "shared-account",
        },
    )
    refresh_started = asyncio.Event()
    finish_refresh = asyncio.Event()
    persisted = []

    async def fake_refresh(refresh_token: str, proxy_url: str = ""):
        assert refresh_token == "old-refresh"
        refresh_started.set()
        await finish_refresh.wait()
        return {
            "access_token": "stale-refreshed-access",
            "refresh_token": "stale-refreshed-token",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "email": "stale@example.com",
            "account_id": "shared-account",
        }

    async def persist_callback(patch: dict):
        persisted.append(patch)

    monkeypatch.setattr(oauth_source, "refresh_access_token", fake_refresh)
    provider = _make_provider(
        {"oauth_expires_at": expires_at},
        persist_callback=persist_callback,
        shared_state=shared_state,
    )
    try:
        refresh_task = asyncio.create_task(provider._ensure_fresh_oauth_token())
        await refresh_started.wait()
        shared_state.replace(
            {
                "auth_mode": "openai_oauth",
                "oauth_provider": "openai",
                "oauth_access_token": "imported-access",
                "oauth_refresh_token": "imported-refresh",
                "oauth_expires_at": (
                    datetime.now(timezone.utc) + timedelta(hours=2)
                ).isoformat(),
                "oauth_account_id": "shared-account",
            }
        )
        finish_refresh.set()
        await refresh_task

        snapshot = shared_state.snapshot()
        assert snapshot["oauth_access_token"] == "imported-access"
        assert snapshot["oauth_refresh_token"] == "imported-refresh"
        assert persisted == []
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_shared_oauth_state_updates_headers_for_other_models():
    shared_state = OpenAIOAuthSharedState(
        "openai_oauth",
        {
            "oauth_access_token": "old-access",
            "oauth_refresh_token": "old-refresh",
            "oauth_expires_at": "2026-07-22T16:58:10+00:00",
            "oauth_account_id": "shared-account",
        },
    )
    sol = _make_provider(shared_state=shared_state)
    terra = _make_provider(
        {"id": "openai_oauth/gpt-5.6-terra"},
        shared_state=shared_state,
    )
    try:
        sol._apply_oauth_token_to_runtime(
            {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_at": "2026-07-22T17:58:10+00:00",
                "email": "shared@example.com",
                "account_id": "shared-account",
            }
        )

        headers = terra._build_backend_headers()

        assert headers["Authorization"] == "Bearer new-access"
        assert terra.provider_config["oauth_refresh_token"] == "new-refresh"
    finally:
        await sol.terminate()
        await terra.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_method", "request_once_method"),
    [
        ("_request_backend", "_request_backend_once"),
        ("_request_image_backend", "_request_image_backend_once"),
    ],
)
async def test_shared_oauth_state_refreshes_once_after_concurrent_401(
    monkeypatch,
    request_method: str,
    request_once_method: str,
):
    shared_state = OpenAIOAuthSharedState(
        "openai_oauth",
        {
            "oauth_access_token": "rejected-access",
            "oauth_refresh_token": "shared-refresh",
            "oauth_expires_at": (
                datetime.now(timezone.utc) + timedelta(hours=1)
            ).isoformat(),
            "oauth_account_id": "shared-account",
        },
    )
    refresh_calls = 0
    first_attempts = 0
    first_attempts_ready = asyncio.Event()

    async def fake_refresh(refresh_token: str, proxy_url: str = ""):
        nonlocal refresh_calls
        refresh_calls += 1
        assert refresh_token == "shared-refresh"
        return {
            "access_token": "accepted-access",
            "refresh_token": "rotated-refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "email": "shared@example.com",
            "account_id": "shared-account",
        }

    def make_backend():
        attempts = 0

        async def request_backend(payload: dict):
            nonlocal attempts, first_attempts
            attempts += 1
            attempted_version = shared_state.version
            if attempts == 1:
                first_attempts += 1
                if first_attempts == 2:
                    first_attempts_ready.set()
                await first_attempts_ready.wait()
                return 401, '{"error":{"message":"expired"}}', attempted_version
            return (
                200,
                'data: {"type":"response.completed","response":'
                '{"id":"resp_ok","output_text":"OK","output":[]}}\n\n',
                attempted_version,
            )

        return request_backend

    monkeypatch.setattr(oauth_source, "refresh_access_token", fake_refresh)
    sol = _make_provider(
        {"id": "openai_oauth/gpt-5.6-sol"},
        shared_state=shared_state,
    )
    terra = _make_provider(
        {"id": "openai_oauth/gpt-5.6-terra"},
        shared_state=shared_state,
    )
    monkeypatch.setattr(sol, request_once_method, make_backend())
    monkeypatch.setattr(terra, request_once_method, make_backend())
    try:
        sol_response, terra_response = await asyncio.gather(
            getattr(sol, request_method)({"model": "gpt-5.6-sol", "input": []}),
            getattr(terra, request_method)({"model": "gpt-5.6-terra", "input": []}),
        )

        assert refresh_calls == 1
        assert sol_response["id"] == "resp_ok"
        assert terra_response["id"] == "resp_ok"
        assert terra.provider_config["oauth_refresh_token"] == "rotated-refresh"
    finally:
        await sol.terminate()
        await terra.terminate()


@pytest.mark.asyncio
async def test_request_backend_refreshes_once_after_401(monkeypatch):
    calls = {"refresh": 0}

    async def fake_refresh(refresh_token: str, proxy_url: str = ""):
        calls["refresh"] += 1
        return {
            "access_token": "retried-access",
            "refresh_token": "retried-refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "email": "",
            "account_id": "retried-account",
        }

    class FakeResponse:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self._text = text

        async def aread(self):
            return self._text.encode()

    class FakeClient:
        responses = [
            FakeResponse(401, '{"error":{"message":"expired"}}'),
            FakeResponse(
                200,
                'data: {"type":"response.completed","response":{"id":"resp_ok","output_text":"OK","output":[]}}\n\n',
            ),
        ]

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aclose(self):
            pass

        async def post(self, *args, **kwargs):
            return self.responses.pop(0)

    monkeypatch.setattr(oauth_source, "refresh_access_token", fake_refresh)
    monkeypatch.setattr(oauth_source.httpx, "AsyncClient", FakeClient)
    provider = _make_provider()
    try:
        response = await provider._request_backend(
            {"model": "gpt-5.4", "input": "ping"}
        )

        assert calls["refresh"] == 1
        assert response["id"] == "resp_ok"
        assert provider.provider_config["oauth_access_token"] == "retried-access"
        assert provider.provider_config["oauth_account_id"] == "retried-account"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_oauth_provider_exposes_codex_model_catalog_and_defaults():
    provider = _make_provider()
    try:
        models = await provider.get_models()

        assert models[:4] == [
            "gpt-6-astra",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
        ]
        assert provider.model_capabilities["gpt-6-astra"] == {
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": (
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
            ),
        }
        expected_efforts = ("none", "low", "medium", "high", "xhigh", "max")
        for model in models[1:4]:
            assert (
                provider.model_capabilities[model]["supported_reasoning_efforts"]
                == expected_efforts
            )
        assert (
            provider.model_capabilities["gpt-5.6-sol"]["default_reasoning_effort"]
            == "low"
        )
        assert (
            provider.model_capabilities["gpt-5.6-terra"]["default_reasoning_effort"]
            == "medium"
        )
        assert (
            provider.model_capabilities["gpt-5.6-luna"]["default_reasoning_effort"]
            == "medium"
        )
        assert (
            provider.model_capabilities["gpt-5.3-codex-spark"][
                "default_reasoning_effort"
            ]
            == "high"
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_request_backend_sends_codex_identity_and_residency_headers(
    monkeypatch,
):
    sent_requests: list[dict] = []
    access_token = _jwt_with_claims(
        {
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "test-account",
                "chatgpt_compute_residency": "us",
            }
        }
    )

    class FakeResponse:
        status_code = 200

        async def aread(self):
            return b'data: {"type":"response.completed","response":{"id":"ok"}}\n\n'

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aclose(self):
            pass

        async def post(self, *args, **kwargs):
            sent_requests.append(kwargs)
            return FakeResponse()

    monkeypatch.setattr(oauth_source.httpx, "AsyncClient", FakeClient)
    provider = _make_provider({"oauth_access_token": access_token})
    try:
        status_code, _text, attempted_version = await provider._request_backend_once(
            {"model": "gpt-5.6-luna"}
        )

        headers = sent_requests[0]["headers"]
        assert status_code == 200
        assert attempted_version == provider._oauth_shared_state.version
        assert headers["version"] == "0.153.4"
        assert headers["User-Agent"] == "codex_cli_rs/0.153.4"
        assert headers["x-openai-internal-codex-residency"] == "us"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_request_backend_reports_version_used_by_authorization_header(
    monkeypatch,
):
    sent_requests: list[dict] = []
    shared_state = OpenAIOAuthSharedState(
        "openai_oauth",
        {
            "oauth_access_token": "header-access",
            "oauth_refresh_token": "header-refresh",
            "oauth_expires_at": "2026-07-22T16:58:10+00:00",
            "oauth_account_id": "shared-account",
        },
    )

    class FakeResponse:
        status_code = 200

        async def aread(self):
            return b'data: {"type":"response.completed","response":{"id":"ok"}}\n\n'

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aclose(self):
            pass

        async def post(self, *args, **kwargs):
            sent_requests.append(kwargs)
            shared_state.replace(
                {
                    "oauth_access_token": "newer-access",
                    "oauth_refresh_token": "newer-refresh",
                    "oauth_expires_at": "2026-07-22T17:58:10+00:00",
                    "oauth_account_id": "shared-account",
                }
            )
            return FakeResponse()

    monkeypatch.setattr(oauth_source.httpx, "AsyncClient", FakeClient)
    provider = _make_provider(shared_state=shared_state)
    try:
        _status_code, _text, attempted_version = await provider._request_backend_once(
            {"model": "gpt-5.6-sol"}
        )

        assert sent_requests[0]["headers"]["Authorization"] == "Bearer header-access"
        assert attempted_version < shared_state.version
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claims", "expected_residency"),
    [
        (
            {
                "https://api.openai.com/auth": {
                    "chatgpt_data_residency": "eu",
                    "chatgpt_compute_residency": "us",
                },
                "chatgpt_data_residency": "ca",
            },
            "eu",
        ),
        (
            {
                "https://api.openai.com/auth": {},
                "chatgpt_compute_residency": "ca",
            },
            "ca",
        ),
        ({}, None),
    ],
)
async def test_backend_headers_resolve_residency_claims(claims, expected_residency):
    provider = _make_provider({"oauth_access_token": _jwt_with_claims(claims)})
    try:
        headers = provider._build_backend_headers()

        if expected_residency is None:
            assert "x-openai-internal-codex-residency" not in headers
        else:
            assert headers["x-openai-internal-codex-residency"] == expected_residency
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_backend_headers_allow_explicit_overrides_and_invalid_jwt():
    provider = _make_provider(
        {
            "oauth_access_token": "not-a-jwt",
            "custom_headers": {
                "version": "custom-version",
                "x-openai-internal-codex-residency": "manual",
            },
        }
    )
    try:
        headers = provider._build_backend_headers()

        assert headers["version"] == "custom-version"
        assert headers["x-openai-internal-codex-residency"] == "manual"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "configured_effort", "expected_effort"),
    [
        ("gpt-5.6-luna", "max", "max"),
        ("gpt-5.5", "max", "xhigh"),
        ("gpt-5.6-terra", "off", "none"),
    ],
)
async def test_query_normalizes_reasoning_effort_for_codex_responses(
    model,
    configured_effort,
    expected_effort,
):
    requested_payloads: list[dict] = []
    provider = _make_provider(
        {
            "model": model,
            "custom_extra_body": {"reasoning_effort": configured_effort},
        }
    )

    async def fake_request_backend(payload: dict):
        requested_payloads.append(payload)
        return {"id": "resp_text", "output_text": "pong"}

    provider._request_backend = fake_request_backend
    try:
        await provider._query(
            {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
            },
            None,
        )

        payload = requested_payloads[0]
        assert payload["reasoning"] == {"effort": expected_effort}
        assert "reasoning_effort" not in payload
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("custom_extra_body", "request_kwargs", "model", "expected_reasoning"),
    [
        (
            {"reasoning_effort": "low", "reasoning": {"effort": "medium"}},
            {},
            "gpt-5.6-sol",
            {"effort": "medium"},
        ),
        (
            {"reasoning": {"effort": "low", "summary": "auto"}},
            {"reasoning_effort": "high"},
            "gpt-5.6-sol",
            {"effort": "high", "summary": "auto"},
        ),
        (
            {"reasoning_effort": "medium"},
            {"reasoning_effort": "experimental"},
            "gpt-future-codex",
            {"effort": "experimental"},
        ),
    ],
)
async def test_text_chat_reasoning_precedence_and_unknown_model_passthrough(
    custom_extra_body,
    request_kwargs,
    model,
    expected_reasoning,
):
    requested_payloads: list[dict] = []
    provider = _make_provider(
        {
            "model": model,
            "custom_extra_body": custom_extra_body,
        }
    )

    async def fake_request_backend(payload: dict):
        requested_payloads.append(payload)
        return {"id": "resp_text", "output_text": "pong"}

    provider._request_backend = fake_request_backend
    try:
        await provider.text_chat(prompt="ping", **request_kwargs)

        assert requested_payloads[0]["reasoning"] == expected_reasoning
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_rejects_invalid_effort_for_known_model():
    backend_called = False
    provider = _make_provider(
        {
            "model": "gpt-5.6-sol",
            "custom_extra_body": {"reasoning_effort": "experimental"},
        }
    )

    async def fake_request_backend(payload: dict):
        nonlocal backend_called
        backend_called = True
        return {"id": "resp_text", "output_text": "pong"}

    provider._request_backend = fake_request_backend
    try:
        with pytest.raises(ValueError, match="experimental"):
            await provider.text_chat(prompt="ping")
        assert backend_called is False
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_text_chat_reasoning_kwargs_override_model_configuration():
    requested_payloads: list[dict] = []
    provider = _make_provider(
        {
            "model": "gpt-5.6-sol",
            "custom_extra_body": {"reasoning_effort": "low"},
        }
    )

    async def fake_request_backend(payload: dict):
        requested_payloads.append(payload)
        return {"id": "resp_text", "output_text": "pong"}

    provider._request_backend = fake_request_backend
    try:
        await provider.text_chat(
            prompt="ping",
            reasoning_effort="high",
            reasoning={"effort": "max", "summary": "auto"},
        )

        assert requested_payloads[0]["reasoning"] == {
            "effort": "max",
            "summary": "auto",
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_text_chat_builds_astra_payload_with_reasoning_effort():
    requested_payloads: list[dict] = []
    provider = _make_provider({"model": "gpt-6-astra"})

    async def fake_request_backend(payload: dict):
        requested_payloads.append(payload)
        return {"id": "resp_text", "output_text": "pong"}

    provider._request_backend = fake_request_backend
    try:
        await provider.text_chat(prompt="ping", reasoning_effort="max")

        assert requested_payloads == [
            {
                "model": "gpt-6-astra",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": "ping",
                    }
                ],
                "instructions": "",
                "stream": True,
                "store": False,
                "reasoning": {"effort": "max"},
            }
        ]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_rejects_ultra_as_single_provider_request():
    backend_called = False
    provider = _make_provider(
        {
            "model": "gpt-5.6-sol",
            "custom_extra_body": {"reasoning_effort": "ultra"},
        }
    )

    async def fake_request_backend(payload: dict):
        nonlocal backend_called
        backend_called = True
        return {"id": "resp_text", "output_text": "pong"}

    provider._request_backend = fake_request_backend
    try:
        with pytest.raises(ValueError, match="ultra"):
            await provider.text_chat(prompt="ping")
        assert backend_called is False
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_query_accepts_request_max_retries_and_preserves_responses_payload():
    requested_payloads: list[dict] = []
    provider = _make_provider()

    async def fake_request_backend(payload: dict):
        requested_payloads.append(payload)
        return {
            "id": "resp_text",
            "output_text": "pong",
            "usage": {
                "input_tokens": 3,
                "output_tokens": 4,
                "total_tokens": 7,
            },
        }

    provider._request_backend = fake_request_backend
    try:
        response = await provider._query(
            {
                "model": "gpt-5.4",
                "messages": [
                    {"role": "system", "content": "use concise replies"},
                    {"role": "user", "content": "ping"},
                ],
            },
            None,
            request_max_retries=2,
        )

        assert response.completion_text == "pong"
        payload = requested_payloads[0]
        assert payload["model"] == "gpt-5.4"
        assert payload["instructions"] == "use concise replies"
        assert payload["input"] == [
            {
                "type": "message",
                "role": "user",
                "content": "ping",
            }
        ]
        assert payload["stream"] is True
        assert payload["store"] is False
        assert "reasoning" not in payload
        assert "reasoning_effort" not in payload
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_generate_image_with_reference_file_builds_image_edit_payload(tmp_path):
    source_image_bytes = b"\x89PNG\r\n\x1a\nreference"
    output_image_bytes = b"\x89PNG\r\n\x1a\noutput"
    source_path = tmp_path / "reference.png"
    source_path.write_bytes(source_image_bytes)
    requested_payloads: list[dict] = []
    provider = _make_provider(
        {
            "generated_image_dir": str(tmp_path / "generated"),
        }
    )

    async def fake_request_image_backend(payload: dict):
        requested_payloads.append(payload)
        return {
            "output": [
                {
                    "type": "image_generation_call",
                    "result": base64.b64encode(output_image_bytes).decode(),
                }
            ]
        }

    provider._request_image_backend = fake_request_image_backend
    try:
        results = await provider.generate_image(
            prompt="keep the subject and change the background",
            model="gpt-5.4",
            size="1024x1024",
            reference_images=[str(source_path)],
        )

        payload = requested_payloads[0]
        assert payload["instructions"] == "keep the subject and change the background"
        assert payload["stream"] is True
        assert payload["tools"] == [
            {
                "type": "image_generation",
                "action": "edit",
                "size": "1024x1024",
            }
        ]
        assert payload["input"] == [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "keep the subject and change the background",
                    },
                    {
                        "type": "input_image",
                        "image_url": (
                            "data:image/png;base64,"
                            + base64.b64encode(source_image_bytes).decode()
                        ),
                    },
                ],
            }
        ]
        assert Path(results[0].path).read_bytes() == output_image_bytes
        assert provider.capabilities["image_edit"] is True
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_generate_image_with_data_url_reference_keeps_data_url(tmp_path):
    output_image_bytes = b"\x89PNG\r\n\x1a\noutput"
    data_url = "data:image/jpeg;base64," + base64.b64encode(b"jpeg").decode()
    requested_payloads: list[dict] = []
    provider = _make_provider({"generated_image_dir": str(tmp_path)})

    async def fake_request_image_backend(payload: dict):
        requested_payloads.append(payload)
        return {
            "output": [
                {
                    "type": "image_generation_call",
                    "result": base64.b64encode(output_image_bytes).decode(),
                }
            ]
        }

    provider._request_image_backend = fake_request_image_backend
    try:
        await provider.generate_image(
            prompt="turn this into a watercolor illustration",
            reference_images=[data_url],
            action="auto",
        )

        payload = requested_payloads[0]
        assert payload["instructions"] == "turn this into a watercolor illustration"
        assert payload["stream"] is True
        assert payload["tools"] == [
            {
                "type": "image_generation",
                "action": "auto",
            }
        ]
        assert payload["input"][0]["content"][0] == {
            "type": "input_text",
            "text": "turn this into a watercolor illustration",
        }
        assert payload["input"][0]["content"][1] == {
            "type": "input_image",
            "image_url": data_url,
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_generate_image_reads_sse_incrementally(monkeypatch, tmp_path):
    image_bytes = b"\x89PNG\r\n\x1a\nstreamed"
    image_base64 = base64.b64encode(image_bytes).decode()
    sent_requests: list[dict] = []

    class FakeStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aread(self):
            raise AssertionError("image generation should not read the full SSE body")

        async def aiter_lines(self):
            yield "event: response.output_item.done"
            yield (
                'data: {"type":"response.output_item.done","item":'
                '{"id":"ig_test","type":"image_generation_call",'
                f'"result":"{image_base64}","revised_prompt":"streamed prompt"}}'
                ',"output_index":0}'
            )
            yield ""
            yield "event: response.completed"
            yield (
                'data: {"type":"response.completed","response":'
                '{"id":"resp_img","output":[]}}'
            )
            yield ""

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aclose(self):
            pass

        async def post(self, *args, **kwargs):
            raise AssertionError("image generation should use an SSE stream")

        def stream(self, method, url, **kwargs):
            sent_requests.append(
                {
                    "method": method,
                    "url": url,
                    **kwargs,
                }
            )
            return FakeStreamResponse()

    monkeypatch.setattr(oauth_source.httpx, "AsyncClient", FakeClient)
    access_token = _jwt_with_claims(
        {
            "https://api.openai.com/auth": {
                "chatgpt_data_residency": "eu",
            }
        }
    )
    provider = _make_provider(
        {
            "generated_image_dir": str(tmp_path),
            "oauth_access_token": access_token,
        }
    )
    try:
        results = await provider.generate_image("draw from streaming response")

        assert sent_requests[0]["method"] == "POST"
        assert sent_requests[0]["headers"]["version"] == "0.153.4"
        assert sent_requests[0]["headers"]["User-Agent"] == ("codex_cli_rs/0.153.4")
        assert sent_requests[0]["headers"]["x-openai-internal-codex-residency"] == "eu"
        assert sent_requests[0]["json"]["stream"] is True
        assert (
            sent_requests[0]["json"]["instructions"] == "draw from streaming response"
        )
        assert sent_requests[0]["json"]["tools"] == [
            {
                "type": "image_generation",
                "action": "generate",
            }
        ]
        assert len(results) == 1
        assert results[0].revised_prompt == "streamed prompt"
        assert Path(results[0].path).read_bytes() == image_bytes
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_parse_backend_response_rehydrates_sse_output_items():
    provider = _make_provider()
    try:
        text = """
event: response.output_text.done
data: {"type":"response.output_text.done","content_index":0,"item_id":"msg_test","output_index":0,"sequence_number":6,"text":"PONG"}

event: response.output_item.done
data: {"type":"response.output_item.done","item":{"id":"msg_test","type":"message","status":"completed","content":[{"type":"output_text","annotations":[],"logprobs":[],"text":"PONG"}],"phase":"final_answer","role":"assistant"},"output_index":0,"sequence_number":8}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_test","object":"response","created_at":1775575895,"status":"completed","background":false,"completed_at":1775575901,"error":null,"model":"gpt-5.4","output":[],"parallel_tool_calls":true,"reasoning":{"effort":"none","summary":null},"service_tier":"default","store":false,"temperature":1.0,"text":{"format":{"type":"text"},"verbosity":"medium"},"tool_choice":"auto","tool_usage":{"image_gen":{"input_tokens":0,"input_tokens_details":{"image_tokens":0,"text_tokens":0},"output_tokens":0,"output_tokens_details":{"image_tokens":0,"text_tokens":0},"total_tokens":0},"web_search":{"num_requests":0}},"tools":[],"top_logprobs":0,"top_p":0.98,"truncation":"disabled","usage":{"input_tokens":12,"input_tokens_details":{"cached_tokens":0},"output_tokens":6,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":18},"user":null,"metadata":{}},"sequence_number":9}
""".strip()

        response = provider._parse_backend_response(text)
        llm_response = await provider._parse_responses_completion(response, None)

        assert llm_response.completion_text == "PONG"
        assert response["output_text"] == "PONG"
        assert response["output"][0]["content"][0]["text"] == "PONG"
        assert llm_response.usage is not None
        assert llm_response.usage.output == 6
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_text_chat_stream_preserves_provider_positional_arguments():
    provider = _make_provider()
    provider._prepare_chat_payload = AsyncMock(
        return_value=({"model": "model", "messages": []}, [])
    )
    captured = []

    async def fake_query_stream(payloads, tools, *, request_max_retries=None):
        captured.append((payloads, tools, request_max_retries))
        yield LLMResponse(role="assistant", completion_text="ok")

    provider._query_stream = fake_query_stream
    provider._record_provider_stat = AsyncMock()
    tool = SimpleNamespace(empty=lambda: False)
    tool_result = SimpleNamespace()
    extra_parts = [SimpleNamespace()]
    try:
        responses = [
            response
            async for response in provider.text_chat_stream(
                "prompt",
                "session",
                ["image"],
                ["audio"],
                tool,
                [{"role": "user", "content": "message"}],
                "system",
                tool_result,
                "model",
                "required",
                2,
                extra_user_content_parts=extra_parts,
            )
        ]

        assert len(responses) == 1
        provider._prepare_chat_payload.assert_awaited_once_with(
            "prompt",
            ["image"],
            ["audio"],
            [{"role": "user", "content": "message"}],
            "system",
            tool_result,
            model="model",
            extra_user_content_parts=extra_parts,
        )
        assert captured == [
            (
                {
                    "model": "model",
                    "messages": [],
                    "tool_choice": "required",
                },
                tool,
                2,
            )
        ]
    finally:
        await provider.terminate()
