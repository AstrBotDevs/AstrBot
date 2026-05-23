from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from astrbot.core.utils.t2i.network_strategy import NetworkRenderStrategy


@pytest.mark.asyncio
async def test_network_strategy_render_preserves_backticks():
    strategy = NetworkRenderStrategy()
    strategy.get_template = AsyncMock(return_value="template")
    strategy.render_custom_template = AsyncMock(return_value="rendered")

    result = await strategy.render("```python\nprint('hi')\n```")

    assert result == "rendered"
    _, tmpl_data, return_url = strategy.render_custom_template.call_args.args
    assert tmpl_data["text"] == "```python\nprint('hi')\n```"
    assert return_url is False


def test_t2i_templates_use_json_serialization_for_text():
    template_paths = sorted(
        Path("astrbot/core/utils/t2i/template").glob("*.html"),
    )

    assert template_paths

    for template_path in template_paths:
        content = template_path.read_text(encoding="utf-8")
        assert "text | safe" not in content
        assert "text | tojson" in content
