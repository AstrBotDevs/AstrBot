from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path
from typing import cast

import pytest

from astrbot.core.computer import computer_client
from astrbot.core.computer.booters.base import ComputerBooter


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


@pytest.fixture(autouse=True)
def _isolate_builtin_plugin_skills(monkeypatch, tmp_path: Path) -> None:
    builtin_plugins_root = tmp_path / "builtin_plugins"
    builtin_plugins_root.mkdir()
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_builtin_plugin_path",
        lambda: str(builtin_plugins_root),
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
    import astrbot.core.star.star as star_module
    from astrbot.core.star.star import StarMetadata

    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    temp_root = tmp_path / "temp"
    skills_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    plugin_skill_dir = plugins_root / "astrbot_plugin_demo" / "skills" / "demo-skill"
    plugin_skill_dir.mkdir(parents=True)
    plugin_skill_dir.joinpath("SKILL.md").write_text("# demo", encoding="utf-8")

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
    monkeypatch.setattr(
        star_module,
        "star_registry",
        [
            StarMetadata(
                name="demo",
                root_dir_name="astrbot_plugin_demo",
                activated=True,
            )
        ],
    )

    booter = _FakeBooter(
        '{"skills":[{"name":"demo-skill","description":"","path":"skills/demo-skill/SKILL.md"}]}'
    )
    asyncio.run(computer_client._sync_skills_to_sandbox(cast(ComputerBooter, booter)))

    assert len(booter.uploads) == 1
    assert booter.uploads[0][1] == "skills/skills.zip"
    assert captured["skills"] == [
        {
            "name": "demo-skill",
            "description": "",
            "path": "skills/demo-skill/SKILL.md",
        }
    ]


def test_sync_skills_skips_inactive_plugin_provided_skills(
    monkeypatch,
    tmp_path: Path,
):
    import astrbot.core.star.star as star_module
    from astrbot.core.star.star import StarMetadata

    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    temp_root = tmp_path / "temp"
    skills_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    plugin_skill_dir = plugins_root / "astrbot_plugin_demo" / "skills" / "demo-skill"
    plugin_skill_dir.mkdir(parents=True)
    plugin_skill_dir.joinpath("SKILL.md").write_text("# demo", encoding="utf-8")

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
        star_module,
        "star_registry",
        [
            StarMetadata(
                name="demo",
                root_dir_name="astrbot_plugin_demo",
                activated=False,
            )
        ],
    )

    booter = _FakeBooter('{"skills":[]}')
    asyncio.run(computer_client._sync_skills_to_sandbox(cast(ComputerBooter, booter)))

    assert booter.uploads == []
    assert any(cmd == "rm -f skills/skills.zip" for cmd in booter.shell.commands)


def test_build_scan_command_frontmatter_newline_is_escaped_literal():
    command = computer_client._build_scan_command()
    script = _extract_embedded_python(command)

    assert 'frontmatter = "\\n".join(lines[1:end_idx])' in script


def test_build_scan_command_embedded_python_is_syntax_valid():
    command = computer_client._build_scan_command()
    script = _extract_embedded_python(command)

    compile(script, "<scan_script>", "exec")


def _setup_local_skills(monkeypatch, tmp_path: Path, names: list[str]) -> Path:
    """Create local skills and point AstrBot paths at the test directories."""
    skills_root = tmp_path / "skills"
    data_root = tmp_path / "data"
    temp_root = tmp_path / "temp"
    for path in (skills_root, data_root, temp_root, tmp_path / "plugins"):
        path.mkdir(parents=True, exist_ok=True)
    for name in names:
        skill_dir = skills_root / name
        skill_dir.mkdir()
        skill_dir.joinpath("SKILL.md").write_text(f"# {name}", encoding="utf-8")
        skill_dir.joinpath("notes.txt").write_text("private", encoding="utf-8")

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
        lambda: str(data_root),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_plugin_path",
        lambda: str(tmp_path / "plugins"),
    )
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.SkillManager.set_sandbox_skills_cache",
        lambda self, skills: None,
    )
    return temp_root


class _BundleRecordingBooter(_FakeBooter):
    """Fake booter that records the skill names inside each uploaded bundle."""

    def __init__(self):
        super().__init__('{"skills":[]}')
        self.bundles: list[set[str]] = []

    async def upload_file(self, path: str, file_name: str) -> dict:
        with zipfile.ZipFile(path) as zf:
            self.bundles.append({name.split("/")[0] for name in zf.namelist()})
        return await super().upload_file(path, file_name)


