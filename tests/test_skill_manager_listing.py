"""Tests for SkillManager.list_skills resilience against broken skill directories."""

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


def _isolate_data_paths(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    temp_dir = tmp_path / "temp"
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )


def test_list_skills_skips_unreadable_skill_dir(monkeypatch, tmp_path: Path):
    # Regression for #10589: one ACL-denied skill directory used to raise out of
    # list_skills and fail the whole agent request, even when the broken skill
    # was unrelated to the request.
    _isolate_data_paths(monkeypatch, tmp_path)
    skills_root = tmp_path / "skills"
    skills_root.mkdir()

    mgr = SkillManager(skills_root=str(skills_root))
    _write_skill(skills_root, "good-skill", "works fine")
    broken = skills_root / "broken-skill"
    broken.mkdir()

    real_iterdir = Path.iterdir

    def fake_iterdir(self: Path):
        if self == broken:
            raise PermissionError("simulated ACL denial")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    skills = mgr.list_skills()
    assert [skill.name for skill in skills] == ["good-skill"]


def test_list_skills_tolerates_unreadable_skills_root(monkeypatch, tmp_path: Path):
    _isolate_data_paths(monkeypatch, tmp_path)
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    mgr = SkillManager(skills_root=str(skills_root))
    _write_skill(skills_root, "good-skill", "works fine")

    real_iterdir = Path.iterdir

    def fake_iterdir(self: Path):
        if self == skills_root:
            raise PermissionError("simulated ACL denial")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    assert mgr.list_skills() == []
