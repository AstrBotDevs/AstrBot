from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

from astrbot.core.computer import computer_client
from astrbot.core.skills.skill_manager import SkillManager


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
        self.uploaded_entries: list[str] = []

    async def upload_file(self, path: str, file_name: str) -> dict:
        self.uploads.append((path, file_name))
        with zipfile.ZipFile(path) as zf:
            self.uploaded_entries = sorted(
                name.replace("\\", "/") for name in zf.namelist()
            )
        return {"success": True}


def _write_sdk_registered_skill(
    root: Path,
    skill_name: str,
) -> None:
    skill_dir = root / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text("# demo", encoding="utf-8")


def test_sync_skills_keeps_builtin_skills_when_local_is_empty(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    skills_root = tmp_path / "skills"
    temp_root = tmp_path / "temp"
    data_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)

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
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.SkillManager.set_sandbox_skills_cache",
        _fake_set_cache,
    )

    booter = _FakeBooter(
        '{"skills":[{"name":"python-sandbox","description":"ship","path":"skills/python-sandbox/SKILL.md"}]}'
    )
    asyncio.run(computer_client._sync_skills_to_sandbox(booter))

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
    data_dir = tmp_path / "data"
    skills_root = tmp_path / "skills"
    temp_root = tmp_path / "temp"
    skill_dir = skills_root / "custom-agent-skill"
    data_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text("# demo", encoding="utf-8")
    temp_root.mkdir(parents=True, exist_ok=True)

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
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.SkillManager.set_sandbox_skills_cache",
        _fake_set_cache,
    )

    booter = _FakeBooter(
        '{"skills":[{"name":"custom-agent-skill","description":"","path":"skills/custom-agent-skill/SKILL.md"}]}'
    )
    asyncio.run(computer_client._sync_skills_to_sandbox(booter))

    assert len(booter.uploads) == 1
    assert booter.uploads[0][1].replace("\\", "/") == "skills/skills.zip"
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


def test_sync_skills_includes_sdk_registered_skills(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    skills_root = tmp_path / "skills"
    temp_root = tmp_path / "temp"
    registered_root = tmp_path / "sdk_registered"
    data_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    registered_root.mkdir(parents=True, exist_ok=True)
    _write_sdk_registered_skill(registered_root, "browser-helper")

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
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.SkillManager.set_sandbox_skills_cache",
        _fake_set_cache,
    )
    SkillManager(skills_root=str(skills_root)).replace_sdk_plugin_skills(
        "sdk-demo",
        [
            {
                "name": "sdk-demo.browser-helper",
                "description": "",
                "path": str(registered_root / "browser-helper" / "SKILL.md"),
                "skill_dir": str(registered_root / "browser-helper"),
            }
        ],
    )

    booter = _FakeBooter(
        '{"skills":[{"name":"sdk-demo.browser-helper","description":"","path":"skills/sdk-demo.browser-helper/SKILL.md"}]}'
    )
    asyncio.run(computer_client._sync_skills_to_sandbox(booter))

    assert len(booter.uploads) == 1
    assert "sdk-demo.browser-helper/" in booter.uploaded_entries
    assert "sdk-demo.browser-helper/SKILL.md" in booter.uploaded_entries
    assert captured["skills"] == [
        {
            "name": "sdk-demo.browser-helper",
            "description": "",
            "path": "skills/sdk-demo.browser-helper/SKILL.md",
        }
    ]

