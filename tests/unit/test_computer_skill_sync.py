import asyncio
from pathlib import Path
from typing import cast

from astrbot.core.computer import computer_client
from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.star.star import StarMetadata


def _extract_embedded_python(command: str) -> str:
    start_marker = "$PYBIN - <<'PY'\n"
    end_marker = "\nPY"
    start = command.find(start_marker)
    assert start != -1
    start += len(start_marker)
    end = command.rfind(end_marker)
    assert end != -1
    return command[start:end]


class _FakeShell:
    def __init__(self, sync_payload_json: str):
        self.sync_payload_json = sync_payload_json
        self.commands: list[str] = []

    async def exec(self, command: str, **kwargs):
        _ = kwargs
        self.commands.append(command)
        if "PYBIN" in command and "managed_skills" in command:
            return {
                "success": True,
                "stdout": self.sync_payload_json,
                "stderr": "",
                "exit_code": 0,
            }
        return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}


class _FakeBooter:
    def __init__(self, sync_payload_json: str):
        self.shell = _FakeShell(sync_payload_json)
        self.uploads: list[tuple[str, str]] = []

    async def upload_file(self, path: str, file_name: str) -> dict:
        self.uploads.append((path, file_name))
        return {"success": True}


def _isolate_skill_manager_data(monkeypatch, tmp_path: Path) -> None:
    """Keep SkillManager's config/cache writes inside this test's temp root."""
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_root),
    )


def test_sync_skills_keeps_builtin_skills_when_local_is_empty(
    monkeypatch, tmp_path: Path
):
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    temp_root = tmp_path / "temp"
    skills_root.mkdir(parents=True, exist_ok=True)
    plugins_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    _isolate_skill_manager_data(monkeypatch, tmp_path)

    captured = {"skills": None}

    def _fake_set_cache(self, skills):
        captured["skills"] = skills

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_skills_path",
        lambda: str(skills_root),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_plugin_path",
        lambda: str(plugins_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.SkillManager.set_sandbox_skills_cache",
        _fake_set_cache,
    )

    booter = _FakeBooter(
        '{"skills":[{"name":"python-sandbox","description":"ship","path":"skills/python-sandbox/SKILL.md"}]}'
    )
    asyncio.run(computer_client._sync_skills_to_sandbox(cast(ComputerBooter, booter)))

    assert booter.uploads == []
    assert any(cmd == "rm -f skills/skills.zip" for cmd in booter.shell.commands)
    assert captured["skills"] == [
        {
            "name": "python-sandbox",
            "description": "ship",
            "path": "skills/python-sandbox/SKILL.md",
        }
    ]


def test_sync_skills_uses_managed_strategy_instead_of_wiping_all(
    monkeypatch,
    tmp_path: Path,
):
    skills_root = tmp_path / "skills"
    temp_root = tmp_path / "temp"
    skill_dir = skills_root / "custom-agent-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text("# demo", encoding="utf-8")
    temp_root.mkdir(parents=True, exist_ok=True)
    _isolate_skill_manager_data(monkeypatch, tmp_path)

    captured = {"skills": None}

    def _fake_set_cache(self, skills):
        captured["skills"] = skills

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_skills_path",
        lambda: str(skills_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.SkillManager.set_sandbox_skills_cache",
        _fake_set_cache,
    )

    booter = _FakeBooter(
        '{"skills":[{"name":"custom-agent-skill","description":"","path":"skills/custom-agent-skill/SKILL.md"}]}'
    )
    asyncio.run(computer_client._sync_skills_to_sandbox(cast(ComputerBooter, booter)))

    assert len(booter.uploads) == 1
    assert booter.uploads[0][1] == "skills/skills.zip"
    assert not any(
        "find skills -mindepth 1 -delete" in cmd for cmd in booter.shell.commands
    )
    assert captured["skills"] == [
        {
            "name": "custom-agent-skill",
            "description": "",
            "path": "skills/custom-agent-skill/SKILL.md",
        }
    ]


