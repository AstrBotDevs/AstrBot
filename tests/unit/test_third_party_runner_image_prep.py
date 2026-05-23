from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party import (
    _prepare_images_for_third_party_runner,
)
from astrbot.core.provider.entities import ProviderRequest


@pytest.mark.asyncio
async def test_prepare_images_for_dashscope_uses_default_image_caption_provider() -> None:
    req = ProviderRequest(prompt="请帮我分析这张图", image_urls=["base64://image-data"])

    with patch(
        "astrbot.core.astr_main_agent._request_img_caption",
        new=AsyncMock(return_value="图片里有一只猫"),
    ) as request_img_caption:
        await _prepare_images_for_third_party_runner(
            req=req,
            runner_type="dashscope",
            provider_settings={"default_image_caption_provider_id": "vision-model"},
            plugin_context=object(),
        )

    request_img_caption.assert_awaited_once()
    assert req.prompt == "请帮我分析这张图\n<image_caption>图片里有一只猫</image_caption>"
    assert req.image_urls == []


@pytest.mark.asyncio
async def test_prepare_images_for_dashscope_falls_back_to_placeholder_when_needed() -> None:
    req = ProviderRequest(prompt=None, image_urls=["base64://image-data"])

    await _prepare_images_for_third_party_runner(
        req=req,
        runner_type="dashscope",
        provider_settings={},
        plugin_context=object(),
    )

    assert req.prompt == "[图片]"
    assert req.image_urls == []


@pytest.mark.asyncio
async def test_prepare_images_for_non_dashscope_keeps_images_untouched() -> None:
    req = ProviderRequest(prompt="hello", image_urls=["base64://image-data"])

    await _prepare_images_for_third_party_runner(
        req=req,
        runner_type="coze",
        provider_settings={"default_image_caption_provider_id": "vision-model"},
        plugin_context=object(),
    )

    assert req.prompt == "hello"
    assert req.image_urls == ["base64://image-data"]
