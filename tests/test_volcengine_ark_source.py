import sys
import types
from importlib import import_module as _real_import_module

import pytest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.register import provider_cls_map
from astrbot.core.provider.sources.volcengine_ark_source import ProviderVolcengineArk


def _make_provider_config() -> dict:
    return {
        "id": "test-ark",
        "type": "volcengine_ark_chat_completion",
        "model": "ep-test",
        "key": ["test-key"],
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    }


def _install_fake_sdk(monkeypatch: pytest.MonkeyPatch) -> type:
    class FakeResponses:
        def __init__(self, owner) -> None:
            self.owner = owner

        def create(self, **kwargs):
            self.owner.last_kwargs = kwargs
            if kwargs.get("stream"):
                return [
                    types.SimpleNamespace(
                        type="response.output_text.delta",
                        delta="Hel",
                        response_id="resp_stream",
                    ),
                    types.SimpleNamespace(
                        type="response.reasoning.delta",
                        delta="Think",
                        response_id="resp_stream",
                    ),
                    types.SimpleNamespace(
                        type="response.completed",
                        response=types.SimpleNamespace(
                            id="resp_stream",
                            output=[
                                types.SimpleNamespace(
                                    type="reasoning",
                                    summary=[
                                        types.SimpleNamespace(
                                            type="summary_text",
                                            text="Think",
                                        )
                                    ],
                                ),
                                types.SimpleNamespace(
                                    type="message",
                                    role="assistant",
                                    content=[
                                        types.SimpleNamespace(
                                            type="output_text",
                                            text="Hello",
                                        )
                                    ],
                                ),
                            ],
                            usage=types.SimpleNamespace(
                                input_tokens=12,
                                output_tokens=4,
                                input_tokens_details=types.SimpleNamespace(
                                    cached_tokens=3
                                ),
                            ),
                        ),
                    ),
                ]
            return types.SimpleNamespace(
                id="resp_sync",
                output=[
                    types.SimpleNamespace(
                        type="reasoning",
                        summary=[
                            types.SimpleNamespace(type="summary_text", text="Plan")
                        ],
                    ),
                    types.SimpleNamespace(
                        type="function_call",
                        name="lookup",
                        call_id="call_1",
                        arguments='{"query":"moon"}',
                    ),
                    types.SimpleNamespace(
                        type="message",
                        role="assistant",
                        content=[
                            types.SimpleNamespace(type="output_text", text="Working")
                        ],
                    ),
                ],
                usage=types.SimpleNamespace(
                    input_tokens=10,
                    output_tokens=5,
                    input_tokens_details=types.SimpleNamespace(cached_tokens=2),
                ),
            )

    class FakeArk:
        last_instance = None

        def __init__(
            self,
            api_key,
            base_url=None,
            timeout=None,
            default_headers=None,
            http_client=None,
        ) -> None:
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout
            self.default_headers = default_headers
            self.http_client = http_client
            self.responses = FakeResponses(self)
            self.last_kwargs = None
            FakeArk.last_instance = self

        def close(self) -> None:
            return None

    fake_module = types.ModuleType("volcenginesdkarkruntime")
    fake_module.Ark = FakeArk
    monkeypatch.setitem(sys.modules, "volcenginesdkarkruntime", fake_module)
    return FakeArk


