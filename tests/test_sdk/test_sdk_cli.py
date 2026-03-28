from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from astrbot_sdk.cli import cli


def _write_manifest(plugin_dir: Path, manifest_text: str) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(manifest_text, encoding="utf-8")


def test_init_prompts_author_and_generates_repo(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    result = runner.invoke(
        cli,
        ["init", "demo-plugin"],
        input="demo-author\nDemo plugin\n0.2.0\n",
    )

    assert result.exit_code == 0
    manifest = (tmp_path / "astrbot_plugin_demo_plugin" / "plugin.yaml").read_text(
        encoding="utf-8"
    )
    assert "author: demo-author" in manifest
    assert "repo: astrbot_plugin_demo_plugin" in manifest
    assert "version: 0.2.0" in manifest


def test_validate_requires_author(tmp_path: Path) -> None:
    runner = CliRunner()
    plugin_dir = tmp_path / "missing_author"
    _write_manifest(
        plugin_dir,
        "\n".join(
            [
                "name: missing_author",
                "repo: missing_author",
                "version: 1.0.0",
                "runtime:",
                '  python: "3.11"',
                "components:",
                "  - class: main:DemoPlugin",
            ]
        ),
    )

    result = runner.invoke(cli, ["validate", "--plugin-dir", str(plugin_dir)])

    assert result.exit_code == 3
    assert "缺少 author" in result.output


def test_validate_requires_repo(tmp_path: Path) -> None:
    runner = CliRunner()
    plugin_dir = tmp_path / "missing_repo"
    _write_manifest(
        plugin_dir,
        "\n".join(
            [
                "name: missing_repo",
                "author: demo",
                "version: 1.0.0",
                "runtime:",
                '  python: "3.11"',
                "components:",
                "  - class: main:DemoPlugin",
            ]
        ),
    )

    result = runner.invoke(cli, ["validate", "--plugin-dir", str(plugin_dir)])

    assert result.exit_code == 3
    assert "缺少 repo" in result.output