def test_sync_skills_only_uploads_allowed_and_active_skills(
    monkeypatch, tmp_path: Path
):
    from astrbot.core.skills.skill_manager import SkillManager

    temp_root = _setup_local_skills(
        monkeypatch,
        tmp_path,
        ["allowed-skill", "unselected-skill", "disabled-skill"],
    )
    SkillManager().set_skill_active("disabled-skill", False)

    booter = _BundleRecordingBooter()
    asyncio.run(
        computer_client._sync_skills_to_sandbox(
            cast(ComputerBooter, booter),
            frozenset({"allowed-skill", "disabled-skill"}),
        )
    )

    assert booter.bundles == [{"allowed-skill"}]
    # Temporary bundles are per sync and cleaned up afterwards.
    assert list(temp_root.iterdir()) == []


def test_sync_skills_never_uploads_globally_disabled_skills(
    monkeypatch, tmp_path: Path
):
    from astrbot.core.skills.skill_manager import SkillManager

    _setup_local_skills(monkeypatch, tmp_path, ["active-skill", "disabled-skill"])
    SkillManager().set_skill_active("disabled-skill", False)

    booter = _BundleRecordingBooter()
    asyncio.run(computer_client._sync_skills_to_sandbox(cast(ComputerBooter, booter)))

    assert booter.bundles == [{"active-skill"}]


def test_sync_skills_with_empty_allowlist_uploads_nothing(monkeypatch, tmp_path: Path):
    _setup_local_skills(monkeypatch, tmp_path, ["some-skill"])

    booter = _BundleRecordingBooter()
    asyncio.run(
        computer_client._sync_skills_to_sandbox(
            cast(ComputerBooter, booter), frozenset()
        )
    )

    assert booter.uploads == []
    # The apply phase still runs, so previously managed copies are removed.
    assert any("managed_skills" in cmd for cmd in booter.shell.commands)


class _SessionContext:
    def __init__(self):
        self.config = {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {"booter": "boxlite"},
            }
        }

    def get_config(self, umo: str | None = None):
        return self.config


class _AvailableBooter:
    async def available(self) -> bool:
        return True


def test_get_booter_resyncs_when_session_skills_change(monkeypatch):
    session_id = "test:FriendMessage:skill-scope"
    booter = _AvailableBooter()
    synced: list[frozenset[str] | None] = []

    async def _fake_sync(booter, skill_names=None):
        synced.append(skill_names)

    monkeypatch.setattr(computer_client, "_sync_skills_to_sandbox", _fake_sync)
    monkeypatch.setitem(computer_client.session_booter, session_id, booter)
    monkeypatch.setitem(
        computer_client._session_synced_skill_names,
        session_id,
        frozenset({"old-skill"}),
    )
    monkeypatch.setitem(
        computer_client.session_skill_names, session_id, frozenset({"new-skill"})
    )
    ctx = _SessionContext()

    assert asyncio.run(computer_client.get_booter(ctx, session_id)) is booter
    assert synced == [frozenset({"new-skill"})]

    # Unchanged allowlist: no extra sync on later tool calls.
    asyncio.run(computer_client.get_booter(ctx, session_id))
    assert synced == [frozenset({"new-skill"})]

    # Revoking every skill resyncs with an empty allowlist.
    computer_client.session_skill_names[session_id] = frozenset()
    asyncio.run(computer_client.get_booter(ctx, session_id))
    assert synced == [frozenset({"new-skill"}), frozenset()]


def test_sync_skills_to_active_sandboxes_uses_session_allowlists(monkeypatch):
    synced: dict[int, frozenset[str] | None] = {}

    async def _fake_sync(booter, skill_names=None):
        synced[id(booter)] = skill_names

    known, unknown = _AvailableBooter(), _AvailableBooter()
    monkeypatch.setattr(computer_client, "_sync_skills_to_sandbox", _fake_sync)
    monkeypatch.setattr(
        computer_client, "session_booter", {"known": known, "unknown": unknown}
    )
    monkeypatch.setattr(
        computer_client, "session_skill_names", {"known": frozenset({"a"})}
    )
    monkeypatch.setattr(computer_client, "_session_synced_skill_names", {})

    asyncio.run(computer_client.sync_skills_to_active_sandboxes())

    assert synced == {id(known): frozenset({"a"}), id(unknown): frozenset()}
