from pathlib import Path

from astrbot.core.skills.skill_manager import SkillManager


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\ndescription: {description}\n---\n# {name}\n",
        encoding="utf-8",
    )


def test_list_skills_discovers_plugin_skills(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    data_dir.mkdir(parents=True)
    skills_root.mkdir()
    plugin_skills = plugins_root / "astrbot_plugin_demo" / "skills"
    _write_skill(plugin_skills, "demo-skill", "from a plugin")
    _write_skill(skills_root, "local-skill", "from local skills")

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )

    manager = SkillManager(
        skills_root=str(skills_root),
        plugins_root=str(plugins_root),
    )
    by_name = {item.name: item for item in manager.list_skills()}

    assert "demo-skill" in by_name
    assert "local-skill" in by_name
    assert by_name["demo-skill"].description == "from a plugin"
    assert "astrbot_plugin_demo" in by_name["demo-skill"].path
