from pathlib import Path

import pytest

from astrbot.core.star.star import StarMetadata
from astrbot.dashboard.services.plugin_service import PluginService, PluginServiceError


class _FakeContext:
    def __init__(self, stars: list[StarMetadata]) -> None:
        self._stars = stars

    def get_all_stars(self) -> list[StarMetadata]:
        return self._stars


class _FakePluginManager:
    def __init__(self, root: Path, stars: list[StarMetadata]) -> None:
        self.reserved_plugin_path = root
        self.plugin_store_path = root
        self.context = _FakeContext(stars)


def _make_service(
    tmp_path: Path, readmes: dict[str, str] | None = None
) -> tuple[PluginService, Path]:
    plugin_dir = tmp_path / "demo"
    plugin_dir.mkdir()
    star = StarMetadata(name="demo", root_dir_name="demo", readmes=readmes or {})
    service = PluginService(None, _FakePluginManager(tmp_path, [star]))
    return service, plugin_dir


def test_legacy_readme_without_declaration(tmp_path: Path):
    service, plugin_dir = _make_service(tmp_path)
    (plugin_dir / "README.md").write_text("# hello", encoding="utf-8")

    payload, _message = service.get_plugin_readme("demo", "zh-CN")

    assert payload == {
        "content": "# hello",
        "resolved_locale": None,
        "available_locales": [],
    }


def test_declared_locale_is_preferred(tmp_path: Path):
    service, plugin_dir = _make_service(
        tmp_path,
        {
            "default": "README.md",
            "zh-CN": "README_zh.md",
            "en-US": "README_en.md",
        },
    )
    (plugin_dir / "README.md").write_text("default", encoding="utf-8")
    (plugin_dir / "README_zh.md").write_text("zh", encoding="utf-8")
    (plugin_dir / "README_en.md").write_text("en", encoding="utf-8")

    payload, _message = service.get_plugin_readme("demo", "zh-CN")
    assert payload["content"] == "zh"
    assert payload["resolved_locale"] == "zh-CN"
    assert payload["available_locales"] == ["zh-CN", "en-US"]

    payload, _message = service.get_plugin_readme("demo", "en_US")
    assert payload["content"] == "en"


def test_base_language_fallback(tmp_path: Path):
    service, plugin_dir = _make_service(
        tmp_path,
        {"default": "README.md", "zh": "README_zh.md"},
    )
    (plugin_dir / "README.md").write_text("default", encoding="utf-8")
    (plugin_dir / "README_zh.md").write_text("zh", encoding="utf-8")

    payload, _message = service.get_plugin_readme("demo", "zh-TW")

    assert payload["content"] == "zh"
    assert payload["resolved_locale"] == "zh"


def test_unknown_locale_falls_back_to_default(tmp_path: Path):
    service, plugin_dir = _make_service(
        tmp_path,
        {"default": "README.md", "zh-CN": "README_zh.md"},
    )
    (plugin_dir / "README.md").write_text("default", encoding="utf-8")
    (plugin_dir / "README_zh.md").write_text("zh", encoding="utf-8")

    payload, _message = service.get_plugin_readme("demo", "fr-FR")

    assert payload["content"] == "default"
    assert payload["resolved_locale"] is None


def test_missing_declared_file_falls_back_to_default(tmp_path: Path):
    service, plugin_dir = _make_service(
        tmp_path,
        {"default": "README.md", "zh-CN": "missing.md"},
    )
    (plugin_dir / "README.md").write_text("default", encoding="utf-8")

    payload, _message = service.get_plugin_readme("demo", "zh-CN")

    assert payload["content"] == "default"


def test_parent_directory_escape_is_rejected(tmp_path: Path):
    service, plugin_dir = _make_service(
        tmp_path,
        {"default": "../secret.md"},
    )
    (tmp_path / "secret.md").write_text("secret", encoding="utf-8")

    with pytest.raises(PluginServiceError):
        service.get_plugin_readme("demo")


def test_absolute_path_is_rejected(tmp_path: Path):
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    service, _plugin_dir = _make_service(tmp_path, {"default": str(outside)})

    with pytest.raises(PluginServiceError):
        service.get_plugin_readme("demo")


def test_non_markdown_file_is_rejected(tmp_path: Path):
    service, plugin_dir = _make_service(tmp_path, {"default": "config.json"})
    (plugin_dir / "config.json").write_text("{}", encoding="utf-8")

    with pytest.raises(PluginServiceError):
        service.get_plugin_readme("demo")


def test_symlink_escape_is_rejected(tmp_path: Path):
    service, plugin_dir = _make_service(tmp_path, {"default": "README.md"})
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    link = plugin_dir / "README.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(PluginServiceError):
        service.get_plugin_readme("demo")


def test_normalize_locale():
    assert PluginService._normalize_locale("zh_CN") == "zh-cn"
    assert PluginService._normalize_locale(" zh-CN ") == "zh-cn"
    assert PluginService._normalize_locale(None) == ""
