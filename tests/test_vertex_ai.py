import json
from pathlib import Path

import httpx
import pytest
from google.auth import credentials as google_auth_credentials

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.vertex_ai import (
    build_vertex_ai_publisher_models_url,
    make_vertex_ai_refresh_request,
    normalize_vertex_ai_provider_config,
    normalize_vertex_ai_provider_source_config,
    resolve_vertex_ai_project_id,
    to_vertex_ai_genai_model_name,
)


def _vertex_config(**overrides):
    config = {
        "id": "vertex-test",
        "provider": "google-vertex-ai",
        "type": "googlegenai_chat_completion",
        "provider_type": "chat_completion",
        "model": "google/gemini-3-flash-preview",
        "key": [],
        "api_base": "",
        "timeout": 120,
        "proxy": "",
        "custom_headers": {},
        "vertex_ai_auth_type": "json",
        "vertex_ai_project_id": "demo-project",
        "vertex_ai_location": "global",
        "vertex_ai_credentials_path": "",
        "vertex_ai_credentials_json": "",
    }
    config.update(overrides)
    return config


def _vertex_api_key_config(**overrides):
    config = _vertex_config(
        type="googlegenai_chat_completion",
        vertex_ai_api_key=["test-api-key"],
        api_base="https://aiplatform.googleapis.com/v1",
        custom_headers={},
        vertex_ai_auth_type="api_key",
        vertex_ai_project_id="",
        vertex_ai_credentials_path="",
        vertex_ai_credentials_json="",
    )
    config.update(overrides)
    return config


def _vertex_key_json_config(**overrides):
    config = _vertex_config(
        type="googlegenai_chat_completion",
        api_base="https://aiplatform.googleapis.com/v1",
        vertex_ai_credentials_json=json.dumps(
            {
                "project_id": "demo-project",
                "client_email": "vertex@example.iam.gserviceaccount.com",
                "private_key": "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----\n",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
    )
    config.update(overrides)
    return config


class FakeVertexCredentials(google_auth_credentials.Credentials):
    def __init__(self):
        super().__init__()
        self.token = "ya29.fake-token"
        self.refresh_count = 0

    def refresh(self, request):
        self.refresh_count += 1
        self.token = "ya29.refreshed-token"


def test_vertex_ai_publisher_models_url_uses_native_vertex_endpoint():
    config = _vertex_config(
        api_base="https://aiplatform.googleapis.com/v1",
        vertex_ai_project_id="demo-project",
        vertex_ai_location="global",
    )

    assert build_vertex_ai_publisher_models_url(config) == (
        "https://aiplatform.googleapis.com/v1beta1/publishers/google/models"
    )


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (
            "google/gemini-3-flash-preview",
            "publishers/google/models/gemini-3-flash-preview",
        ),
        ("models/gemini-2.5-pro", "publishers/google/models/gemini-2.5-pro"),
        ("gemini-2.5-flash", "publishers/google/models/gemini-2.5-flash"),
        (
            "publishers/google/models/gemini-3-flash-preview",
            "publishers/google/models/gemini-3-flash-preview",
        ),
    ],
)
def test_vertex_ai_genai_model_name_normalization(model, expected):
    assert to_vertex_ai_genai_model_name(model) == expected


def test_vertex_ai_project_id_can_be_loaded_from_service_account_file(tmp_path):
    credentials_path = tmp_path / "service-account.json"
    credentials_path.write_text(
        json.dumps({"project_id": "file-project"}),
        encoding="utf-8",
    )

    assert (
        resolve_vertex_ai_project_id(
            _vertex_config(
                vertex_ai_project_id="",
                vertex_ai_credentials_path=str(credentials_path),
            )
        )
        == "file-project"
    )


