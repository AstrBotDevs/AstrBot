from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from astrbot.core.skills.skill_manager import SkillManager


@dataclass
class MockAstrbotPaths:
    """Mock AstrbotPaths for testing."""
    root: Path
    data: Path
    config: Path
    skills: Path
    temp: Path


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\ndescription: {description}\n---\n# {name}\n",
        encoding="utf-8",
    )


def _create_mock_astrbot_paths(tmp_path: Path) -> MockAstrbotPaths:
    """Create a mock AstrbotPaths object with temp directories."""
    data_dir = tmp_path / "data"
    config_dir = data_dir / "config"
    temp_dir = tmp_path / "temp"
    skills_root = tmp_path / "skills"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)
    return MockAstrbotPaths(
        root=tmp_path,
        data=data_dir,
        config=config_dir,
        skills=skills_root,
        temp=temp_dir,
    )


def test_list_skills_merges_local_and_sandbox_cache(tmp_path: Path):
    mock_paths = _create_mock_astrbot_paths(tmp_path)

    mgr = SkillManager(skills_root=str(mock_paths.skills), astrbot_paths=mock_paths)
    _write_skill(mock_paths.skills, "custom-local", "local description")

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


def test_sandbox_cached_skill_respects_active_and_display_path(tmp_path: Path):
    mock_paths = _create_mock_astrbot_paths(tmp_path)
    mgr = SkillManager(skills_root=str(mock_paths.skills), astrbot_paths=mock_paths)
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


def test_sandbox_and_local_path_resolution_with_show_sandbox_path_false(tmp_path: Path):
    mock_paths = _create_mock_astrbot_paths(tmp_path)
    mgr = SkillManager(skills_root=str(mock_paths.skills), astrbot_paths=mock_paths)
    _write_skill(mock_paths.skills, "custom-local", "local description")
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
    assert local_skill_path.is_relative_to(mock_paths.skills)
    assert local_skill_path == mock_paths.skills / "custom-local" / "SKILL.md"
    assert by_name["python-sandbox"].path == "/app/skills/python-sandbox/SKILL.md"