def test_sync_skills_includes_plugin_provided_skills(
    monkeypatch,
    tmp_path: Path,
):
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    temp_root = tmp_path / "temp"
    skills_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    plugin_skill_dir = plugins_root / "astrbot_plugin_demo" / "skills" / "demo-skill"
    plugin_skill_dir.mkdir(parents=True)
    plugin_skill_dir.joinpath("SKILL.md").write_text("# demo", encoding="utf-8")
    _isolate_skill_manager_data(monkeypatch, tmp_path)

    captured = {"skills": None}

    def _fake_set_cache(self, skills):
        captured["skills"] = skills

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_skills_path",
        lambda: str(skills_root),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_plugin_path",
        lambda: str(plugins_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.SkillManager.set_sandbox_skills_cache",
        _fake_set_cache,
    )

    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(
            name="Demo",
            module_path="astrbot.plugins.demo.main",
            root_dir_name="astrbot_plugin_demo",
            activated=True,
        )
    )

    booter = _FakeBooter(
        '{"skills":[{"name":"demo-skill","description":"","path":"skills/demo-skill/SKILL.md"}]}'
    )
    asyncio.run(
        computer_client._sync_skills_to_sandbox(
            cast(ComputerBooter, booter),
            plugins=catalogs.plugins,
        )
    )

    assert len(booter.uploads) == 1
    assert booter.uploads[0][1] == "skills/skills.zip"
    assert captured["skills"] == [
        {
            "name": "demo-skill",
            "description": "",
            "path": "skills/demo-skill/SKILL.md",
        }
    ]


def test_sync_skills_fails_closed_for_disabled_or_unknown_plugin_skills(
    monkeypatch,
    tmp_path: Path,
):
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    temp_root = tmp_path / "temp"
    skills_root.mkdir()
    temp_root.mkdir()
    for plugin_name in ("disabled_plugin", "unknown_plugin"):
        skill_dir = plugins_root / plugin_name / "skills" / f"{plugin_name}-skill"
        skill_dir.mkdir(parents=True)
        skill_dir.joinpath("SKILL.md").write_text("# demo", encoding="utf-8")
    _isolate_skill_manager_data(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_skills_path",
        lambda: str(skills_root),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_plugin_path",
        lambda: str(plugins_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_temp_path",
        lambda: str(temp_root),
    )

    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(
            name="Disabled",
            module_path="astrbot.plugins.disabled.main",
            root_dir_name="disabled_plugin",
            activated=False,
        )
    )
    booter = _FakeBooter('{"skills":[]}')

    asyncio.run(
        computer_client._sync_skills_to_sandbox(
            cast(ComputerBooter, booter),
            plugins=catalogs.plugins,
        )
    )

    assert booter.uploads == []


def test_sync_skills_includes_builtin_only_skills_without_local_root(
    monkeypatch,
    tmp_path: Path,
):
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    temp_root = tmp_path / "temp"
    builtin_root = tmp_path / "builtin_stars"
    plugins_root.mkdir(parents=True)
    temp_root.mkdir(parents=True)
    builtin_skill = builtin_root / "builtin_demo" / "skills" / "builtin-skill"
    builtin_skill.mkdir(parents=True)
    builtin_skill.joinpath("SKILL.md").write_text("# builtin", encoding="utf-8")
    _isolate_skill_manager_data(monkeypatch, tmp_path)

    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(
            name="Builtin Demo",
            module_path="astrbot.builtin_stars.builtin_demo.main",
            root_dir_name="builtin_demo",
            reserved=True,
        )
    )
    catalogs.builtin_skills.bind(catalogs.plugins, builtin_root)
    manager = SkillManager(
        skills_root=str(skills_root),
        plugins_root=str(plugins_root),
        builtin_skill_catalog=catalogs.builtin_skills,
    )
    captured = {"skills": None}

    def _fake_set_cache(self, skills):
        captured["skills"] = skills

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_skills_path",
        lambda: str(skills_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.SkillManager.set_sandbox_skills_cache",
        _fake_set_cache,
    )

    booter = _FakeBooter(
        '{"skills":[{"name":"builtin-skill","description":"","path":"skills/builtin-skill/SKILL.md"}]}'
    )
    asyncio.run(computer_client._sync_skills_to_sandbox(booter, skill_manager=manager))

    assert len(booter.uploads) == 1
    assert booter.uploads[0][1] == "skills/skills.zip"


def test_build_scan_command_frontmatter_newline_is_escaped_literal():
    command = computer_client._build_scan_command()
    script = _extract_embedded_python(command)

    assert 'frontmatter = "\\n".join(lines[1:end_idx])' in script


def test_build_scan_command_embedded_python_is_syntax_valid():
    command = computer_client._build_scan_command()
    script = _extract_embedded_python(command)

    compile(script, "<scan_script>", "exec")
