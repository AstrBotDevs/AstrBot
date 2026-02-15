from __future__ import annotations

from pathlib import Path

from astrbot.core.skills.skill_manager import SkillManager


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\ndescription: {description}\n---\n# {name}\n",
        encoding="utf-8",
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
    assert by_name["python-sandbox"].path == "skills/python-sandbox/SKILL.md"


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

    mgr.set_skill_active("browser-automation", False)
    active_skills = mgr.list_skills(runtime="sandbox", active_only=True)
    assert active_skills == []

