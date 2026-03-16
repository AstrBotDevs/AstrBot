from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.core.computer import computer_client


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


def test_sync_skills_keeps_builtin_skills_when_local_is_empty(monkeypatch, tmp_path: Path):
    skills_root = tmp_path / "skills"
    temp_root = tmp_path / "temp"
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
    skills_root = tmp_path / "skills"
    temp_root = tmp_path / "temp"
    skill_dir = skills_root / "custom-agent-skill"
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
        "astrbot.core.computer.computer_client.SkillManager.set_sandbox_skills_cache",
        _fake_set_cache,
    )

    booter = _FakeBooter(
        '{"skills":[{"name":"custom-agent-skill","description":"","path":"skills/custom-agent-skill/SKILL.md"}]}'
    )
    asyncio.run(computer_client._sync_skills_to_sandbox(booter))

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

