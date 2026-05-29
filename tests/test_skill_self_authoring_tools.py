"""Tests for skill self-authoring tools (CreateSkillZipTool, InstallSkillFromZipTool)."""
from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.tools.computer_tools.skill_tools import (
    CreateSkillZipTool,
    InstallSkillFromZipTool,
    _resolve_temp_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(role: str = "admin", runtime: str = "local") -> ContextWrapper:
    """Build a minimal ContextWrapper that satisfies check_admin_permission and
    is_local_runtime without requiring a real AstrBot instance."""
    provider_settings = {
        "computer_use_runtime": runtime,
        "computer_use_require_admin": True,
    }
    cfg = {"provider_settings": provider_settings}
    event = SimpleNamespace(role=role, unified_msg_origin="test_umo", get_sender_id=lambda: "test_user_id")
    inner_context = SimpleNamespace(
        get_config=lambda umo: cfg,
        event=event,
    )
    outer_context = SimpleNamespace(context=inner_context, event=event)
    return SimpleNamespace(context=outer_context)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# _resolve_temp_path
# ---------------------------------------------------------------------------


def test_resolve_temp_path_rejects_absolute():
    # Use a platform-appropriate absolute path
    import os
    abs_path = "C:/Windows/System32/evil.zip" if os.name == "nt" else "/etc/passwd"
    with pytest.raises(ValueError, match="Invalid filename"):
        _resolve_temp_path(True, abs_path)


def test_resolve_temp_path_rejects_dotdot():
    with pytest.raises(ValueError, match="Invalid filename"):
        _resolve_temp_path(True, "../escape.zip")


def test_resolve_temp_path_local(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.skill_tools.get_astrbot_temp_path",
        lambda: str(tmp_path),
        raising=False,
    )
    # Patch the import inside the function
    with patch(
        "astrbot.core.utils.astrbot_path.get_astrbot_temp_path",
        return_value=str(tmp_path),
    ):
        result = _resolve_temp_path(True, "my_skill.zip")
    assert result == tmp_path / "my_skill.zip"


# ---------------------------------------------------------------------------
# CreateSkillZipTool
# ---------------------------------------------------------------------------


class TestCreateSkillZipTool:
    def test_invalid_skill_name_rejected(self):
        ctx = _make_context()
        tool = CreateSkillZipTool()
        result = asyncio.run(tool.call(ctx, skill_name="../evil"))
        assert "Invalid skill name" in result

    def test_missing_skill_dir_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.get_astrbot_skills_path",
            lambda: str(tmp_path / "skills"),
        )
        ctx = _make_context()
        tool = CreateSkillZipTool()
        result = asyncio.run(tool.call(ctx, skill_name="nonexistent"))
        assert "not found" in result.lower()

    def test_missing_skill_md_returns_error(self, tmp_path, monkeypatch):
        skills_root = tmp_path / "skills"
        skill_dir = skills_root / "myskill"
        skill_dir.mkdir(parents=True)
        # No SKILL.md

        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.get_astrbot_skills_path",
            lambda: str(skills_root),
        )
        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.get_astrbot_temp_path",
            lambda: str(tmp_path / "temp"),
        )
        ctx = _make_context()
        tool = CreateSkillZipTool()
        result = asyncio.run(tool.call(ctx, skill_name="myskill"))
        assert "SKILL.md" in result

    def test_happy_path_creates_zip(self, tmp_path, monkeypatch):
        skills_root = tmp_path / "skills"
        skill_dir = skills_root / "myskill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("name: myskill\ndescription: test\n")
        (skill_dir / "helper.py").write_text("# helper\n")

        temp_root = tmp_path / "temp"
        temp_root.mkdir()

        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.get_astrbot_skills_path",
            lambda: str(skills_root),
        )
        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.get_astrbot_temp_path",
            lambda: str(temp_root),
        )

        ctx = _make_context()
        tool = CreateSkillZipTool()
        result = asyncio.run(tool.call(ctx, skill_name="myskill"))

        assert "packaged successfully" in result
        zip_file = temp_root / "myskill.zip"
        assert zip_file.exists()
        with zipfile.ZipFile(zip_file) as zf:
            names = zf.namelist()
        assert any("SKILL.md" in n for n in names)
        assert any("helper.py" in n for n in names)

    def test_overwrite_false_blocks_existing_zip(self, tmp_path, monkeypatch):
        skills_root = tmp_path / "skills"
        skill_dir = skills_root / "myskill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("name: myskill\ndescription: test\n")

        temp_root = tmp_path / "temp"
        temp_root.mkdir()
        (temp_root / "myskill.zip").write_bytes(b"existing")

        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.get_astrbot_skills_path",
            lambda: str(skills_root),
        )
        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.get_astrbot_temp_path",
            lambda: str(temp_root),
        )

        ctx = _make_context()
        tool = CreateSkillZipTool()
        result = asyncio.run(tool.call(ctx, skill_name="myskill", overwrite=False))
        assert "already exists" in result.lower()

    def test_non_admin_blocked(self):
        ctx = _make_context(role="member")
        tool = CreateSkillZipTool()
        result = asyncio.run(tool.call(ctx, skill_name="myskill"))
        assert "Permission denied" in result or result.startswith("error:")


# ---------------------------------------------------------------------------
# InstallSkillFromZipTool
# ---------------------------------------------------------------------------


class TestInstallSkillFromZipTool:
    def test_invalid_skill_name_override_rejected(self):
        ctx = _make_context()
        tool = InstallSkillFromZipTool()
        result = asyncio.run(
            tool.call(ctx, zip_path="myskill.zip", skill_name="../evil")
        )
        assert "Invalid skill name" in result

    def test_missing_zip_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.get_astrbot_temp_path",
            lambda: str(tmp_path),
        )
        ctx = _make_context()
        tool = InstallSkillFromZipTool()
        result = asyncio.run(tool.call(ctx, zip_path="nonexistent.zip"))
        assert "not found" in result.lower()

    def test_happy_path_installs_skill(self, tmp_path, monkeypatch):
        # Create a valid skill zip
        skill_zip = tmp_path / "myskill.zip"
        with zipfile.ZipFile(skill_zip, "w") as zf:
            zf.writestr("myskill/SKILL.md", "name: myskill\ndescription: test\n")

        monkeypatch.setattr(
            "astrbot.core.utils.astrbot_path.get_astrbot_temp_path",
            lambda: str(tmp_path),
        )

        mock_manager = MagicMock()
        mock_manager.install_skill_from_zip.return_value = "myskill"

        with patch(
            "astrbot.core.skills.skill_manager.SkillManager",
            return_value=mock_manager,
        ):
            ctx = _make_context()
            tool = InstallSkillFromZipTool()
            result = asyncio.run(tool.call(ctx, zip_path="myskill.zip"))

        assert "Successfully installed" in result
        mock_manager.install_skill_from_zip.assert_called_once()

    def test_non_admin_blocked(self):
        ctx = _make_context(role="member")
        tool = InstallSkillFromZipTool()
        result = asyncio.run(tool.call(ctx, zip_path="myskill.zip"))
        assert "Permission denied" in result or result.startswith("error:")