def test_vertex_ai_refresh_request_uses_provider_proxy(monkeypatch):
    captured = {}

    class FakeSession:
        def __init__(self):
            self.proxies = {}
            self.trust_env = True

    class FakeRequest:
        def __init__(self, session=None):
            captured["session"] = session

    monkeypatch.setattr("google.auth.transport.requests.Request", FakeRequest)
    monkeypatch.setattr("requests.Session", FakeSession)

    assert make_vertex_ai_refresh_request({"proxy": "http://127.0.0.1:7890"})
    session = captured["session"]
    assert session.proxies == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }
    assert session.trust_env is False


def test_vertex_ai_api_key_config_is_normalized_to_google_genai_provider():
    config = _vertex_config(
        type="openai_chat_completion",
        vertex_ai_auth_type="api_key",
        vertex_ai_api_key=["vertex-api-key"],
    )

    normalized = normalize_vertex_ai_provider_config(config)
    assert normalized["type"] == "googlegenai_chat_completion"
    assert normalized["key"] == ["vertex-api-key"]


def test_vertex_ai_runtime_normalization_does_not_mutate_source_config():
    config = _vertex_config(
        type="openai_chat_completion",
        vertex_ai_auth_type="api_key",
        vertex_ai_api_key=["vertex-api-key"],
        vertex_ai_credentials_json='{"project_id":"demo-project"}',
    )

    normalized = normalize_vertex_ai_provider_config(config)
    assert normalized is not config
    assert normalized["key"] == ["vertex-api-key"]
    assert normalized["vertex_ai_credentials_json"] == '{"project_id":"demo-project"}'
    assert "key" in config
    assert config["key"] == []
    assert config["type"] == "openai_chat_completion"
    assert config["vertex_ai_credentials_json"] == '{"project_id":"demo-project"}'


def test_vertex_ai_api_key_normalization_migrates_legacy_key_field():
    config = _vertex_config(
        type="openai_chat_completion",
        vertex_ai_auth_type="api_key",
        key=["legacy-api-key"],
    )

    normalized = normalize_vertex_ai_provider_config(config)
    assert normalized["vertex_ai_api_key"] == ["legacy-api-key"]
    assert normalized["key"] == ["legacy-api-key"]


def test_vertex_ai_source_normalization_does_not_persist_runtime_key():
    config = _vertex_config(
        type="googlegenai_chat_completion",
        vertex_ai_auth_type="api_key",
        vertex_ai_api_key=["vertex-api-key"],
        key=["stale-runtime-key"],
    )

    normalized = normalize_vertex_ai_provider_source_config(config)
    assert normalized["vertex_ai_api_key"] == ["vertex-api-key"]
    assert "key" not in normalized
    assert config["key"] == ["stale-runtime-key"]


def test_vertex_ai_source_normalization_preserves_json_and_api_key_fields():
    config = _vertex_config(
        type="googlegenai_chat_completion",
        vertex_ai_auth_type="json",
        vertex_ai_api_key=["vertex-api-key"],
        vertex_ai_credentials_json='{"project_id":"demo-project"}',
        key=["stale-runtime-key"],
    )

    normalized = normalize_vertex_ai_provider_source_config(config)
    assert normalized["vertex_ai_auth_type"] == "json"
    assert normalized["vertex_ai_api_key"] == ["vertex-api-key"]
    assert normalized["vertex_ai_credentials_json"] == '{"project_id":"demo-project"}'
    assert "key" not in normalized


def test_vertex_ai_missing_auth_type_defaults_to_json():
    config = _vertex_config(vertex_ai_auth_type="")

    assert normalize_vertex_ai_provider_config(config)["vertex_ai_auth_type"] == "json"


def test_vertex_ai_legacy_service_account_auth_type_normalizes_to_json():
    config = _vertex_config(vertex_ai_auth_type="service_account")

    assert normalize_vertex_ai_provider_config(config)["vertex_ai_auth_type"] == "json"


