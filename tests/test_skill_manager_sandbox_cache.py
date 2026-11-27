from __future__ import annotations

from pathlib import Path

import pytest

from astrbot.core.skills.skill_manager import SkillManager


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\ndescription: {description}\n---\n# {name}\n",
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _isolate_plugin_skills(monkeypatch, tmp_path: Path) -> None:
    plugins_root = tmp_path / "plugins"
    builtin_plugins_root = tmp_path / "builtin_plugins"
    plugins_root.mkdir()
    builtin_plugins_root.mkdir()
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_plugin_path",
        lambda: str(plugins_root),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_builtin_plugin_path",
        lambda: str(builtin_plugins_root),
    )


def test_list_skills_merges_local_and_sandbox_cache(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    temp_dir = tmp_path / "temp"
    skills_root = tmp_path / "skills"
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    mgr = SkillManager(skills_root=str(skills_root))
    _write_skill(skills_root, "custom-local", "local description")

    mgr.set_sandbox_skills_cache(
        [
            {
                "name": "python-sandbox",
                "description": "ship built-in",
                "path": "/app/skills/python-sandbox/SKILL.md",
            },
            {
                "name": "custom-local",
                "description": "should be ignored by local override",
                "path": "skills/custom-local/SKILL.md",
            },
        ]
    )

    skills = mgr.list_skills(runtime="sandbox")
    by_name = {item.name: item for item in skills}

    assert sorted(by_name) == ["custom-local", "python-sandbox"]
    assert by_name["custom-local"].description == "local description"
    assert by_name["custom-local"].path == "skills/custom-local/SKILL.md"
    assert by_name["python-sandbox"].description == "ship built-in"
    assert by_name["python-sandbox"].path == "/app/skills/python-sandbox/SKILL.md"


def test_sandbox_cached_skill_respects_active_and_display_path(
    monkeypatch,
    tmp_path: Path,
):
    data_dir = tmp_path / "data"
    temp_dir = tmp_path / "temp"
    skills_root = tmp_path / "skills"
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    mgr = SkillManager(skills_root=str(skills_root))
    mgr.set_sandbox_skills_cache(
        [
            {
                "name": "browser-automation",
                "description": "gull built-in",
                "path": "/app/skills/browser-automation/SKILL.md",
            }
        ]
    )

    all_skills = mgr.list_skills(
        runtime="sandbox",
        active_only=False,
        show_sandbox_path=False,
    )
    assert len(all_skills) == 1
    assert all_skills[0].path == "/app/skills/browser-automation/SKILL.md"

    with pytest.raises(PermissionError):
        mgr.set_skill_active("browser-automation", False)

    active_skills = mgr.list_skills(runtime="sandbox", active_only=True)
    assert len(active_skills) == 1
    assert active_skills[0].name == "browser-automation"


def test_sandbox_and_local_path_resolution_with_show_sandbox_path_false(
    monkeypatch,
    tmp_path: Path,
):
    data_dir = tmp_path / "data"
    temp_dir = tmp_path / "temp"
    skills_root = tmp_path / "skills"
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    mgr = SkillManager(skills_root=str(skills_root))
    _write_skill(skills_root, "custom-local", "local description")
    mgr.set_sandbox_skills_cache(
        [
            {
                "name": "custom-local",
                "description": "cached description should be overridden",
                "path": "/app/skills/custom-local/SKILL.md",
            },
            {
                "name": "python-sandbox",
                "description": "ship built-in",
                "path": "/app/skills/python-sandbox/SKILL.md",
            },
        ]
    )

    skills = mgr.list_skills(runtime="sandbox", show_sandbox_path=False)
    by_name = {item.name: item for item in skills}

    assert sorted(by_name) == ["custom-local", "python-sandbox"]
    assert by_name["custom-local"].description == "local description"
    local_skill_path = Path(by_name["custom-local"].path)
    assert local_skill_path.is_relative_to(skills_root)
    assert local_skill_path == skills_root / "custom-local" / "SKILL.md"
    assert by_name["python-sandbox"].path == "/app/skills/python-sandbox/SKILL.md"


def test_delete_skill_path_boundaries(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    skills_root, victim_dir = data_dir / "skills", data_dir / "victim"
    skills_root.mkdir(parents=True)
    victim_dir.mkdir()
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path", lambda: str(data_dir)
    )

    mgr = SkillManager(skills_root=str(skills_root))
    for name in ("skill-1.0.0", "my skill", "demo"):
        _write_skill(skills_root, name, "local")

    for bad in ("", " ", ".", "..", "../victim", "..\\victim", str(victim_dir), 123):
        with pytest.raises(ValueError, match="Invalid skill"):
            mgr.delete_skill(bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Invalid skill"):
        mgr.set_skill_active(123, False)  # type: ignore[arg-type]

    mgr.delete_skill(" demo")
    assert victim_dir.exists() and (skills_root / "demo").exists()

    for name in ("skill-1.0.0", "my skill"):
        mgr.delete_skill(name)
        assert not (skills_root / name).exists()


@pytest.mark.asyncio
async def test_skill_zip_and_service_boundaries(monkeypatch, tmp_path: Path):
    import zipfile

    from astrbot.dashboard.services.skills_service import (
        SkillsService,
        SkillsServiceError,
    )

    data_dir, temp_dir = tmp_path / "data", tmp_path / "temp"
    skills_root = data_dir / "skills"
    skills_root.mkdir(parents=True)
    temp_dir.mkdir()
    for target, val in (
        ("astrbot.core.skills.skill_manager.get_astrbot_data_path", str(data_dir)),
        ("astrbot.core.skills.skill_manager.get_astrbot_temp_path", str(temp_dir)),
        ("astrbot.core.skills.skill_manager.get_astrbot_skills_path", str(skills_root)),
        (
            "astrbot.dashboard.services.skills_service.get_astrbot_temp_path",
            str(temp_dir),
        ),
    ):
        monkeypatch.setattr(target, lambda v=val: v)

    z_path = tmp_path / "padded.zip"
    with zipfile.ZipFile(z_path, "w") as zf:
        zf.writestr(" .. /SKILL.md", "---\ndescription: x\n---\n")
    mgr = SkillManager(skills_root=str(skills_root))
    with pytest.raises(ValueError):
        mgr.install_skill_from_zip(str(z_path), overwrite=True, skill_name_hint="..")
    with pytest.raises(ValueError):
        mgr.install_skill_from_zip(str(z_path), overwrite=True)

    legacy = skills_root / "legacy"
    legacy.mkdir()
    (legacy / "skill.md").write_text("---\ndescription: x\n---\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (legacy / "leak.txt").symlink_to(outside)

    service = SkillsService(core_lifecycle=None)
    with zipfile.ZipFile(service.prepare_skill_archive("legacy").path) as zf:
        assert zf.namelist() == ["legacy/skill.md"]
    with pytest.raises(SkillsServiceError, match="Invalid skill"):
        await service.delete_skill({"name": "../victim"})
    with pytest.raises(SkillsServiceError, match="Invalid skill"):
        service.prepare_skill_archive("..")
