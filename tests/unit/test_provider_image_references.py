import base64
from copy import deepcopy

import pytest
from PIL import Image

from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.utils.image_media_store import ImageMediaStore
from astrbot.core.utils.media_utils import ImagePayloadTooLargeError


@pytest.fixture
def image_context(tmp_path, monkeypatch):
    with Image.new("RGB", (4, 3), "red") as image:
        source = tmp_path / "source.png"
        image.save(source, "PNG")
    ref = ImageMediaStore(tmp_path / "media").put(source.read_bytes())
    context = [{"role": "user", "content": [ref.model_dump()]}]
    for module in ("openai_source", "anthropic_source", "gemini_source"):
        monkeypatch.setattr(
            f"astrbot.core.provider.sources.{module}.get_astrbot_data_path",
            lambda tmp_path=tmp_path: str(tmp_path),
        )
    return context


def _bare(adapter):
    instance = object.__new__(adapter)
    instance.provider_config = {}
    instance.provider_settings = {}
    instance.model_name = "test-model"
    instance.client = type(
        "Client", (), {"base_url": type("URL", (), {"host": ""})()}
    )()
    return instance


@pytest.mark.asyncio
async def test_openai_payload_materializes_reference_without_mutating(image_context):
    adapter = _bare(ProviderOpenAIOfficial)
    payload, _ = await adapter._prepare_chat_payload(None, contexts=image_context)
    assert payload["messages"][0]["content"][0]["image_url"]["url"].startswith(
        "data:image/"
    )
    assert image_context[0]["content"][0]["type"] == "image_media_ref"


@pytest.mark.asyncio
async def test_oversized_reference_fails_before_materialization(image_context):
    oversized = deepcopy(image_context)
    oversized[0]["content"][0]["byte_size"] = 10_000_000
    adapter = _bare(ProviderOpenAIOfficial)
    with pytest.raises(ImagePayloadTooLargeError):
        await adapter._prepare_chat_payload(None, contexts=oversized)


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_type", [ProviderOpenAIOfficial, ProviderGoogleGenAI])
async def test_provider_settings_control_reference_budget(adapter_type, image_context):
    adapter = _bare(adapter_type)
    adapter.provider_settings = {"image_compress_options": {"max_encoded_bytes": 1}}
    with pytest.raises(ImagePayloadTooLargeError):
        if adapter_type is ProviderOpenAIOfficial:
            await adapter._prepare_chat_payload(None, contexts=image_context)
        else:
            await adapter._prepare_conversation({"messages": image_context})

    adapter.provider_settings = {
        "image_compress_options": {"max_encoded_bytes": 1024 * 1024}
    }
    if adapter_type is ProviderOpenAIOfficial:
        payload, _ = await adapter._prepare_chat_payload(None, contexts=image_context)
        assert payload["messages"][0]["content"][0]["image_url"]
    else:
        contents = await adapter._prepare_conversation({"messages": image_context})
        assert contents[0].parts[0].inline_data is not None


@pytest.mark.asyncio
async def test_text_only_modality_scrubs_missing_oversized_reference_without_read(
    image_context,
):
    missing = deepcopy(image_context)
    missing[0]["content"][0]["media_id"] = "f" * 64
    missing[0]["content"][0]["byte_size"] = 100_000_000
    adapter = _bare(ProviderOpenAIOfficial)
    adapter.provider_config = {"modalities": ["text"]}
    payload, _ = await adapter._prepare_chat_payload(None, contexts=missing)
    assert payload["messages"][0]["content"] == [{"type": "text", "text": "[Image]"}]


@pytest.mark.asyncio
async def test_anthropic_text_chat_materializes_reference_without_mutating(
    image_context,
):
    adapter = _bare(ProviderAnthropic)
    captured = {}

    async def query(payloads, tools, **kwargs):
        captured.update(payloads)
        raise RuntimeError("stop after capture")

    adapter._query = query
    with pytest.raises(RuntimeError, match="stop after capture"):
        await adapter.text_chat(contexts=deepcopy(image_context))
    image = captured["messages"][0]["content"][0]
    assert image["source"]["type"] == "base64"
    assert image_context[0]["content"][0]["type"] == "image_media_ref"


@pytest.mark.asyncio
async def test_anthropic_provider_settings_control_reference_budget(image_context):
    adapter = _bare(ProviderAnthropic)
    adapter.provider_settings = {"image_compress_options": {"max_encoded_bytes": 1}}
    with pytest.raises(ImagePayloadTooLargeError):
        await adapter.text_chat(contexts=image_context)


@pytest.mark.asyncio
async def test_gemini_conversation_materializes_reference(image_context):
    adapter = _bare(ProviderGoogleGenAI)
    contents = await adapter._prepare_conversation({"messages": image_context})
    assert contents[0].parts[0].inline_data is not None
    assert image_context[0]["content"][0]["type"] == "image_media_ref"


def test_anthropic_payload_detects_data_uri_from_prefix_without_copying_payload(
    monkeypatch,
):
    adapter = _bare(ProviderAnthropic)
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"x" * 4096
    encoded = base64.b64encode(image_bytes).decode()
    detected_prefixes = []

    def detect_mime(prefix: bytes) -> str:
        detected_prefixes.append(prefix)
        return "image/png"

    monkeypatch.setattr(adapter, "_detect_image_mime_type", detect_mime)
    _, messages = adapter._prepare_payload(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    }
                ],
            }
        ]
    )

    assert detected_prefixes == [image_bytes[:48]]
    assert messages[0]["content"][0]["source"]["data"] == encoded


@pytest.mark.asyncio
async def test_gemini_data_uri_skips_shared_resolver(monkeypatch):
    adapter = _bare(ProviderGoogleGenAI)
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"payload"
    encoded = base64.b64encode(image_bytes).decode()

    async def fail_if_resolved(*_args, **_kwargs):
        raise AssertionError("data URLs should not go through the shared resolver")

    monkeypatch.setattr(
        "astrbot.core.provider.sources.gemini_source.resolve_media_ref_to_base64_data",
        fail_if_resolved,
    )
    contents = await adapter._prepare_conversation(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        }
                    ],
                }
            ]
        }
    )

    assert contents[0].parts is not None
    assert contents[0].parts[0].inline_data.data == image_bytes
    assert contents[0].parts[0].inline_data.mime_type == "image/png"