@pytest.mark.asyncio
async def test_vertex_ai_api_key_provider_uses_native_vertex_endpoint():
    provider = ProviderGoogleGenAI(_vertex_api_key_config(), provider_settings={})

    try:
        api_client = provider.client._api_client
        request = api_client._build_request(
            "post",
            "publishers/google/models/gemini-3-flash-preview:generateContent",
            {"contents": []},
            None,
        )

        assert api_client.vertexai is True
        assert api_client._http_options.api_version == "v1"
        assert (
            api_client._http_options.base_url.rstrip("/")
            == "https://aiplatform.googleapis.com"
        )
        assert api_client._http_options.headers["x-goog-api-key"] == "test-api-key"
        assert str(request.url) == (
            "https://aiplatform.googleapis.com/v1/publishers/google/"
            "models/gemini-3-flash-preview:generateContent"
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_vertex_ai_api_key_text_chat_hits_native_vertex_endpoint():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "pong"}],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 1,
                    "candidatesTokenCount": 1,
                },
                "responseId": "vertex-api-key-response",
            },
        )

    transport = httpx.MockTransport(handler)
    provider = ProviderGoogleGenAI(_vertex_api_key_config(), provider_settings={})
    await provider._http_client.aclose()
    provider._http_client = httpx.AsyncClient(
        transport=transport,
        base_url=provider._get_vertex_ai_sdk_base_url(),
        timeout=provider.timeout,
    )
    provider.client._api_client._async_httpx_client = provider._http_client

    try:
        response = await provider.text_chat(prompt="ping")

        assert response.completion_text == "pong"
        assert len(requests) == 1
        assert str(requests[0].url) == (
            "https://aiplatform.googleapis.com/v1/publishers/google/"
            "models/gemini-3-flash-preview:generateContent"
        )
        assert requests[0].headers["x-goog-api-key"] == "test-api-key"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_vertex_ai_api_key_text_chat_normalizes_astrbot_model_id():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": "pong"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
                "responseId": "vertex-normalized-model-response",
            },
        )

    provider = ProviderGoogleGenAI(
        _vertex_api_key_config(model="google/gemini-3-flash-preview"),
        provider_settings={},
    )
    await provider._http_client.aclose()
    provider._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=provider._get_vertex_ai_sdk_base_url(),
        timeout=provider.timeout,
    )
    provider.client._api_client._async_httpx_client = provider._http_client

    try:
        response = await provider.text_chat(prompt="ping")

        assert response.completion_text == "pong"
        assert str(requests[0].url) == (
            "https://aiplatform.googleapis.com/v1/publishers/google/"
            "models/gemini-3-flash-preview:generateContent"
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_vertex_ai_api_key_provider_omits_empty_api_key_header():
    provider = ProviderGoogleGenAI(
        _vertex_api_key_config(vertex_ai_api_key=[]),
        provider_settings={},
    )

    try:
        headers = provider.client._api_client._http_options.headers
        assert "x-goog-api-key" not in headers
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_vertex_ai_api_key_provider_requires_key_for_text_chat():
    provider = ProviderGoogleGenAI(
        _vertex_api_key_config(vertex_ai_api_key=[]),
        provider_settings={},
    )

    try:
        with pytest.raises(ValueError, match="Vertex AI API key is required"):
            await provider.text_chat(prompt="ping")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_vertex_ai_service_account_google_genai_get_models_uses_publisher_endpoint(
    monkeypatch,
):
    credentials = FakeVertexCredentials()
    calls = []
    responses = [
        {
            "models": [
                {"name": "publishers/google/models/gemini-3-flash-preview"},
                {
                    "name": (
                        "projects/demo-project/locations/global/"
                        "publishers/google/models/gemini-2.5-pro"
                    )
                },
            ],
            "nextPageToken": "page-2",
        },
        {"models": [{"name": "gemini-3-flash-preview"}]},
    ]

    def fake_client(**kwargs):
        assert kwargs["credentials"] is credentials
        assert kwargs["project"] == "demo-project"
        assert kwargs["location"] == "global"
        assert kwargs["vertexai"] is True
        return type(
            "FakeGenAIClient",
            (),
            {
                "aio": type(
                    "FakeAsyncClient",
                    (),
                    {
                        "models": type(
                            "FakeModels",
                            (),
                            {"list": lambda self: pytest.fail("models.list called")},
                        )(),
                        "aclose": lambda self: None,
                    },
                )()
            },
        )()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=responses.pop(0))

    monkeypatch.setattr(
        ProviderGoogleGenAI,
        "_load_vertex_ai_service_account_credentials",
        lambda self: credentials,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.gemini_source.genai.Client",
        fake_client,
    )

    transport = httpx.MockTransport(handler)
    provider = ProviderGoogleGenAI(
        _vertex_config(type="googlegenai_chat_completion"),
        provider_settings={},
    )
    await provider._http_client.aclose()
    provider._http_client = httpx.AsyncClient(
        transport=transport,
        base_url=provider._get_vertex_ai_sdk_base_url(),
        timeout=provider.timeout,
    )

    try:
        assert await provider.get_models() == [
            "google/gemini-2.5-pro",
            "google/gemini-3-flash-preview",
        ]
        assert len(calls) == 2
        assert calls[0].url.path == "/v1beta1/publishers/google/models"
        assert calls[0].url.params["pageSize"] == "300"
        assert calls[1].url.path == "/v1beta1/publishers/google/models"
        assert calls[1].url.params["pageToken"] == "page-2"
        assert calls[0].headers["authorization"] == "Bearer ya29.fake-token"
        assert calls[0].headers["x-goog-user-project"] == "demo-project"
        assert calls[0].headers["accept-encoding"] == "gzip, deflate"
        assert credentials.refresh_count == 0
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_vertex_ai_api_key_provider_rejects_model_list_without_json(
    monkeypatch,
):
    provider = ProviderGoogleGenAI(_vertex_api_key_config(), provider_settings={})

    async def fail_list():
        raise AssertionError("Vertex AI API-key mode must not call models.list()")

    monkeypatch.setattr(provider.client.models, "list", fail_list)

    try:
        with pytest.raises(ValueError, match="API Key 无法获取模型列表"):
            await provider.get_models()
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_vertex_ai_key_json_provider_fetches_model_list(monkeypatch):
    credentials = FakeVertexCredentials()
    calls = []

    def fake_client(**kwargs):
        assert kwargs["credentials"] is credentials
        assert kwargs["project"] == "demo-project"
        assert kwargs["location"] == "global"
        assert kwargs["vertexai"] is True
        return type(
            "FakeGenAIClient",
            (),
            {
                "aio": type(
                    "FakeAsyncClient",
                    (),
                    {
                        "models": type(
                            "FakeModels",
                            (),
                            {"list": lambda self: pytest.fail("models.list called")},
                        )(),
                        "aclose": lambda self: None,
                    },
                )()
            },
        )()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "publisherModels": [
                    {"name": "publishers/google/models/gemini-3-flash-preview"},
                ]
            },
        )

    from google.oauth2 import service_account

    captured_info = {}

    def fake_from_service_account_info(info, scopes=None):
        captured_info["info"] = info
        captured_info["scopes"] = scopes
        return credentials

    monkeypatch.setattr(
        service_account.Credentials,
        "from_service_account_info",
        staticmethod(fake_from_service_account_info),
    )
    original_load_credentials = (
        ProviderGoogleGenAI._load_vertex_ai_service_account_credentials
    )

    def fake_load_credentials(self):
        assert (
            "vertex@example.iam.gserviceaccount.com"
            in self.provider_config["vertex_ai_credentials_json"]
        )
        return original_load_credentials(self)

    monkeypatch.setattr(
        ProviderGoogleGenAI,
        "_load_vertex_ai_service_account_credentials",
        fake_load_credentials,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.gemini_source.genai.Client",
        fake_client,
    )

    provider = ProviderGoogleGenAI(_vertex_key_json_config(), provider_settings={})
    await provider._http_client.aclose()
    provider._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=provider._get_vertex_ai_sdk_base_url(),
        timeout=provider.timeout,
    )

    try:
        assert captured_info["info"]["project_id"] == "demo-project"
        assert await provider.get_models() == ["google/gemini-3-flash-preview"]
        assert calls[0].url.path == "/v1beta1/publishers/google/models"
        assert calls[0].headers["authorization"] == "Bearer ya29.fake-token"
    finally:
        await provider.terminate()


