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


def _write_sdk_registered_skill(
    root: Path,
    skill_name: str,
    description: str,
) -> Path:
    skill_dir = root / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\ndescription: {description}\n---\n# {skill_name}\n",
        encoding="utf-8",
    )
    return skill_dir


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
    assert by_name["python-sandbox"].path == "/workspace/skills/python-sandbox/SKILL.md"


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


def test_list_skills_includes_sdk_registered_sources(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    temp_dir = tmp_path / "temp"
    skills_root = tmp_path / "skills"
    registered_root = tmp_path / "sdk_registered"
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)
    registered_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    mgr = SkillManager(skills_root=str(skills_root))
    browser_skill_dir = _write_sdk_registered_skill(
        registered_root,
        "browser-helper",
        "sdk plugin skill",
    )
    triage_skill_dir = _write_sdk_registered_skill(
        registered_root,
        "triage",
        "sdk triage skill",
    )
    mgr.replace_sdk_plugin_skills(
        "sdk-demo",
        [
            {
                "name": "sdk-demo.browser-helper",
                "description": "sdk plugin skill",
                "path": str(browser_skill_dir / "SKILL.md"),
                "skill_dir": str(browser_skill_dir),
            },
            {
                "name": "sdk-demo.triage",
                "description": "sdk triage skill",
                "path": str(triage_skill_dir / "SKILL.md"),
                "skill_dir": str(triage_skill_dir),
            },
        ],
    )
    skills = mgr.list_skills(show_sandbox_path=False)
    by_name = {item.name: item for item in skills}

    assert sorted(by_name) == ["sdk-demo.browser-helper", "sdk-demo.triage"]
    assert by_name["sdk-demo.browser-helper"].description == "sdk plugin skill"
    assert Path(by_name["sdk-demo.browser-helper"].path) == (
        browser_skill_dir / "SKILL.md"
    )
    assert by_name["sdk-demo.triage"].description == "sdk triage skill"
    assert Path(by_name["sdk-demo.triage"].path) == (triage_skill_dir / "SKILL.md")


def test_sdk_registered_skill_cannot_be_deleted(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    temp_dir = tmp_path / "temp"
    skills_root = tmp_path / "skills"
    registered_root = tmp_path / "sdk_registered"
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)
    registered_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    skill_dir = _write_sdk_registered_skill(
        registered_root,
        "browser-helper",
        "sdk plugin skill",
    )

    mgr = SkillManager(skills_root=str(skills_root))
    mgr.replace_sdk_plugin_skills(
        "sdk-demo",
        [
            {
                "name": "sdk-demo.browser-helper",
                "description": "sdk plugin skill",
                "path": str(skill_dir / "SKILL.md"),
                "skill_dir": str(skill_dir),
            }
        ],
    )

    with pytest.raises(PermissionError):
        mgr.delete_skill("sdk-demo.browser-helper")

    assert skill_dir.exists()


def test_remove_sdk_registered_skill_prunes_stale_sandbox_cache(
    monkeypatch,
    tmp_path: Path,
):
    data_dir = tmp_path / "data"
    temp_dir = tmp_path / "temp"
    skills_root = tmp_path / "skills"
    registered_root = tmp_path / "sdk_registered"
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)
    registered_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    skill_dir = _write_sdk_registered_skill(
        registered_root,
        "browser-helper",
        "sdk plugin skill",
    )
    mgr = SkillManager(skills_root=str(skills_root))
    mgr.replace_sdk_plugin_skills(
        "sdk-demo",
        [
            {
                "name": "sdk-demo.browser-helper",
                "description": "sdk plugin skill",
                "path": str(skill_dir / "SKILL.md"),
                "skill_dir": str(skill_dir),
            }
        ],
    )
    mgr.set_sandbox_skills_cache(
        [
            {
                "name": "sdk-demo.browser-helper",
                "description": "sdk plugin skill",
                "path": "/workspace/skills/sdk-demo.browser-helper/SKILL.md",
            }
        ]
    )

    mgr.remove_sdk_plugin_skills("sdk-demo")

    assert mgr.list_skills(runtime="sandbox") == []

