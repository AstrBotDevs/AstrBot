"""Plugin metadata validation fails before import or dependency installation."""

from pathlib import Path

import pytest

from astrbot.core.star import star_manager
from astrbot.core.star.star_manager import (
    PluginDependencyInstallError,
    PluginManager,
    PluginVersionIncompatibleError,
    PluginVersionUnsupportedError,
)


@pytest.mark.parametrize("filename", ["metadata.yaml", "metadata.yml"])
def test_plugin_directory_comes_from_valid_normalized_metadata(tmp_path, filename):
    (tmp_path / filename).write_text("name: '  weather_plugin  '\n", encoding="utf-8")
    assert (
        PluginManager._get_plugin_dir_name_from_metadata(str(tmp_path))
        == "weather_plugin"
    )


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "{}",
        "name: 123",
        "name: ''",
        "name: ../escape",
        "name: a/b",
        "name: a-b",
        "name: class",
    ],
)
def test_invalid_metadata_is_rejected_without_creating_files(tmp_path, content):
    path = tmp_path / "metadata.yaml"
    path.write_text(content, encoding="utf-8")
    before = set(tmp_path.iterdir())
    with pytest.raises(Exception):
        PluginManager._get_plugin_dir_name_from_metadata(str(tmp_path))
    assert set(tmp_path.iterdir()) == before
    assert path.read_text(encoding="utf-8") == content


def test_missing_metadata_reports_both_supported_names(tmp_path):
    with pytest.raises(Exception, match=r"metadata.yaml.*metadata.yml"):
        PluginManager._get_plugin_dir_name_from_metadata(str(tmp_path))


@pytest.mark.parametrize(
    ("specifier", "allowed"),
    [
        (None, True),
        (" ", True),
        (">=4.0,<5", True),
        (">=5", False),
        ("not-a-version", False),
    ],
)
def test_version_compatibility_uses_current_version(monkeypatch, specifier, allowed):
    monkeypatch.setattr(star_manager, "VERSION", "4.16.0")
    compatible, error = PluginManager._validate_astrbot_version_specifier(specifier)
    assert compatible is allowed
    assert (error is None) is allowed


def test_dependency_error_preserves_original_cause_and_path(tmp_path):
    error = ImportError("missing dependency")
    requirements = str(tmp_path / "requirements.txt")
    wrapped = PluginDependencyInstallError(
        plugin_label="weather", requirements_path=requirements, error=error
    )
    assert wrapped.error is error
    assert wrapped.plugin_label == "weather"
    assert Path(wrapped.requirements_path) == tmp_path / "requirements.txt"
    assert (
        str(wrapped)
        == "Failed to install dependencies for plugin weather: missing dependency"
    )
    assert isinstance(
        PluginVersionUnsupportedError("incompatible"), PluginVersionIncompatibleError
    )
