from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from astrbot_sdk.cli import cli


def test_init_normalizes_plugin_name_and_adds_prefix() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "demo-plugin"])

        assert result.exit_code == 0
        plugin_dir = Path("astrbot_plugin_demo_plugin")
        assert plugin_dir.exists()
        manifest = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8")
        assert "name: astrbot_plugin_demo_plugin" in manifest
        assert "display_name: demo-plugin" in manifest
        assert "version: 1.0.0" in manifest


def test_init_interactive_prompts_and_sanitizes_name() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["init"],
            input="\nMy Plugin,Name;Beta\nAlice\nExample plugin\n\n",
        )

        assert result.exit_code == 0
        assert "该字段不能为空，请重新输入。" in result.output
        plugin_dir = Path("astrbot_plugin_my_plugin_name_beta")
        assert plugin_dir.exists()
        manifest = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8")
        assert "name: astrbot_plugin_my_plugin_name_beta" in manifest
        assert "display_name: My Plugin,Name;Beta" in manifest
        assert "author: Alice" in manifest
        assert "desc: Example plugin" in manifest
        assert "version: 1.0.0" in manifest
