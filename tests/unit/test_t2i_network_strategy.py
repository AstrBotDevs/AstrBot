import base64

import pytest

from astrbot.core.config import VERSION
from astrbot.core.utils.t2i.network_strategy import NetworkRenderStrategy


@pytest.mark.asyncio
async def test_network_render_strategy_passes_text_and_text_base64(monkeypatch):
    captured: dict = {}

    async def fake_get_template(self, name: str = "base") -> str:
        return "<html>{{ text }}</html>"

    async def fake_render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        return_url: bool = True,
        options: dict | None = None,
    ) -> str:
        captured["tmpl_str"] = tmpl_str
        captured["tmpl_data"] = tmpl_data
        captured["return_url"] = return_url
        captured["options"] = options
        return "ok"

    monkeypatch.setattr(NetworkRenderStrategy, "get_template", fake_get_template)
    monkeypatch.setattr(
        NetworkRenderStrategy,
        "render_custom_template",
        fake_render_custom_template,
    )

    strategy = NetworkRenderStrategy(base_url="https://example.com")
    await strategy.render("hello", return_url=True, template_name="base")

    assert captured["tmpl_str"] == "<html>{{ text }}</html>"
    assert captured["tmpl_data"]["text"] == "hello"
    assert captured["tmpl_data"]["text_base64"] == base64.b64encode(
        b"hello"
    ).decode("ascii")
    assert captured["tmpl_data"]["version"] == f"v{VERSION}"
