import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.core.provider import Provider
from astrbot.core.utils.image_caption_cache import (
    ImageCaptionCache,
    image_caption_cache,
)


@pytest.mark.asyncio
async def test_group_chat_context_reuses_cached_image_caption(tmp_path):
    image_caption_cache.clear()
    image_path = tmp_path / "same-image.png"
    image_path.write_bytes(b"same-image-bytes")

    provider = MagicMock(spec=Provider)
    provider.provider_config = {"id": "caption-provider"}
    provider.text_chat = AsyncMock(
        return_value=MagicMock(completion_text="cached caption")
    )

    context = MagicMock()
    context.get_provider_by_id.return_value = provider

    group_chat_context = GroupChatContext(MagicMock(), context)

    caption1 = await group_chat_context.get_image_caption(
        str(image_path),
        "caption-provider",
        "Please describe the image using Chinese.",
        600,
    )
    caption2 = await group_chat_context.get_image_caption(
        str(image_path),
        "caption-provider",
        "Please describe the image using Chinese.",
        600,
    )

    assert caption1 == "cached caption"
    assert caption2 == "cached caption"
    provider.text_chat.assert_awaited_once()
    image_caption_cache.clear()


@pytest.mark.asyncio
async def test_image_caption_cache_releases_per_key_lock_after_waiters_complete():
    cache = ImageCaptionCache()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def caption_factory() -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "cached caption"

    task1 = asyncio.create_task(
        cache.get_or_create(
            provider_id="caption-provider",
            prompt="Please describe the image using Chinese.",
            image_urls=["same-image.png"],
            ttl_seconds=600,
            caption_factory=caption_factory,
        )
    )
    await started.wait()
    task2 = asyncio.create_task(
        cache.get_or_create(
            provider_id="caption-provider",
            prompt="Please describe the image using Chinese.",
            image_urls=["same-image.png"],
            ttl_seconds=600,
            caption_factory=caption_factory,
        )
    )

    await asyncio.sleep(0)
    assert len(cache._locks) == 1

    release.set()

    assert await task1 == "cached caption"
    assert await task2 == "cached caption"
    assert calls == 1
    assert cache._locks == {}


@pytest.mark.asyncio
async def test_group_chat_context_default_provider_cache_identity_is_stable_per_provider(
    tmp_path,
):
    image_caption_cache.clear()
    image_path = tmp_path / "same-image.png"
    image_path.write_bytes(b"same-image-bytes")

    provider1 = MagicMock(spec=Provider)
    provider1.provider_config = {"type": "openai_chat_completion"}
    provider1.get_model.return_value = "gpt-4o"
    provider1.text_chat = AsyncMock(
        return_value=MagicMock(completion_text="caption from provider one")
    )

    provider2 = MagicMock(spec=Provider)
    provider2.provider_config = {"type": "google_genai"}
    provider2.get_model.return_value = "gemini-2.5-pro"
    provider2.text_chat = AsyncMock(
        return_value=MagicMock(completion_text="caption from provider two")
    )

    context = MagicMock()
    context.get_using_provider.side_effect = [provider1, provider2]

    group_chat_context = GroupChatContext(MagicMock(), context)

    caption1 = await group_chat_context.get_image_caption(
        str(image_path),
        "",
        "Please describe the image using Chinese.",
        600,
    )
    caption2 = await group_chat_context.get_image_caption(
        str(image_path),
        "",
        "Please describe the image using Chinese.",
        600,
    )

    assert caption1 == "caption from provider one"
    assert caption2 == "caption from provider two"
    provider1.text_chat.assert_awaited_once()
    provider2.text_chat.assert_awaited_once()
    image_caption_cache.clear()
