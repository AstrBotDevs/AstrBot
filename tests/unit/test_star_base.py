"""Tests for Star base class safety helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.star.base import Star


class DemoStar(Star):
    """Concrete test star."""


@pytest.mark.asyncio
async def test_text_to_image_handles_missing_context_config() -> None:
    star = DemoStar(context=SimpleNamespace())

    with patch(
        "astrbot.core.star.base.html_renderer.render_t2i",
        new=AsyncMock(return_value="ok"),
    ) as mock_render:
        result = await star.text_to_image("hello")

    assert result == "ok"
    mock_render.assert_awaited_once_with(
        "hello",
        return_url=True,
        template_name=None,
    )


@pytest.mark.asyncio
async def test_text_to_image_uses_context_get_config_when_available() -> None:
    context = SimpleNamespace(get_config=lambda: {"t2i_active_template": "my-template"})
    star = DemoStar(context=context)

    with patch(
        "astrbot.core.star.base.html_renderer.render_t2i",
        new=AsyncMock(return_value="ok"),
    ) as mock_render:
        await star.text_to_image("hello")

    assert mock_render.await_args.kwargs["template_name"] == "my-template"
