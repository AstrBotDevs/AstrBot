"""Image-byte budgets must not change history or token accounting."""

import base64
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from astrbot.core.agent.context.compressor import LLMSummaryCompressor
from astrbot.core.agent.context.image_budget import (
    get_image_encoded_byte_limit,
    validate_context_image_bytes,
)
from astrbot.core.agent.message import Message
from astrbot.core.exceptions import ProviderRequestTooLargeError
from astrbot.core.utils.image_media_store import ImageMediaStore
from astrbot.core.utils.media_utils import ImagePayloadTooLargeError


@pytest.mark.parametrize("limit", [None, True, False, 0, -1, "100"])
def test_invalid_provider_image_limit_uses_default(limit):
    assert (
        get_image_encoded_byte_limit(
            {"image_compress_options": {"max_encoded_bytes": limit}}
        )
        == 4 * 1024 * 1024
    )


def test_provider_image_limit_is_respected():
    assert (
        get_image_encoded_byte_limit(
            {"image_compress_options": {"max_encoded_bytes": 16 * 1024 * 1024}}
        )
        == 16 * 1024 * 1024
    )


@pytest.mark.parametrize("as_models", [False, True])
def test_byte_budget_does_not_rewrite_history(as_models):
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AAAA"},
                }
            ],
        }
    ]
    messages = (
        [Message.model_validate(item) for item in history] if as_models else history
    )
    before = copy.deepcopy(messages)
    assert validate_context_image_bytes(messages, 4) == 4
    with pytest.raises(ImagePayloadTooLargeError):
        validate_context_image_bytes(messages, 3)
    assert messages == before


def test_reference_size_is_checked_without_opening_media():
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_media_ref",
                    "media_id": "a" * 64,
                    "byte_size": 12,
                    "mime_type": "image/png",
                    "version": 1,
                }
            ],
        }
    ]
    assert validate_context_image_bytes(history, 16) == 16
    with pytest.raises(ImagePayloadTooLargeError):
        validate_context_image_bytes(history, 15)


@pytest.mark.asyncio
@pytest.mark.parametrize("vision", [True, False])
async def test_summary_loads_only_its_selected_images(tmp_path, monkeypatch, vision):
    image_path = tmp_path / "old.png"
    Image.new("RGB", (8, 8), "blue").save(image_path)
    original = image_path.read_bytes()
    store = ImageMediaStore(tmp_path / "media")
    old_ref = store.put(original, detail="high", image_id="old-image")
    messages = [
        Message.model_validate({"role": "user", "content": [old_ref.model_dump()]}),
        Message(role="assistant", content="old answer"),
        Message.model_validate(
            {
                "role": "user",
                "content": [{**old_ref.model_dump(), "media_id": "f" * 64}],
            }
        ),
    ]
    before = [message.model_dump() for message in messages]
    opened = []
    original_read = store.read

    def read(ref, allowed_ids):
        opened.append(ref.media_id)
        return original_read(ref, allowed_ids)

    monkeypatch.setattr(store, "read", read)
    provider = SimpleNamespace(
        provider_config={"modalities": ["text", "image"] if vision else ["text"]},
        provider_settings={},
        text_chat=AsyncMock(return_value=SimpleNamespace(completion_text="summary")),
    )
    result = await LLMSummaryCompressor(
        provider, keep_recent_ratio=0, image_media_store=store
    )(messages)
    assert opened == ([old_ref.media_id] if vision else [])
    assert result[-1] is messages[-1]
    assert [message.model_dump() for message in messages] == before
    if vision:
        sent = provider.text_chat.call_args.kwargs["contexts"][0]
        image = sent["content"][0]["image_url"]
        assert base64.b64decode(image["url"].split(",", 1)[1]) == original
        assert image["detail"] == "high"
        assert image["id"] == "old-image"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        MemoryError(),
        ImagePayloadTooLargeError("oversize"),
        ProviderRequestTooLargeError("413"),
    ],
)
async def test_summary_resource_failure_is_not_swallowed(error):
    provider = SimpleNamespace(
        provider_config={"modalities": ["text"]},
        provider_settings={},
        text_chat=AsyncMock(side_effect=error),
    )
    messages = [
        Message(role="user", content="old question"),
        Message(role="assistant", content="old answer"),
        Message(role="user", content="current question"),
    ]
    with pytest.raises(type(error)) as caught:
        await LLMSummaryCompressor(provider, keep_recent_ratio=0)(messages)
    assert caught.value is error
    assert provider.text_chat.await_count == 1
