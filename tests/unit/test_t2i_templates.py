from pathlib import Path

import pytest
from jinja2 import Environment

from astrbot.core.utils.t2i import template_manager
from astrbot.core.utils.t2i.network_strategy import NetworkRenderStrategy

TEMPLATE_DIR = (
    Path(__file__).resolve().parents[2]
    / "astrbot"
    / "core"
    / "utils"
    / "t2i"
    / "template"
)


def test_bundled_t2i_templates_encode_markdown_source_as_json_data():
    env = Environment(autoescape=False)
    payload = "</script></textarea><script>window.__astrbot_t2i_xss = true</script>"

    for template_name in (
        "base.html",
        "astrbot_powershell.html",
        "astrbot_vitepress.html",
    ):
        template_text = (TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
        rendered = env.from_string(template_text).render(
            text=payload,
            version="vtest",
        )

        assert "{{ text | safe }}" not in template_text
        assert "{{ text | tojson }}" in template_text
        assert 'type="application/json"' in template_text
        assert "window.DOMPurify.sanitize" in template_text
        assert "contentElement.innerHTML = marked.parse(source)" not in template_text
        assert ".value" not in template_text
        assert "<script>window.__astrbot_t2i_xss = true</script>" not in rendered
        assert rendered.count("</textarea>") == 0
        assert "\\u003c/script\\u003e" in rendered


def test_template_manager_hardens_existing_core_user_templates(tmp_path, monkeypatch):
    root_dir = tmp_path / "root"
    data_dir = tmp_path / "data"
    builtin_dir = root_dir / "astrbot" / "core" / "utils" / "t2i" / "template"
    user_dir = data_dir / "t2i_templates"
    builtin_dir.mkdir(parents=True)
    user_dir.mkdir(parents=True)

    unsafe_template = """
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<textarea id="markdown-source" hidden>{{ text | safe }}</textarea>
<script>
  const contentElement = document.getElementById("content");
  const source = document.getElementById("markdown-source").value;
  contentElement.innerHTML = marked.parse(source);
</script>
"""
    (builtin_dir / "base.html").write_text(unsafe_template, encoding="utf-8")
    (user_dir / "base.html").write_text(unsafe_template, encoding="utf-8")

    monkeypatch.setattr(template_manager, "get_astrbot_path", lambda: str(root_dir))
    monkeypatch.setattr(
        template_manager,
        "get_astrbot_data_path",
        lambda: str(data_dir),
    )

    template_manager.TemplateManager()
    hardened = (user_dir / "base.html").read_text(encoding="utf-8")

    assert "{{ text | safe }}" not in hardened
    assert "{{ text | tojson }}" in hardened
    assert 'type="application/json"' in hardened
    assert "JSON.parse(sourceNode.textContent" in hardened
    assert "window.DOMPurify.sanitize" in hardened
    assert "contentElement.innerHTML = marked.parse(source)" not in hardened


def test_network_strategy_hardens_custom_templates_before_rendering():
    unsafe_template = """
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<textarea id="markdown-source" hidden>{{ text | safe }}</textarea>
<script>
  const contentElement = document.getElementById("content");
  const source = document.getElementById("markdown-source").value;
  contentElement.innerHTML = marked.parse(source);
</script>
"""

    hardened, tmpl_data = NetworkRenderStrategy._prepare_template_sync(
        unsafe_template,
        {"text": "</textarea><script>x</script>"},
    )

    assert tmpl_data["text"] == "</textarea><script>x</script>"
    assert "{{ text | safe }}" not in hardened
    assert "{{ text | tojson }}" in hardened
    assert 'type="application/json"' in hardened
    assert "JSON.parse(sourceNode.textContent" in hardened
    assert "window.DOMPurify.sanitize" in hardened
    assert "contentElement.innerHTML = marked.parse(source)" not in hardened


def test_template_validation_rejects_unsafe_text_safe_filter():
    with pytest.raises(ValueError, match="unsafe safe filter"):
        template_manager.validate_template_content(
            '<textarea id="markdown-source">{{ text | safe }}</textarea>',
        )
