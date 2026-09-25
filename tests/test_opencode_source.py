import hashlib
from types import SimpleNamespace

import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.provider.sources.opencode_go_source import ProviderOpenCodeGo
from astrbot.core.provider.sources.opencode_zen_source import ProviderOpenCodeZen


class _DelegateStub:
    def __init__(self, models: list[str] | None = None) -> None:
        self.models = models or []
        self.chat_kwargs = None
        self.stream_kwargs = None

    async def get_models(self) -> list[str]:
        return self.models

    async def text_chat(self, **kwargs):
        self.chat_kwargs = kwargs
        return SimpleNamespace(role="assistant")

    async def text_chat_stream(self, **kwargs):
        self.stream_kwargs = kwargs
        yield SimpleNamespace(role="assistant")


def _unit_provider(
    provider_class: type[ProviderOpenCodeGo],
    delegate: _DelegateStub,
) -> ProviderOpenCodeGo:
    """Build an OpenCode provider without creating an HTTP client.

    Args:
        provider_class: OpenCode adapter class to instantiate.
        delegate: Stub receiving delegated calls.

    Returns:
        Partially initialized provider suitable for unit tests.
    """
    provider = provider_class.__new__(provider_class)
    provider.openai_provider = delegate
    provider.model_name = provider_class.DEFAULT_MODEL
    provider._fallback_session_id = "fallback-session"
    return provider


def test_opencode_templates_are_available() -> None:
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    assert templates["OpenCode Go"]["type"] == "opencode_go_chat_completion"
    assert templates["OpenCode Zen"]["type"] == "opencode_zen_chat_completion"


@pytest.mark.asyncio
async def test_opencode_go_prefixes_models_and_filters_messages_endpoint() -> None:
    provider = _unit_provider(
        ProviderOpenCodeGo,
        _DelegateStub(
            [
                "kimi-k2.6",
                "opencode-go/gpt-5.6-luna",
                "muse-spark-1.3-contributor",
                "minimax-m2.7",
            ]
        ),
    )

    assert await provider.get_models() == [
        "gpt-5.6-luna",
        "kimi-k2.6",
        "muse-spark-1.3-contributor",
    ]


@pytest.mark.asyncio
async def test_opencode_zen_supports_responses_and_rejects_other_endpoints() -> None:
    provider = _unit_provider(
        ProviderOpenCodeZen,
        _DelegateStub(
            [
                "kimi-k2.6",
                "muse-spark-1.3-contributor-free",
                "claude-sonnet-4-6",
                "gemini-3.1-pro",
            ]
        ),
    )

    assert await provider.get_models() == [
        "kimi-k2.6",
        "muse-spark-1.3-contributor-free",
    ]
    with pytest.raises(ValueError, match="/v1/messages"):
        provider._resolve_model("opencode/claude-sonnet-4-6")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_class", "model", "delegate_class"),
    [
        (ProviderOpenCodeGo, "opencode-go/kimi-k2.6", ProviderOpenAIOfficial),
        (
            ProviderOpenCodeGo,
            "opencode-go/muse-spark-1.3-contributor",
            ProviderOpenAIResponses,
        ),
        (
            ProviderOpenCodeZen,
            "opencode/muse-spark-1.3-contributor-free",
            ProviderOpenAIResponses,
        ),
    ],
)
async def test_opencode_selects_delegate_for_model_endpoint(
    provider_class,
    model,
    delegate_class,
) -> None:
    provider = provider_class({"model": model, "key": ["test-key"]}, {})
    try:
        assert isinstance(provider.openai_provider, delegate_class)
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_sends_coding_agent_and_hashed_session_headers() -> None:
    delegate = _DelegateStub()
    provider = _unit_provider(ProviderOpenCodeGo, delegate)
    provider.provider_config = {"custom_headers": {"x-source": "configured"}}
    provider.api_base = "https://example.test/v1"

    config = provider._build_delegate_config(model="kimi-k2.6")
    await provider.text_chat(
        prompt="hello",
        session_id="telegram:user:123",
        extra_headers={"x-request": "present"},
    )

    assert config["custom_headers"]["User-Agent"].startswith("AstrBot-Coding-Agent/")
    assert config["custom_headers"]["x-source"] == "configured"
    assert delegate.chat_kwargs["extra_headers"] == {
        "x-request": "present",
        "x-opencode-session": hashlib.sha256(b"telegram:user:123").hexdigest(),
    }


@pytest.mark.asyncio
async def test_opencode_stream_uses_stable_fallback_session() -> None:
    delegate = _DelegateStub()
    provider = _unit_provider(ProviderOpenCodeGo, delegate)

    responses = [item async for item in provider.text_chat_stream(prompt="hello")]

    assert responses
    assert delegate.stream_kwargs["extra_headers"]["x-opencode-session"] == (
        hashlib.sha256(b"fallback-session").hexdigest()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_class",
    [ProviderOpenAIOfficial, ProviderOpenAIResponses],
)
async def test_openai_payload_forwards_per_request_headers(provider_class) -> None:
    provider = provider_class(
        {"id": "test", "model": "test-model", "key": ["test-key"]},
        {},
    )
    try:
        payload, _ = await provider._prepare_chat_payload(
            "hello",
            extra_headers={"x-opencode-session": "session-hash"},
        )
        assert payload["extra_headers"] == {"x-opencode-session": "session-hash"}
    finally:
        await provider.terminate()
