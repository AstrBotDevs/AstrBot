from __future__ import annotations

import zipfile
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
        assert not (plugin_dir / ".claude").exists()
        assert not (plugin_dir / ".agents").exists()
        assert not (plugin_dir / ".opencode").exists()


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


def test_init_generates_claude_agent_directory() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "demo-plugin", "--agents", "claude"])

        assert result.exit_code == 0
        plugin_dir = Path("astrbot_plugin_demo_plugin")
        claude_file = (
            plugin_dir / ".claude" / "skills" / "astrbot-plugin-dev" / "SKILL.md"
        )
        assert claude_file.exists()
        content = claude_file.read_text(encoding="utf-8")
        assert "astrbot_plugin_demo_plugin" in content
        assert "name: astrbot-plugin-dev" in content
        assert "Plugin root: `../../..`" in content
        assert (
            plugin_dir
            / ".claude"
            / "skills"
            / "astrbot-plugin-dev"
            / "references"
            / "api-quick-ref.md"
        ).exists()
        assert not (plugin_dir / ".agents").exists()
        assert not (plugin_dir / ".opencode").exists()


def test_init_generates_multiple_agent_directories() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["init", "demo-plugin", "--agents", "claude,codex"],
        )

        assert result.exit_code == 0
        plugin_dir = Path("astrbot_plugin_demo_plugin")
        assert (
            plugin_dir / ".claude" / "skills" / "astrbot-plugin-dev" / "SKILL.md"
        ).exists()
        assert (
            plugin_dir / ".agents" / "skills" / "astrbot-plugin-dev" / "SKILL.md"
        ).exists()
        codex_meta = (
            plugin_dir
            / ".agents"
            / "skills"
            / "astrbot-plugin-dev"
            / "agents"
            / "openai.yaml"
        ).read_text(encoding="utf-8")
        assert "AstrBot Plugin Dev (Codex)" in codex_meta
        assert not (plugin_dir / ".opencode").exists()


def test_init_deduplicates_agents_case_insensitively() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["init", "demo-plugin", "--agents", "Claude,codex,CLAUDE"],
        )

        assert result.exit_code == 0
        plugin_dir = Path("astrbot_plugin_demo_plugin")
        assert (
            plugin_dir / ".claude" / "skills" / "astrbot-plugin-dev" / "SKILL.md"
        ).exists()
        assert (
            plugin_dir / ".agents" / "skills" / "astrbot-plugin-dev" / "SKILL.md"
        ).exists()
        assert not (plugin_dir / ".opencode").exists()


def test_init_rejects_invalid_agents() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["init", "demo-plugin", "--agents", "claude,unknown"],
        )

        assert result.exit_code == 2
        assert "仅支持以下 agent" in result.output
        assert "unknown" in result.output
        assert not Path("astrbot_plugin_demo_plugin").exists()


def test_init_generates_opencode_agent_directory() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "demo-plugin", "--agents", "opencode"])

        assert result.exit_code == 0
        plugin_dir = Path("astrbot_plugin_demo_plugin")
        opencode_file = (
            plugin_dir / ".opencode" / "skills" / "astrbot-plugin-dev" / "SKILL.md"
        )
        assert opencode_file.exists()
        content = opencode_file.read_text(encoding="utf-8")
        assert "astrbot_plugin_demo_plugin" in content
        assert "Plugin root: `../../..`" in content


def test_build_excludes_generated_agent_skill_directories() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        init_result = runner.invoke(
            cli,
            ["init", "demo-plugin", "--agents", "claude,codex,opencode"],
        )
        assert init_result.exit_code == 0

        plugin_dir = Path("astrbot_plugin_demo_plugin")
        build_result = runner.invoke(
            cli,
            ["build", "--plugin-dir", str(plugin_dir)],
        )

        assert build_result.exit_code == 0
        archive_path = plugin_dir / "dist" / "astrbot_plugin_demo_plugin-1.0.0.zip"
        assert archive_path.exists()

        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()

        assert "plugin.yaml" in names
        assert "main.py" in names
        assert all(not name.startswith(".claude/") for name in names)
        assert all(not name.startswith(".agents/") for name in names)
        assert all(not name.startswith(".opencode/") for name in names)