def test_volcengine_ark_provider_requires_sdk(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delitem(sys.modules, "volcenginesdkarkruntime", raising=False)

    def _raise_for_sdk(name: str, package=None):
        if name == "volcenginesdkarkruntime":
            raise ImportError("missing test sdk")
        return _real_import_module(name, package)

    monkeypatch.setattr(
        "astrbot.core.provider.sources.volcengine_ark_source.importlib.import_module",
        _raise_for_sdk,
    )

    with pytest.raises(ImportError, match="volcengine-python-sdk"):
        ProviderVolcengineArk(_make_provider_config(), {})


@pytest.mark.asyncio
async def test_volcengine_ark_text_chat_maps_payload_and_response(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_ark = _install_fake_sdk(monkeypatch)
    provider = ProviderVolcengineArk(_make_provider_config(), {})
    tool_set = ToolSet(
        [
            FunctionTool(
                name="lookup",
                description="Lookup something",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            )
        ]
    )

    try:
        response = await provider.text_chat(
            prompt="hello",
            system_prompt="be helpful",
            func_tool=tool_set,
        )

        last_kwargs = fake_ark.last_instance.last_kwargs
        assert last_kwargs is not None
        assert last_kwargs["model"] == "ep-test"
        assert last_kwargs["stream"] is False
        assert last_kwargs["input"][0]["role"] == "system"
        assert last_kwargs["input"][0]["content"][0]["text"] == "be helpful"
        assert last_kwargs["input"][1]["role"] == "user"
        assert last_kwargs["input"][1]["content"][0]["text"] == "hello"
        assert last_kwargs["tools"] == [
            {
                "type": "function",
                "name": "lookup",
                "description": "Lookup something",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]

        assert response.role == "tool"
        assert response.completion_text == "Working"
        assert response.reasoning_content == "Plan"
        assert response.tools_call_name == ["lookup"]
        assert response.tools_call_ids == ["call_1"]
        assert response.tools_call_args == [{"query": "moon"}]
        assert response.usage is not None
        assert response.usage.input_other == 8
        assert response.usage.input_cached == 2
        assert response.usage.output == 5
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_volcengine_ark_text_chat_stream_yields_chunks_and_final(
    monkeypatch: pytest.MonkeyPatch,
):
    _install_fake_sdk(monkeypatch)
    provider = ProviderVolcengineArk(_make_provider_config(), {})

    try:
        responses = []
        async for item in provider.text_chat_stream(prompt="hello"):
            responses.append(item)

        assert len(responses) == 3
        assert responses[0].is_chunk is True
        assert responses[0].completion_text == "Hel"
        assert responses[1].is_chunk is True
        assert responses[1].reasoning_content == "Think"
        assert responses[2].is_chunk is False
        assert responses[2].completion_text == "Hello"
        assert responses[2].reasoning_content == "Think"
        assert responses[2].usage is not None
        assert responses[2].usage.input_cached == 3
    finally:
        await provider.terminate()


def test_volcengine_ark_provider_registration():
    assert "volcengine_ark_chat_completion" in provider_cls_map
    assert (
        provider_cls_map["volcengine_ark_chat_completion"].cls_type
        is ProviderVolcengineArk
    )


def test_volcengine_ark_template_exists():
    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]["Volcengine Ark"]
    assert template["type"] == "volcengine_ark_chat_completion"
    assert template["provider_type"] == "chat_completion"
    assert template["provider"] == "volcengine"
    assert "model" in template
    assert "custom_extra_body" in template


@pytest.mark.asyncio
async def test_volcengine_ark_remote_image_uses_base64_transport(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    _install_fake_sdk(monkeypatch)
    provider = ProviderVolcengineArk(_make_provider_config(), {})
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    async def _fake_download_image_by_url(url: str, *args, **kwargs) -> str:
        assert url == "https://example.com/image.jpg"
        return str(image_path)

    monkeypatch.setattr(
        "astrbot.core.provider.sources.volcengine_ark_source.download_image_by_url",
        _fake_download_image_by_url,
    )

    try:
        part = await provider._resolve_image_part("https://example.com/image.jpg")
        assert part["type"] == "input_image"
        assert part["image_url"].startswith("file://")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_volcengine_ark_data_url_is_materialized_to_local_file(
    monkeypatch: pytest.MonkeyPatch,
):
    _install_fake_sdk(monkeypatch)
    provider = ProviderVolcengineArk(_make_provider_config(), {})

    try:
        part = await provider._resolve_image_part("data:image/png;base64,aGVsbG8=")
        assert part["type"] == "input_image"
        assert part["image_url"].startswith("file://")
    finally:
        await provider.terminate()
