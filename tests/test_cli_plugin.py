from pathlib import Path

import pytest
from click.testing import CliRunner

from astrbot.cli.commands.cmd_plug import plug


def _write_plugin(path: Path, name: str = "astrbot_plugin_local_demo") -> None:
    path.mkdir(parents=True)
    (path / "metadata.yaml").write_text(
        "\n".join(
            [
                f"name: {name}",
                "desc: Local plugin",
                "version: 1.0.0",
                "author: AstrBot",
                "repo: https://example.com/local-plugin",
            ],
        ),
        encoding="utf-8",
    )
    (path / "main.py").write_text("PLUGIN_LOADED = True\n", encoding="utf-8")


def _write_astrbot_root(path: Path) -> None:
    (path / ".astrbot").touch()
    (path / "data" / "plugins").mkdir(parents=True)


def test_plugin_install_editable_copies_local_plugin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    source = tmp_path / "source-plugin"
    root.mkdir()
    _write_astrbot_root(root)
    _write_plugin(source)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(
        plug,
        ["install", "-e", str(source)],
        catch_exceptions=False,
    )

    target = root / "data" / "plugins" / "astrbot_plugin_local_demo"
    assert result.exit_code == 0
    assert (target / "metadata.yaml").exists()
    assert (target / "main.py").read_text(encoding="utf-8") == "PLUGIN_LOADED = True\n"


def test_plugin_install_accepts_local_path_without_editable_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    source = tmp_path / "source-plugin"
    root.mkdir()
    _write_astrbot_root(root)
    _write_plugin(source)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(plug, ["install", str(source)])

    assert result.exit_code == 0
    assert (
        root / "data" / "plugins" / "astrbot_plugin_local_demo" / "metadata.yaml"
    ).exists()


def test_plugin_install_editable_rejects_existing_plugin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    source = tmp_path / "source-plugin"
    root.mkdir()
    _write_astrbot_root(root)
    _write_plugin(source)
    _write_plugin(root / "data" / "plugins" / "astrbot_plugin_local_demo")
    monkeypatch.chdir(root)

    result = CliRunner().invoke(plug, ["install", "-e", str(source)])

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_plugin_install_requires_name_or_editable_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_astrbot_root(root)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(plug, ["install"])

    assert result.exit_code != 0
    assert "Missing plugin name or local plugin path" in result.output
