from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_builtin_skill_creator_initializes_and_validates(tmp_path: Path) -> None:
    skill_creator_root = (
        Path(__file__).parents[1]
        / "astrbot"
        / "builtin_stars"
        / "astrbot"
        / "skills"
        / "skill-creator"
    )
    target_root = tmp_path / "skills"

    initialized = subprocess.run(
        [
            sys.executable,
            str(skill_creator_root / "scripts" / "init_skill.py"),
            "demo-skill",
            "--path",
            str(target_root),
            "--description",
            "Create demo outputs when the user requests a demo Skill.",
            "--resources",
            "scripts,references",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert initialized.returncode == 0, initialized.stderr
    created_skill = target_root / "demo-skill"
    assert created_skill.joinpath("SKILL.md").is_file()
    assert created_skill.joinpath("scripts").is_dir()
    assert created_skill.joinpath("references").is_dir()
    assert not created_skill.joinpath("assets").exists()

    validated = subprocess.run(
        [
            sys.executable,
            str(skill_creator_root / "scripts" / "validate_skill.py"),
            str(created_skill),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert validated.returncode == 0, validated.stdout + validated.stderr
    assert "valid:" in validated.stdout
