from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from jinja2.sandbox import SandboxedEnvironment

import astrbot.core.utils.t2i.network_strategy as network_strategy
from astrbot.core.utils.t2i.network_strategy import (
    SHIKI_RUNTIME_SCRIPT_ID,
    NetworkRenderStrategy,
    inject_shiki_runtime,
)
from astrbot.core.utils.t2i.template_manager import TemplateManager

TEMPLATE_DIR = (
    Path(__file__).resolve().parents[2]
    / "astrbot"
    / "core"
    / "utils"
    / "t2i"
    / "template"
)


@pytest.fixture
def temp_astrbot_root(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_render_passes_raw_text_template_data(
    temp_astrbot_root: Path,
) -> None:
    strategy = NetworkRenderStrategy("https://example.com")
    strategy.get_template = AsyncMock(return_value="<html>{{ text }}</html>")
    strategy.render_custom_template = AsyncMock(return_value="rendered.png")

    text = "hello `world` ${name} \\ </script>"
    result = await strategy.render(text, return_url=True)

    assert result == "rendered.png"
    strategy.render_custom_template.assert_awaited_once()
    _, tmpl_data, return_url = strategy.render_custom_template.await_args.args
    assert tmpl_data["text"] == text
    assert "text_base64" not in tmpl_data
    assert return_url is True


def test_builtin_templates_read_legacy_text_from_hidden_textarea() -> None:
    for template_name in (
        "base.html",
        "astrbot_powershell.html",
        "astrbot_vitepress.html",
    ):
        content = (TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
        assert '<textarea id="markdown-source" hidden>' in content
        assert "{{ text | safe }}" in content
        assert 'document.getElementById("markdown-source").value' in content
        assert "const source = `{{ text | safe }}`" not in content
        assert "{{ text_base64 }}" not in content
        assert "{{ shiki_runtime | safe }}" not in content


def test_template_manager_migrates_legacy_user_template(
    temp_astrbot_root: Path,
) -> None:
    user_template_dir = temp_astrbot_root / "data" / "t2i_templates"
    user_template_dir.mkdir(parents=True)
    stale_template = user_template_dir / "astrbot_vitepress.html"
    stale_template.write_text(
        """<html>
<body>
  <script>{{ shiki_runtime | safe }}</script>
  <script>
    (function () {
      const source = decodeBase64Utf8("{{ text_base64 }}");

      function decodeBase64Utf8(base64Text) {
        const binary = window.atob(base64Text || "");
        const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));

        if (window.TextDecoder) {
          return new TextDecoder().decode(bytes);
        }

        let fallback = "";
        bytes.forEach((byte) => {
          fallback += String.fromCharCode(byte);
        });
        return decodeURIComponent(escape(fallback));
      }
    })();
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )

    manager = TemplateManager()

    content = manager.get_template("astrbot_vitepress")
    assert "{{ text | safe }}" in content
    assert '<textarea id="markdown-source" hidden>' in content
    assert 'document.getElementById("markdown-source").value' in content
    assert "{{ text_base64 }}" not in content
    assert "{{ shiki_runtime | safe }}" not in content
    assert "function decodeBase64Utf8" not in content
    assert "`{{ text | safe }}`" not in content
    assert stale_template.read_text(encoding="utf-8") == content


def test_template_manager_migrates_plain_script_markdown_source() -> None:
    content = TemplateManager._migrate_legacy_template_content(
        """<html>
<body>
  <script id="markdown-source" type="text/plain">{{ text | safe }}</script>
  <script>
    const source = document.getElementById("markdown-source").textContent;
  </script>
</body>
</html>
""",
    )

    assert '<textarea id="markdown-source" hidden>' in content
    assert '<script id="markdown-source" type="text/plain">' not in content
    assert 'document.getElementById("markdown-source").value' in content
    assert content.count('id="markdown-source"') == 1


def test_inject_shiki_runtime_adds_runtime_before_head_close(monkeypatch) -> None:
    monkeypatch.setattr(
        "astrbot.core.utils.t2i.network_strategy.get_shiki_runtime",
        lambda: "window.AstrBotT2IShiki = {};",
    )

    html = "<html><head><title>T2I</title></head><body></body></html>"

    injected = inject_shiki_runtime(html)

    assert f'id="{SHIKI_RUNTIME_SCRIPT_ID}"' in injected
    assert "window.AstrBotT2IShiki = {};" in injected
    assert "{% raw %}" in injected
    assert "{% endraw %}" in injected
    assert injected.index(SHIKI_RUNTIME_SCRIPT_ID) < injected.lower().index("</head>")


def test_injected_shiki_runtime_survives_jinja_render() -> None:
    html = "<html><head></head><body>{{ text | safe }}</body></html>"

    rendered = (
        SandboxedEnvironment()
        .from_string(inject_shiki_runtime(html))
        .render(
            {"text": "hello"},
        )
    )

    assert f'id="{SHIKI_RUNTIME_SCRIPT_ID}"' in rendered
    assert "{% raw %}" not in rendered
    assert "{% endraw %}" not in rendered
    assert "hello" in rendered


def test_inject_shiki_runtime_keeps_legacy_placeholder_templates(monkeypatch) -> None:
    monkeypatch.setattr(
        "astrbot.core.utils.t2i.network_strategy.get_shiki_runtime",
        lambda: "window.AstrBotT2IShiki = {};",
    )
    html = "<script>{{ shiki_runtime | safe }}</script><body></body>"

    assert inject_shiki_runtime(html) == html


@pytest.mark.asyncio
async def test_render_custom_template_injects_runtime_without_template_data(
    monkeypatch,
    temp_astrbot_root: Path,
) -> None:
    captured = {}

    async def fake_download_image_by_url(url, *, post, post_data):
        captured["url"] = url
        captured["post"] = post
        captured["post_data"] = post_data
        return "image.png"

    monkeypatch.setattr(network_strategy, "get_shiki_runtime", lambda: "runtime")
    monkeypatch.setattr(
        network_strategy,
        "download_image_by_url",
        fake_download_image_by_url,
    )
    strategy = NetworkRenderStrategy("https://example.com")

    result = await strategy.render_custom_template(
        "<html><head></head><body>{{ text | safe }}</body></html>",
        {"text": "hello"},
        return_url=False,
    )

    assert result == "image.png"
    assert f'id="{SHIKI_RUNTIME_SCRIPT_ID}"' in captured["post_data"]["tmpl"]
    assert "shiki_runtime" not in captured["post_data"]["tmpldata"]
    assert captured["post_data"]["options"]["quality"] == 40
    assert "device_scale_factor_level" not in captured["post_data"]["options"]


@pytest.mark.asyncio
async def test_render_custom_template_keeps_legacy_runtime_placeholder(
    monkeypatch,
    temp_astrbot_root: Path,
) -> None:
    captured = {}

    async def fake_download_image_by_url(url, *, post, post_data):
        captured["post_data"] = post_data
        return "image.png"

    monkeypatch.setattr(network_strategy, "get_shiki_runtime", lambda: "runtime")
    monkeypatch.setattr(
        network_strategy,
        "download_image_by_url",
        fake_download_image_by_url,
    )
    strategy = NetworkRenderStrategy("https://example.com")
    tmpl = "<script>{{ shiki_runtime | safe }}</script><body>{{ text | safe }}</body>"

    await strategy.render_custom_template(tmpl, {"text": "hello"}, return_url=False)

    assert captured["post_data"]["tmpl"] == tmpl
    assert captured["post_data"]["tmpldata"]["shiki_runtime"] == "runtime"
