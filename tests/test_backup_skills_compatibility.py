"""Preserve user skill files across current and legacy backup archives."""

import json
import zipfile
from pathlib import Path

import pytest

from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.config.default import VERSION
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_skills_path


@pytest.fixture
def skill_files() -> dict[str, bytes]:
    return {
        "custom-skill/SKILL.md": (
            b"---\r\nname: custom-skill\r\ndescription: User skill\r\n---\r\n"
            b"Keep this user's instructions exactly.\r\n"
        ),
        "custom-skill/scripts/run.py": b"print('user script')\n",
        "custom-skill/assets/reference.bin": b"\x00\xff\x80user-asset\r\n",
    }


def _write_tree(root: Path, files: dict[str, bytes]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _read_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.asyncio
async def test_user_skill_bytes_survive_export_and_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, skill_files: dict[str, bytes]
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    default_root = tmp_path / "default"
    source_skills = source_root / "data" / "skills"
    target_skills = target_root / "data" / "skills"
    default_skills = default_root / "data" / "skills"
    default_files = {"custom-skill/SKILL.md": b"Default root must stay unchanged.\n"}
    _write_tree(source_skills, skill_files)
    _write_tree(default_skills, default_files)
    monkeypatch.chdir(default_root)
    monkeypatch.setenv("ASTRBOT_ROOT", str(source_root))
    assert get_astrbot_skills_path() == str(source_skills)

    source = SQLiteDatabase(str(tmp_path / "source.db"))
    target = SQLiteDatabase(str(tmp_path / "target.db"))
    try:
        archive_path = await AstrBotExporter(
            main_db=source,
            config_path=str(source_root / "data" / "cmd_config.json"),
        ).export_all(output_dir=str(tmp_path / "backups"))
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert "skills" in manifest["directories"]
            assert manifest["statistics"]["directories"]["skills"] == {
                "files": len(skill_files),
                "size": sum(map(len, skill_files.values())),
            }
            assert {
                name.removeprefix("directories/skills/"): archive.read(name)
                for name in archive.namelist()
                if name.startswith("directories/skills/")
            } == skill_files

        monkeypatch.setenv("ASTRBOT_ROOT", str(target_root))
        assert get_astrbot_skills_path() == str(target_skills)
        result = await AstrBotImporter(
            main_db=target,
            config_path=str(target_root / "data" / "cmd_config.json"),
        ).import_all(archive_path)
        assert result.success, result.errors
        assert not result.warnings
        assert result.imported_directories["skills"] == len(skill_files)
        assert _read_tree(target_skills) == skill_files
        assert _read_tree(source_skills) == skill_files
        assert _read_tree(default_skills) == default_files
        assert not source_skills.with_name("skills.bak").exists()
        assert not default_skills.with_name("skills.bak").exists()
    finally:
        await source.engine.dispose()
        await target.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_target", [False, True])
async def test_legacy_skills_archive_restores_only_selected_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    skill_files: dict[str, bytes],
    existing_target: bool,
) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    default_root = tmp_path / "default"
    source_skills = source_root / "data" / "skills"
    target_skills = target_root / "data" / "skills"
    default_skills = default_root / "data" / "skills"
    source_files = {"custom-skill/SKILL.md": b"Original source stays unchanged.\n"}
    default_files = {"custom-skill/SKILL.md": b"Default root stays unchanged.\n"}
    previous_target_files = {
        "custom-skill/SKILL.md": b"Target content before restore.\n",
        "previous-skill/notes.txt": b"Keep the previous tree in skills.bak.\n",
    }
    _write_tree(source_skills, source_files)
    _write_tree(default_skills, default_files)
    if existing_target:
        _write_tree(target_skills, previous_target_files)
    monkeypatch.chdir(default_root)
    monkeypatch.setenv("ASTRBOT_ROOT", str(target_root))
    assert get_astrbot_skills_path() == str(target_skills)

    archive_path = tmp_path / "legacy-skills.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "version": "1.1",
                    "astrbot_version": VERSION,
                    "directories": ["skills"],
                }
            ),
        )
        archive.writestr("databases/main_db.json", "{}")
        for name, content in skill_files.items():
            archive.writestr(f"directories/skills/{name}", content)

    target = SQLiteDatabase(str(tmp_path / "target.db"))
    try:
        result = await AstrBotImporter(
            main_db=target,
            config_path=str(target_root / "data" / "cmd_config.json"),
        ).import_all(str(archive_path))
        assert result.success, result.errors
        assert _read_tree(source_skills) == source_files
        assert _read_tree(default_skills) == default_files
        assert result.imported_directories == {"skills": len(skill_files)}
        assert not result.warnings
        assert _read_tree(target_skills) == skill_files
        if existing_target:
            assert _read_tree(target_skills.with_name("skills.bak")) == (
                previous_target_files
            )
        else:
            assert not target_skills.with_name("skills.bak").exists()
        assert not source_skills.with_name("skills.bak").exists()
        assert not default_skills.with_name("skills.bak").exists()
    finally:
        await target.engine.dispose()
