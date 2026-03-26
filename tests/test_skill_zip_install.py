from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from astrbot.core.skills.skill_manager import SkillManager


def _make_manager(monkeypatch, tmp_path: Path) -> tuple[SkillManager, Path]:
    data_dir = tmp_path / "data"
    skills_root = tmp_path / "skills"
    temp_dir = tmp_path / "temp"
    data_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_skills_path",
        lambda: str(skills_root),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    return SkillManager(), skills_root


def _write_zip(zip_path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_install_skill_from_rootless_zip(monkeypatch, tmp_path: Path):
    manager, skills_root = _make_manager(monkeypatch, tmp_path)
    archive_path = tmp_path / "rootless.zip"
    _write_zip(
        archive_path,
        {
            "SKILL.md": (
                "---\n"
                "name: rootless-skill\n"
                "description: Root-level archive\n"
                "---\n"
                "# Rootless Skill\n"
            ),
            "assets/config.json": '{"version": 1}',
            "prompts/system.txt": "be helpful",
        },
    )

    skill_name = manager.install_skill_from_zip(str(archive_path))

    assert skill_name == "rootless-skill"
    installed_dir = skills_root / "rootless-skill"
    assert installed_dir.joinpath("SKILL.md").exists()
    assert installed_dir.joinpath("assets", "config.json").read_text(
        encoding="utf-8"
    ) == '{"version": 1}'
    assert installed_dir.joinpath("prompts", "system.txt").read_text(
        encoding="utf-8"
    ) == "be helpful"


def test_install_skill_from_nested_zip_root(monkeypatch, tmp_path: Path):
    manager, skills_root = _make_manager(monkeypatch, tmp_path)
    archive_path = tmp_path / "nested.zip"
    _write_zip(
        archive_path,
        {
            "downloaded-package/README.md": "outer readme",
            "downloaded-package/skills/demo_skill/SKILL.md": (
                "---\n"
                "name: demo-skill\n"
                "description: Nested archive\n"
                "---\n"
                "# Nested Skill\n"
            ),
            "downloaded-package/skills/demo_skill/scripts/run.sh": "echo ok",
        },
    )

    skill_name = manager.install_skill_from_zip(str(archive_path))

    assert skill_name == "demo_skill"
    installed_dir = skills_root / "demo_skill"
    assert installed_dir.joinpath("SKILL.md").exists()
    assert installed_dir.joinpath("scripts", "run.sh").read_text(
        encoding="utf-8"
    ) == "echo ok"


def test_install_skill_from_zip_rejects_multiple_skill_roots(
    monkeypatch,
    tmp_path: Path,
):
    manager, _skills_root = _make_manager(monkeypatch, tmp_path)
    archive_path = tmp_path / "ambiguous.zip"
    _write_zip(
        archive_path,
        {
            "skill_a/SKILL.md": "---\nname: skill-a\n---\n",
            "skill_b/SKILL.md": "---\nname: skill-b\n---\n",
        },
    )

    with pytest.raises(ValueError, match="Multiple skill roots found"):
        manager.install_skill_from_zip(str(archive_path))
