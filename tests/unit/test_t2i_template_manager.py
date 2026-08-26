from pathlib import Path

import pytest

from astrbot.core.utils.t2i import template_manager
from astrbot.core.utils.t2i.template_manager import TemplateManager


@pytest.fixture
def template_paths(tmp_path: Path, monkeypatch):
    root = tmp_path / "root"
    builtin_dir = root / "astrbot" / "core" / "utils" / "t2i" / "template"
    builtin_dir.mkdir(parents=True)
    data_dir = tmp_path / "data"
    for filename in TemplateManager.CORE_TEMPLATES:
        (builtin_dir / filename).write_text(f"builtin {filename}", encoding="utf-8")

    monkeypatch.setattr(template_manager, "get_astrbot_path", lambda: str(root))
    monkeypatch.setattr(
        template_manager, "get_astrbot_data_path", lambda: str(data_dir)
    )
    return builtin_dir, data_dir / "t2i_templates"


def test_template_manager_does_not_copy_builtin_templates(template_paths):
    builtin_dir, user_dir = template_paths

    manager = TemplateManager()

    assert not (user_dir / "base.html").exists()
    assert manager.get_template("base") == (builtin_dir / "base.html").read_text(
        encoding="utf-8"
    )


def test_template_manager_removes_unmodified_legacy_copy(template_paths):
    builtin_dir, user_dir = template_paths
    user_dir.mkdir(parents=True)
    (user_dir / "base.html").write_text(
        (builtin_dir / "base.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    manager = TemplateManager()

    assert not (user_dir / "base.html").exists()
    assert manager.get_template("base") == "builtin base.html"


def test_template_manager_backs_up_cdn_legacy_core_template(template_paths):
    _, user_dir = template_paths
    user_dir.mkdir(parents=True)
    legacy = '<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script><textarea id="markdown-source"></textarea>'
    (user_dir / "base.html").write_text(legacy, encoding="utf-8")

    manager = TemplateManager()

    assert manager.get_template("base") == "builtin base.html"
    assert (user_dir / "base.html.legacy").read_text(encoding="utf-8") == legacy


def test_template_manager_keeps_explicit_core_override(template_paths):
    _, user_dir = template_paths
    user_dir.mkdir(parents=True)
    (user_dir / "base.html").write_text("custom template", encoding="utf-8")

    manager = TemplateManager()

    assert manager.get_template("base") == "custom template"


def test_reset_default_template_removes_core_overrides_only(template_paths):
    _, user_dir = template_paths
    user_dir.mkdir(parents=True)
    (user_dir / "base.html").write_text("custom base", encoding="utf-8")
    (user_dir / "custom.html").write_text("custom", encoding="utf-8")
    manager = TemplateManager()

    manager.reset_default_template()

    assert manager.get_template("base") == "builtin base.html"
    assert manager.get_template("custom") == "custom"


def test_template_manager_removes_hashed_unmodified_legacy_copy(
    template_paths, monkeypatch
):
    _, user_dir = template_paths
    user_dir.mkdir(parents=True)
    (user_dir / "base.html").write_text(
        "previous unmodified builtin\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        template_manager,
        "_LEGACY_UNMODIFIED_CORE_TEMPLATE_HASHES",
        {
            "base.html": frozenset(
                {
                    "96d9ae2f1a14756153a7809f25406fdbd074896e05d738f1972600dfd16dc566",
                }
            )
        },
    )

    manager = TemplateManager()

    assert not (user_dir / "base.html").exists()
    assert manager.get_template("base") == "builtin base.html"


def test_builtin_base_template_stays_offline():
    content = (
        (
            Path(__file__).resolve().parents[2]
            / "astrbot"
            / "core"
            / "utils"
            / "t2i"
            / "template"
            / "base.html"
        )
        .read_text(encoding="utf-8")
        .replace("\r\n", "\n")
    )

    assert "https://fonts.googleapis.com" not in content
    assert "cdn.jsdelivr.net" not in content
    assert 'src="http' not in content
    assert 'href="http' not in content
    assert "{{ rendered_html | safe }}" in content
    assert "markdown-source" not in content
    assert "marked.min.js" not in content