def test_vertex_ai_config_template_defaults_to_json_and_global():
    provider_metadata = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
    template = provider_metadata["config_template"]["Google Vertex AI"]
    assert template["provider"] == "google-vertex-ai"
    assert template["type"] == "googlegenai_chat_completion"
    assert template["vertex_ai_auth_type"] == "json"
    assert template["vertex_ai_location"] == "global"
    assert template["api_base"] == "https://aiplatform.googleapis.com/v1"
    assert template["gm_safety_settings"]["harassment"] == "BLOCK_MEDIUM_AND_ABOVE"
    assert template["gm_thinking_config"] == {"budget": 0, "level": "HIGH"}

    items = provider_metadata["items"]
    assert items["vertex_ai_auth_type"]["options"] == ["json", "api_key"]
    assert items["vertex_ai_api_key"]["type"] == "list"
    assert items["vertex_ai_api_key"]["button_text"] == "API Key"
    assert items["vertex_ai_api_key"]["dialog_title"] == "API Key"
    assert items["vertex_ai_api_key"]["prefer_single_item"] is True
    assert items["vertex_ai_api_key"]["condition"] == {
        "provider": "google-vertex-ai",
        "vertex_ai_auth_type": "api_key",
    }
    assert items["vertex_ai_location"]["condition"] == {
        "provider": "google-vertex-ai",
    }
    assert items["vertex_ai_project_id"]["invisible"] is True
    assert items["vertex_ai_credentials_path"]["invisible"] is True
    assert items["vertex_ai_credentials_json"]["condition"] == {
        "provider": "google-vertex-ai",
        "vertex_ai_auth_type": "json",
    }


