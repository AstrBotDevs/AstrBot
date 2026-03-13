"""Tests for the private legacy loader helpers."""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import yaml

from astrbot_sdk._legacy_loader import (
    build_legacy_manifest,
    load_legacy_main_component_classes,
    load_plugin_manifest_payload,
    looks_like_legacy_plugin,
    resolve_plugin_component_classes,
)


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_looks_like_legacy_plugin_requires_main_without_manifest():
    with tempfile.TemporaryDirectory() as temp_dir:
        plugin_dir = Path(temp_dir) / "legacy_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "main.py").write_text("print('x')", encoding="utf-8")

        assert looks_like_legacy_plugin(plugin_dir) is True

        (plugin_dir / "plugin.yaml").write_text("name: modern", encoding="utf-8")
        assert looks_like_legacy_plugin(plugin_dir) is False


def test_build_legacy_manifest_uses_metadata_and_marks_legacy_main():
    with tempfile.TemporaryDirectory() as temp_dir:
        plugin_dir = Path(temp_dir) / "legacy_plugin"
        plugin_dir.mkdir()
        metadata_path = plugin_dir / "metadata.yaml"
        metadata_path.write_text(
            yaml.dump({"name": "legacy_demo", "author": "tester", "version": "1.0.0"}),
            encoding="utf-8",
        )

        manifest_path, manifest_data = build_legacy_manifest(
            plugin_dir,
            read_yaml=_read_yaml,
            default_python_version="3.12",
            manifest_flag_key="__legacy_main__",
        )

        assert manifest_path == metadata_path
        assert manifest_data["name"] == "legacy_demo"
        assert manifest_data["runtime"]["python"] == "3.12"
        assert manifest_data["__legacy_main__"] is True


def test_load_legacy_main_component_classes_supports_relative_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        plugin_dir = Path(temp_dir) / "legacy_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "src").mkdir()
        (plugin_dir / "src" / "helper.py").write_text(
            'VALUE = "legacy-ok"\n',
            encoding="utf-8",
        )
        (plugin_dir / "main.py").write_text(
            textwrap.dedent(
                """\
                from astrbot_sdk.api.star import Star
                from .src.helper import VALUE


                class LegacyPlugin(Star):
                    helper_value = VALUE
                """
            ),
            encoding="utf-8",
        )

        classes = load_legacy_main_component_classes(
            plugin_name="legacy-plugin",
            plugin_dir=plugin_dir,
        )

        assert [cls.__name__ for cls in classes] == ["LegacyPlugin"]
        assert classes[0].helper_value == "legacy-ok"


def test_load_plugin_manifest_payload_prefers_plugin_yaml_when_present():
    with tempfile.TemporaryDirectory() as temp_dir:
        plugin_dir = Path(temp_dir) / "plugin"
        plugin_dir.mkdir()
        manifest_path = plugin_dir / "plugin.yaml"
        manifest_path.write_text(
            yaml.dump({"name": "modern_plugin", "runtime": {"python": "3.12"}}),
            encoding="utf-8",
        )

        resolved_path, manifest_data = load_plugin_manifest_payload(
            plugin_dir,
            read_yaml=_read_yaml,
            default_python_version="3.13",
            manifest_flag_key="__legacy_main__",
        )

        assert resolved_path == manifest_path
        assert manifest_data["name"] == "modern_plugin"
        assert "__legacy_main__" not in manifest_data


def test_resolve_plugin_component_classes_falls_back_to_legacy_main():
    with tempfile.TemporaryDirectory() as temp_dir:
        plugin_dir = Path(temp_dir) / "legacy_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "main.py").write_text(
            textwrap.dedent(
                """\
                from astrbot_sdk.api.star import Star


                class LegacyPlugin(Star):
                    pass
                """
            ),
            encoding="utf-8",
        )

        classes = resolve_plugin_component_classes(
            plugin_name="legacy_plugin",
            plugin_dir=plugin_dir,
            manifest_data={"components": [], "__legacy_main__": True},
            manifest_flag_key="__legacy_main__",
            import_string=lambda path, plugin_dir=None: None,
        )

        assert [cls.__name__ for cls in classes] == ["LegacyPlugin"]
