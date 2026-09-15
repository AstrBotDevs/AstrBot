"""Tests for the OrcaRouter credential seam, catalog and provider adapter.

Every credential in these tests is fabricated. No real ``sk-orca-`` key, auth
code, or verifier appears in any fixture, assertion message, or log capture.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from astrbot.core.provider import orcarouter_auth as auth
from astrbot.core.provider import orcarouter_catalog as catalog

FAKE_KEY = "sk-orca-test-not-a-real-credential"
FAKE_CODE = "test-auth-code-not-real"
AUTH_BASE = "https://www.orcarouter.ai"
API_BASE = "https://api.orcarouter.ai/v1"


# --------------------------------------------------------------------------
# api_key adapter
# --------------------------------------------------------------------------


def test_api_key_adapter_returns_shared_credential_shape():
    credentials = auth.api_key_credentials(FAKE_KEY)

    assert credentials.key == FAKE_KEY
    assert credentials.source == "api_key"
    assert credentials.scope == "api"


def test_api_key_adapter_rejects_empty_value():
    with pytest.raises(auth.OrcaRouterAuthError):
        auth.api_key_credentials("   ")


def test_credential_repr_never_contains_the_key():
    credentials = auth.api_key_credentials(FAKE_KEY)

    assert FAKE_KEY not in repr(credentials)
    assert FAKE_KEY not in str(credentials)
    assert "redacted" in repr(credentials)


def test_redact_key_keeps_only_a_short_prefix():
    redacted = auth.redact_key(FAKE_KEY)

    assert FAKE_KEY not in redacted
    assert redacted.startswith("sk-orca-")
    assert auth.redact_key("short") == "****"


# --------------------------------------------------------------------------
# pkce primitives
# --------------------------------------------------------------------------


def test_verifier_and_state_are_fresh_per_attempt():
    verifiers = {auth.generate_verifier() for _ in range(64)}
    states = {auth.generate_state() for _ in range(64)}

    assert len(verifiers) == 64
    assert len(states) == 64


def test_verifier_is_unpadded_base64url_of_32_bytes():
    verifier = auth.generate_verifier()

    assert "=" not in verifier
    assert "+" not in verifier and "/" not in verifier
    assert len(base64.urlsafe_b64decode(verifier + "==")) == 32


def test_challenge_is_s256_of_the_verifier_without_padding():
    verifier = auth.generate_verifier()
    challenge = auth.code_challenge_for(verifier)

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert challenge == expected
    assert "=" not in challenge
    assert challenge != verifier


def test_authorize_url_carries_only_the_challenge_not_the_verifier():
    verifier = auth.generate_verifier()
    state = auth.generate_state()
    url = auth.build_authorize_url(
        auth_base_url=AUTH_BASE,
        app_name="AstrBot",
        code_challenge=auth.code_challenge_for(verifier),
        state=state,
        callback_url="oob",
    )

    assert url.startswith(f"{AUTH_BASE}/auth?")
    params = parse_qs(urlsplit(url).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["callback_url"] == ["oob"]
    assert params["app_name"] == ["AstrBot"]
    assert params["scope"] == ["api"]
    assert params["state"] == [state]
    assert verifier not in url
    assert params["code_challenge"] == [auth.code_challenge_for(verifier)]


def test_authorize_url_rejects_a_scope_orcarouter_would_refuse():
    with pytest.raises(ValueError):
        auth.build_authorize_url(
            auth_base_url=AUTH_BASE,
            app_name="AstrBot",
            code_challenge="x",
            state="y",
            callback_url="oob",
            scope="admin",
        )


def test_authorize_url_rejects_an_insecure_non_loopback_callback():
    with pytest.raises(ValueError):
        auth.build_authorize_url(
            auth_base_url=AUTH_BASE,
            app_name="AstrBot",
            code_challenge="x",
            state="y",
            callback_url="http://evil.example.com/cb",
        )


def test_authorize_url_accepts_an_https_callback_on_any_port():
    url = auth.build_authorize_url(
        auth_base_url=AUTH_BASE,
        app_name="AstrBot",
        code_challenge="x",
        state="y",
        callback_url="https://astrbot.example.com:8443/cb",
    )

    assert "callback_url=https%3A%2F%2Fastrbot.example.com%3A8443%2Fcb" in url


# --------------------------------------------------------------------------
# origins
# --------------------------------------------------------------------------


def test_auth_and_api_origins_are_independent_by_default(monkeypatch):
    for name in ("ORCA_AUTH_BASE_URL", "ORCA_API_BASE_URL", "ORCA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    assert auth.resolve_auth_base_url() == "https://www.orcarouter.ai"
    assert auth.resolve_api_base_url() == "https://api.orcarouter.ai/v1"


def test_explicit_overrides_win_over_the_shared_base(monkeypatch):
    monkeypatch.setenv("ORCA_BASE_URL", "https://shared.selfhosted.example")
    monkeypatch.setenv("ORCA_AUTH_BASE_URL", "https://auth.selfhosted.example")
    monkeypatch.setenv("ORCA_API_BASE_URL", "https://api.selfhosted.example/v1")

    assert auth.resolve_auth_base_url() == "https://auth.selfhosted.example"
    assert auth.resolve_api_base_url() == "https://api.selfhosted.example/v1"


def test_shared_base_is_used_when_no_explicit_override_exists(monkeypatch):
    monkeypatch.delenv("ORCA_AUTH_BASE_URL", raising=False)
    monkeypatch.delenv("ORCA_API_BASE_URL", raising=False)
    monkeypatch.setenv("ORCA_BASE_URL", "https://one-origin.example")

    assert auth.resolve_auth_base_url() == "https://one-origin.example"
    assert auth.resolve_api_base_url() == "https://one-origin.example/v1"


def test_plain_http_is_refused_for_a_remote_origin():
    with pytest.raises(ValueError):
        auth.resolve_api_base_url("http://api.orcarouter.ai/v1")


def test_plain_http_is_allowed_for_loopback_development():
    assert (
        auth.resolve_auth_base_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    )


def test_api_base_appends_v1_without_touching_the_auth_origin(monkeypatch):
    monkeypatch.delenv("ORCA_BASE_URL", raising=False)

    assert auth.resolve_api_base_url("https://api.example.com") == (
        "https://api.example.com/v1"
    )
    # The auth origin is resolved from its own setting, never from this value.
    assert auth.resolve_auth_base_url() == "https://www.orcarouter.ai"


def test_exchange_path_is_not_under_the_relay_v1_prefix():
    assert auth.EXCHANGE_PATH == "/api/v1/auth/keys"
    assert not auth.EXCHANGE_PATH.startswith("/v1/")


# --------------------------------------------------------------------------
# exchange
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _patch_post(monkeypatch, response=None, error=None):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        if error is not None:
            raise error
        return response

    monkeypatch.setattr(auth.httpx, "post", fake_post)
    return calls


def test_exchange_posts_code_and_verifier_to_the_auth_origin(monkeypatch):
    calls = _patch_post(
        monkeypatch,
        _FakeResponse(200, {"key": FAKE_KEY, "user_id": "42", "scope": "api"}),
    )

    credentials = auth.exchange_code(
        auth_base_url=AUTH_BASE, code=FAKE_CODE, code_verifier="v" * 43
    )

    assert calls[0]["url"] == f"{AUTH_BASE}/api/v1/auth/keys"
    assert calls[0]["json"] == {
        "code": FAKE_CODE,
        "code_verifier": "v" * 43,
        "code_challenge_method": "S256",
    }
    assert credentials.source == "pkce"
    assert credentials.key == FAKE_KEY
    assert credentials.user_id == "42"


def test_exchange_reads_back_the_granted_scope_not_the_requested_one(monkeypatch):
    _patch_post(
        monkeypatch,
        _FakeResponse(200, {"key": FAKE_KEY, "scope": "connector"}),
    )

    credentials = auth.exchange_code(
        auth_base_url=AUTH_BASE, code=FAKE_CODE, code_verifier="v" * 43
    )

    assert credentials.scope == "connector"


def test_exchange_403_is_a_code_error(monkeypatch):
    _patch_post(monkeypatch, _FakeResponse(403, {"error": "invalid_grant"}))

    with pytest.raises(auth.OrcaRouterCodeError):
        auth.exchange_code(
            auth_base_url=AUTH_BASE, code=FAKE_CODE, code_verifier="v" * 43
        )


def test_exchange_400_is_a_challenge_method_error(monkeypatch):
    _patch_post(monkeypatch, _FakeResponse(400, {"error": "invalid_request"}))

    with pytest.raises(auth.OrcaRouterCodeError):
        auth.exchange_code(
            auth_base_url=AUTH_BASE, code=FAKE_CODE, code_verifier="v" * 43
        )


def test_exchange_429_is_the_pkce_key_cap(monkeypatch):
    _patch_post(monkeypatch, _FakeResponse(429, {"error": "rate_limited"}))

    with pytest.raises(auth.OrcaRouterRateLimitedError):
        auth.exchange_code(
            auth_base_url=AUTH_BASE, code=FAKE_CODE, code_verifier="v" * 43
        )


def test_exchange_network_failure_does_not_leak_the_verifier(monkeypatch):
    verifier = "verifier-must-not-appear-" + "v" * 20
    _patch_post(monkeypatch, error=httpx.ConnectError("boom"))

    with pytest.raises(auth.OrcaRouterNetworkError) as excinfo:
        auth.exchange_code(
            auth_base_url=AUTH_BASE, code=FAKE_CODE, code_verifier=verifier
        )

    assert verifier not in str(excinfo.value)
    assert FAKE_CODE not in str(excinfo.value)


def test_exchange_rejects_a_non_json_body(monkeypatch):
    _patch_post(monkeypatch, _FakeResponse(200, ValueError("not json")))

    with pytest.raises(auth.OrcaRouterNetworkError):
        auth.exchange_code(
            auth_base_url=AUTH_BASE, code=FAKE_CODE, code_verifier="v" * 43
        )


def test_exchange_rejects_a_body_without_a_key(monkeypatch):
    _patch_post(monkeypatch, _FakeResponse(200, {"scope": "api"}))

    with pytest.raises(auth.OrcaRouterNetworkError):
        auth.exchange_code(
            auth_base_url=AUTH_BASE, code=FAKE_CODE, code_verifier="v" * 43
        )


# --------------------------------------------------------------------------
# flow A — loopback
# --------------------------------------------------------------------------


def test_flow_a_delivers_the_code_to_the_listener():
    pending = auth.PendingLogin("AstrBot")
    url = pending.start_loopback(AUTH_BASE)
    try:
        params = parse_qs(urlsplit(url).query)
        callback = params["callback_url"][0]
        assert callback.startswith("http://127.0.0.1:")

        def redirect():
            httpx.get(f"{callback}?code={FAKE_CODE}&state={pending.state}")

        threading.Thread(target=redirect, daemon=True).start()
        code = pending.loopback.wait_for_code(timeout=10)
    finally:
        pending.close()

    assert code == FAKE_CODE
    # The verifier was never placed on the wire in the authorize URL.
    assert pending.verifier not in url


def test_flow_a_state_mismatch_is_rejected_before_the_code_is_used():
    pending = auth.PendingLogin("AstrBot")
    pending.start_loopback(AUTH_BASE)
    try:
        callback = pending.loopback.redirect_uri

        def redirect():
            httpx.get(f"{callback}?code={FAKE_CODE}&state=not-the-issued-state")

        threading.Thread(target=redirect, daemon=True).start()
        with pytest.raises(auth.OrcaRouterStateMismatchError):
            pending.loopback.wait_for_code(timeout=10)
    finally:
        pending.close()


def test_flow_a_denial_is_reported_as_a_denial():
    pending = auth.PendingLogin("AstrBot")
    pending.start_loopback(AUTH_BASE)
    try:
        callback = pending.loopback.redirect_uri

        def redirect():
            httpx.get(f"{callback}?error=access_denied&state={pending.state}")

        threading.Thread(target=redirect, daemon=True).start()
        with pytest.raises(auth.OrcaRouterDeniedError):
            pending.loopback.wait_for_code(timeout=10)
    finally:
        pending.close()


def test_flow_a_timeout_releases_the_listener():
    pending = auth.PendingLogin("AstrBot")
    pending.start_loopback(AUTH_BASE)

    with pytest.raises(auth.OrcaRouterAuthError):
        pending.loopback.wait_for_code(timeout=0.2)

    # The port is released, so a second attempt can bind a fresh listener.
    second = auth.PendingLogin("AstrBot")
    second.start_loopback(AUTH_BASE)
    second.close()


def test_parse_authorize_redirect_compares_state_before_reading_the_code():
    with pytest.raises(auth.OrcaRouterStateMismatchError):
        auth.parse_authorize_redirect(f"code={FAKE_CODE}&state=wrong", "right")

    assert (
        auth.parse_authorize_redirect(f"code={FAKE_CODE}&state=right", "right")
        == FAKE_CODE
    )


def test_parse_authorize_redirect_surfaces_a_denial():
    with pytest.raises(auth.OrcaRouterDeniedError):
        auth.parse_authorize_redirect("error=access_denied&state=s", "s")


# --------------------------------------------------------------------------
# pending attempt lifecycle
# --------------------------------------------------------------------------


def test_pending_login_uses_a_new_verifier_every_attempt():
    first = auth.PendingLogin("AstrBot")
    second = auth.PendingLogin("AstrBot")

    assert first.verifier != second.verifier
    assert first.state != second.state


def test_expired_attempt_cannot_be_exchanged(monkeypatch):
    pending = auth.PendingLogin("AstrBot")
    pending.created_at -= auth.AUTHORIZE_TIMEOUT_SECONDS + 1

    with pytest.raises(auth.OrcaRouterCodeError):
        auth.credentials_from_exchange(AUTH_BASE, FAKE_CODE, pending)


# --------------------------------------------------------------------------
# terminal 401 handling
# --------------------------------------------------------------------------


def test_only_401_is_terminal():
    assert auth.classify_terminal_status(401) is auth.OrcaRouterNeedsReauthError
    assert auth.classify_terminal_status(403) is None
    assert auth.classify_terminal_status(429) is None
    assert auth.classify_terminal_status(500) is None


# --------------------------------------------------------------------------
# catalog
# --------------------------------------------------------------------------


def _live_payload():
    return {
        "object": "list",
        "data": [
            {
                "id": "openai/gpt-5.5",
                "supported_endpoint_types": ["openai", "openai-response"],
                "architecture": {
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                },
                "context_length": 400000,
                "max_completion_tokens": 128000,
            },
            {
                "id": "deepseek/deepseek-v4-pro",
                "supported_endpoint_types": ["openai", "openai-response"],
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "context_length": 1048576,
                "max_completion_tokens": 384000,
            },
            {
                "id": "orcarouter/auto",
                "supported_endpoint_types": ["openai", "anthropic", "gemini"],
            },
            {"id": "vendor/embed", "supported_endpoint_types": ["embeddings"]},
            {"id": "vendor/image", "supported_endpoint_types": ["image-generation"]},
            {"id": "vendor/video", "supported_endpoint_types": ["openai-video"]},
            {"id": "vendor/rerank", "supported_endpoint_types": ["jina-rerank"]},
            {"id": "", "supported_endpoint_types": ["openai"]},
            "not-a-record",
        ],
    }


def test_parse_catalog_accepts_valid_records_and_drops_broken_ones():
    models = catalog.parse_catalog(_live_payload())

    ids = [model.id for model in models]
    assert "not-a-record" not in ids
    assert "" not in ids
    assert len(models) == 7


def test_parse_catalog_tolerates_a_bare_list_and_a_missing_data_key():
    assert catalog.parse_catalog([{"id": "a"}])[0].id == "a"
    assert catalog.parse_catalog({"data": "nonsense"}) == []
    assert catalog.parse_catalog(None) == []


def test_parse_catalog_bounds_the_item_count():
    payload = [
        {"id": f"vendor/m{index}"} for index in range(catalog.MAX_CATALOG_ITEMS + 50)
    ]

    assert len(catalog.parse_catalog(payload)) == catalog.MAX_CATALOG_ITEMS


def test_chat_filter_keeps_only_speakable_text_models():
    ids = [
        model.id
        for model in catalog.filter_models(
            catalog.parse_catalog(_live_payload()), "chat"
        )
    ]

    assert ids == ["openai/gpt-5.5", "deepseek/deepseek-v4-pro", "orcarouter/auto"]
    assert "vendor/image" not in ids
    assert "vendor/rerank" not in ids
    assert "vendor/embed" not in ids


def test_embedding_image_video_and_rerank_filters_are_strict():
    models = catalog.parse_catalog(_live_payload())

    assert [m.id for m in catalog.filter_models(models, "embedding")] == [
        "vendor/embed"
    ]
    assert [m.id for m in catalog.filter_models(models, "image")] == ["vendor/image"]
    assert [m.id for m in catalog.filter_models(models, "video")] == ["vendor/video"]
    assert [m.id for m in catalog.filter_models(models, "rerank")] == ["vendor/rerank"]


def test_multimodal_filter_fails_closed_for_undeclared_models():
    models = catalog.parse_catalog(_live_payload())

    ids = [m.id for m in catalog.filter_for_multimodal(models, {"image"})]

    assert ids == ["openai/gpt-5.5"]
    # orcarouter/auto is chat-capable but declares no modalities at all.
    assert "orcarouter/auto" not in ids
    assert "deepseek/deepseek-v4-pro" not in ids


def test_multimodal_filter_is_a_noop_for_text_only_entry_points():
    models = catalog.parse_catalog(_live_payload())

    ids = [m.id for m in catalog.filter_for_multimodal(models, set())]

    assert ids == ["openai/gpt-5.5", "deepseek/deepseek-v4-pro", "orcarouter/auto"]


def test_audio_and_video_modalities_are_filtered_independently():
    models = catalog.parse_catalog(
        [
            {
                "id": "vendor/vision",
                "supported_endpoint_types": ["openai"],
                "architecture": {"input_modalities": ["text", "image"]},
            },
            {
                "id": "vendor/omni",
                "supported_endpoint_types": ["openai"],
                "architecture": {
                    "input_modalities": ["text", "image", "audio", "video"]
                },
            },
        ]
    )

    assert [m.id for m in catalog.filter_for_multimodal(models, {"audio"})] == [
        "vendor/omni"
    ]
    assert [m.id for m in catalog.filter_for_multimodal(models, {"image"})] == [
        "vendor/vision",
        "vendor/omni",
    ]


def test_model_metadata_preserves_context_and_modalities():
    model = catalog.parse_catalog(_live_payload())[0]

    metadata = model.to_metadata()

    assert metadata["limit"]["context"] == 400000
    assert metadata["limit"]["output"] == 128000
    assert metadata["modalities"]["input"] == ["image", "text"]


# --------------------------------------------------------------------------
# seed / degradation
# --------------------------------------------------------------------------


def test_seed_contains_the_verified_models_with_metadata_intact():
    seed = catalog.seed_catalog()
    by_id = {model.id: model for model in seed}

    assert set(by_id) == {
        "openai/gpt-5.5",
        "anthropic/claude-opus-4.8",
        "google/gemini-3.5-flash",
        "deepseek/deepseek-v4-pro",
        "orcarouter/auto",
    }
    assert all(model.verified for model in seed)
    assert by_id["google/gemini-3.5-flash"].input_modalities == {
        "text",
        "image",
        "audio",
        "video",
    }
    assert by_id["openai/gpt-5.5"].context_length == 400000


def test_verified_reasoning_effort_ladder_is_retained():
    assert catalog.VERIFIED_REASONING_EFFORTS["openai/gpt-5.5"] == (
        "low",
        "medium",
        "high",
        "xhigh",
    )


def test_seed_is_a_copy_not_the_shared_constant():
    catalog.seed_catalog()[0].id = "mutated"

    assert catalog.VERIFIED_SEED[0].id == "openai/gpt-5.5"


def test_discovery_falls_back_to_the_seed_when_the_endpoint_fails(monkeypatch):
    async def failing(api_base_url, api_key, timeout=None):
        raise httpx.ConnectError("catalog down")

    monkeypatch.setattr(catalog, "fetch_live_catalog", failing)

    result = asyncio.run(catalog.discover_catalog(API_BASE, FAKE_KEY))

    assert result.source == "seed"
    assert result.degraded is True
    assert "openai/gpt-5.5" in result.model_ids()


def test_discovery_prefers_last_known_good_over_the_seed(monkeypatch):
    async def failing(api_base_url, api_key, timeout=None):
        raise httpx.ConnectError("catalog down")

    monkeypatch.setattr(catalog, "fetch_live_catalog", failing)
    last_known = catalog.parse_catalog([{"id": "vendor/cached"}])

    result = asyncio.run(
        catalog.discover_catalog(API_BASE, FAKE_KEY, last_known_good=last_known)
    )

    assert result.source == "last_known_good"
    assert result.degraded is True
    assert result.model_ids() == ["vendor/cached"]


def test_live_discovery_is_authoritative_and_not_mixed_with_the_seed(monkeypatch):
    async def live(api_base_url, api_key, timeout=None):
        return catalog.parse_catalog([{"id": "vendor/live-only"}])

    monkeypatch.setattr(catalog, "fetch_live_catalog", live)

    result = asyncio.run(catalog.discover_catalog(API_BASE, FAKE_KEY))

    assert result.source == "live"
    assert result.degraded is False
    assert result.model_ids() == ["vendor/live-only"]
    assert "openai/gpt-5.5" not in result.model_ids()


def test_live_fetch_requests_the_catalog_from_the_configured_origin_only(monkeypatch):
    seen = {}

    class _FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            seen["url"] = url
            seen["headers"] = headers
            return httpx.Response(
                200,
                content=json.dumps(_live_payload()).encode(),
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(catalog.httpx, "AsyncClient", _FakeClient)

    asyncio.run(catalog.fetch_live_catalog(API_BASE, FAKE_KEY))

    assert seen["url"] == f"{API_BASE}/models"
    assert seen["headers"] == {"Authorization": f"Bearer {FAKE_KEY}"}