def test_vertex_ai_config_metadata_i18n_keys_exist_for_all_locales():
    locales_dir = (
        Path(__file__).resolve().parents[1] / "dashboard" / "src" / "i18n" / "locales"
    )
    expected_keys = {
        "google_vertex_ai",
        "vertex_ai_auth_type",
        "vertex_ai_api_key",
        "vertex_ai_project_id",
        "vertex_ai_location",
        "vertex_ai_credentials_path",
        "vertex_ai_credentials_json",
    }

    for locale in ("zh-CN", "en-US", "ru-RU"):
        metadata_path = locales_dir / locale / "features" / "config-metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        provider_translations = metadata["provider_group"]["provider"]

        assert expected_keys <= provider_translations.keys()


def test_vertex_ai_chinese_i18n_matches_requested_copy():
    metadata_path = (
        Path(__file__).resolve().parents[1]
        / "dashboard"
        / "src"
        / "i18n"
        / "locales"
        / "zh-CN"
        / "features"
        / "config-metadata.json"
    )
    provider_translations = json.loads(metadata_path.read_text(encoding="utf-8"))[
        "provider_group"
    ]["provider"]

    assert provider_translations["vertex_ai_auth_type"]["description"] == "密钥格式"
    assert provider_translations["vertex_ai_credentials_json"]["hint"] == (
        "Google Cloud 服务账号 JSON 可在该网址创建获得 "
        "https://console.cloud.google.com/iam-admin/serviceaccounts"
    )
    assert (
        provider_translations["vertex_ai_api_key"]["hint"]
        == "在 Vertex AI API Key、服务账号 JSON 选择其一使用即可。"
    )
