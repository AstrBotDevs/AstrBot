from pathlib import Path

import astrbot.dashboard.services.skills_service as skills_service_module
from astrbot.dashboard.services.skills_service import SkillsService


def test_prepare_skill_archive_preserves_versioned_skill_name(
    monkeypatch, tmp_path: Path
):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "skill-writing-1.0.0"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Skill", encoding="utf-8")

    class FakeSkillManager:
        @staticmethod
        def is_sandbox_only_skill(_name: str) -> bool:
            return False

        @staticmethod
        def is_plugin_skill(_name: str) -> bool:
            return False

    FakeSkillManager.skills_root = skills_root

    monkeypatch.setattr(skills_service_module, "SkillManager", FakeSkillManager)
    monkeypatch.setattr(
        skills_service_module,
        "get_astrbot_temp_path",
        lambda: str(tmp_path / "temp"),
    )

    archive = SkillsService(None).prepare_skill_archive("skill-writing-1.0.0")

    assert archive.path.name == "skill-writing-1.0.0.zip"
    assert archive.path.is_file()
    assert archive.filename == "skill-writing-1.0.0.zip"
