from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.core.provider import Provider
from astrbot.core.utils.image_caption_cache import image_caption_cache


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
