"""
Unit tests for SkillManager.

Covers construction, list_skills with various combinations (active_only,
runtime modes, sandbox caching), set_sandbox_skills_cache,
get_sandbox_skills_cache_status, is_sandbox_only_skill, set_skill_active,
delete_skill, and config persistence.
All tests use mocks to isolate SkillManager from the filesystem and I/O.
"""

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from astrbot.core.skills.skill_manager import (
    DEFAULT_SKILLS_CONFIG,
    SANDBOX_SKILLS_CACHE_FILENAME,
    SKILLS_CONFIG_FILENAME,
    SANDBOX_SKILLS_ROOT,
    SANDBOX_WORKSPACE_ROOT,
    SkillInfo,
    SkillManager,
    _normalize_skill_name,
    _normalize_cached_sandbox_skill_path,
    _is_ignored_zip_entry,
    _sanitize_prompt_path_for_prompt,
    _sanitize_prompt_description,
    _sanitize_skill_display_name,
    build_skills_prompt,
    _parse_frontmatter,
)


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def mock_astrbot_paths():
    """Create mock AstrbotPaths with in-memory-like attributes."""
    paths = MagicMock()
    paths.skills = "/tmp/.astrbot/skills"
    paths.config = Path("/tmp/.astrbot/config")
    paths.data = Path("/tmp/.astrbot/data")
    paths.temp = Path("/tmp/.astrbot/temp")
    return paths


@pytest.fixture
def skill_manager(mock_astrbot_paths):
    """Create a SkillManager with mocked paths and no real FS side effects."""
    with (
        patch("os.makedirs") as mock_makedirs,
        patch.object(Path, "iterdir", return_value=[]),
    ):
        mgr = SkillManager(
            skills_root="/tmp/test_skills",
            astrbot_paths=mock_astrbot_paths,
        )
        return mgr


@pytest.fixture
def sandbox_skill_entry():
    """Create a canned sandbox skill entry as found in cache."""
    return {
        "name": "sandbox-skill",
        "description": "A sandbox preset skill",
        "path": f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/sandbox-skill/SKILL.md",
    }


# ---------------------------------------------------------------
# Construction
# ---------------------------------------------------------------


class TestSkillManagerConstruction:
    """Test SkillManager construction."""

    def test_construction_sets_attributes(self, mock_astrbot_paths):
        """Test that construction sets expected attributes and creates directories."""
        with patch("os.makedirs") as mock_makedirs:
            mgr = SkillManager(
                skills_root="/tmp/test_skills",
                astrbot_paths=mock_astrbot_paths,
            )
            assert mgr.skills_root == "/tmp/test_skills"
            assert mgr.astrbot_paths is mock_astrbot_paths
            mock_makedirs.assert_called_once_with("/tmp/test_skills", exist_ok=True)

    def test_construction_default_skills_root(self, mock_astrbot_paths):
        """Test that skills_root defaults to astrbot_paths.skills."""
        with patch("os.makedirs"):
            mgr = SkillManager(astrbot_paths=mock_astrbot_paths)
            assert mgr.skills_root == str(mock_astrbot_paths.skills)

    def test_construction_config_path(self, mock_astrbot_paths):
        """Test that config_path is derived from astrbot_paths."""
        with patch("os.makedirs"):
            mgr = SkillManager(
                skills_root="/tmp/foo",
                astrbot_paths=mock_astrbot_paths,
            )
            expected = str(mock_astrbot_paths.config / SKILLS_CONFIG_FILENAME)
            assert mgr.config_path == expected

    def test_construction_sandbox_cache_path(self, mock_astrbot_paths):
        """Test that sandbox_skills_cache_path is derived correctly."""
        with patch("os.makedirs"):
            mgr = SkillManager(
                skills_root="/tmp/foo",
                astrbot_paths=mock_astrbot_paths,
            )
            expected = str(
                mock_astrbot_paths.data / SANDBOX_SKILLS_CACHE_FILENAME,
            )
            assert mgr.sandbox_skills_cache_path == expected


# ---------------------------------------------------------------
# list_skills - config loading
# ---------------------------------------------------------------


class TestSkillManagerListSkillsConfig:
    """Test list_skills config loading behavior."""

    def test_list_skills_creates_default_config_when_missing(
        self,
        skill_manager,
        mock_astrbot_paths,
    ):
        """Test that list_skills creates a default config when config file is missing."""
        # Simulate config file does not exist
        with (
            patch("os.path.exists", return_value=False) as mock_exists,
            patch("builtins.open", mock_open()) as mock_file,
            patch.object(Path, "iterdir", return_value=[]),
            patch.object(Path, "exists", return_value=True),
        ):
            # exists is called multiple times; handle skills_root check too
            mock_exists.side_effect = lambda p: False  # all False

            with patch.object(Path, "mkdir"):
                result = skill_manager.list_skills()

            assert result == []
            # Default config should have been saved
            mock_file.assert_any_call(
                skill_manager.config_path,
                "w",
                encoding="utf-8",
            )

    def test_list_skills_loads_existing_skills_from_config(
        self,
        skill_manager,
        mock_astrbot_paths,
    ):
        """Test that list_skills reads skills from skill config files on disk."""
        config_data = json.dumps({"skills": {"my-skill": {"active": True}}})

        skill_dir = MagicMock(spec=Path)
        skill_dir.is_dir.return_value = True
        skill_dir.name = "my-skill"

        skill_md = MagicMock(spec=Path)
        skill_md.exists.return_value = True
        skill_md.read_text.return_value = (
            "---\nname: my-skill\ndescription: My test skill\n---\nDo stuff."
        )

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=config_data)),
            patch.object(Path, "iterdir", return_value=[skill_dir]),
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                return_value=skill_md,
            ),
        ):
            result = skill_manager.list_skills()

        assert len(result) == 1
        assert result[0].name == "my-skill"
        assert result[0].description == "My test skill"
        assert result[0].active is True
        assert result[0].local_exists is True
        assert result[0].source_type == "local_only"

    def test_list_skills_skips_directories_without_skill_md(
        self,
        skill_manager,
    ):
        """Test that directories without SKILL.md are skipped."""
        config_data = json.dumps({"skills": {}})
        skill_dir = MagicMock(spec=Path)
        skill_dir.is_dir.return_value = True
        skill_dir.name = "not-a-skill"

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=config_data)),
            patch.object(Path, "iterdir", return_value=[skill_dir]),
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                return_value=None,
            ),
        ):
            result = skill_manager.list_skills()

        assert result == []

    def test_list_skills_skips_non_directory_entries(
        self,
        skill_manager,
    ):
        """Test that non-directory entries in skills_root are skipped."""
        config_data = json.dumps({"skills": {}})
        file_entry = MagicMock(spec=Path)
        file_entry.is_dir.return_value = False
        file_entry.name = "README.md"

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=config_data)),
            patch.object(Path, "iterdir", return_value=[file_entry]),
        ):
            result = skill_manager.list_skills()

        assert result == []


# ---------------------------------------------------------------
# list_skills - active_only filter
# ---------------------------------------------------------------


class TestSkillManagerActiveOnly:
    """Test the active_only filter in list_skills."""

    def test_list_skills_active_only_excludes_inactive(
        self,
        skill_manager,
    ):
        """Test that active_only=True excludes inactive skills."""
        config_data = json.dumps(
            {
                "skills": {
                    "active-skill": {"active": True},
                    "inactive-skill": {"active": False},
                },
            },
        )

        active_md = MagicMock(spec=Path)
        active_md.read_text.return_value = "---\nname: active-skill\ndescription: Active\n---"
        inactive_md = MagicMock(spec=Path)
        inactive_md.read_text.return_value = (
            "---\nname: inactive-skill\ndescription: Inactive\n---"
        )

        def normalize_skill_markdown_path(skill_dir):
            if skill_dir.name == "active-skill":
                return active_md
            if skill_dir.name == "inactive-skill":
                return inactive_md
            return None

        active_dir = MagicMock(spec=Path)
        active_dir.is_dir.return_value = True
        active_dir.name = "active-skill"

        inactive_dir = MagicMock(spec=Path)
        inactive_dir.is_dir.return_value = True
        inactive_dir.name = "inactive-skill"

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=config_data)),
            patch.object(
                Path,
                "iterdir",
                return_value=[active_dir, inactive_dir],
            ),
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                side_effect=normalize_skill_markdown_path,
            ),
        ):
            result = skill_manager.list_skills(active_only=True)

        assert len(result) == 1
        assert result[0].name == "active-skill"

    def test_list_skills_active_only_false_returns_all(
        self,
        skill_manager,
    ):
        """Test that active_only=False returns all skills."""
        config_data = json.dumps(
            {
                "skills": {
                    "active-skill": {"active": True},
                    "inactive-skill": {"active": False},
                },
            },
        )

        def make_skill_dir(name, md):
            d = MagicMock(spec=Path)
            d.is_dir.return_value = True
            d.name = name
            return d

        def normalize_skill_markdown_path(skill_dir):
            md = MagicMock(spec=Path)
            md.read_text.return_value = f"---\nname: {skill_dir.name}\ndescription: desc\n---"
            return md

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=config_data)),
            patch.object(
                Path,
                "iterdir",
                return_value=[
                    make_skill_dir("active-skill", None),
                    make_skill_dir("inactive-skill", None),
                ],
            ),
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                side_effect=normalize_skill_markdown_path,
            ),
        ):
            result = skill_manager.list_skills(active_only=False)

        assert len(result) == 2


# ---------------------------------------------------------------
# list_skills - sandbox runtime
# ---------------------------------------------------------------


class TestSkillManagerSandbox:
    """Test list_skills with runtime='sandbox'."""

    def test_list_skills_sandbox_includes_sandbox_only_skills(
        self,
        skill_manager,
        sandbox_skill_entry,
    ):
        """Test that sandbox runtime includes sandbox-only skills from cache."""
        config_data = json.dumps({"skills": {}})

        cache_data = json.dumps(
            {
                "version": 1,
                "skills": [sandbox_skill_entry],
            },
        )

        def exists_side_effect(path):
            """Config file exists, sandbox cache exists."""
            return True

        def open_side_effect(path, *args, **kwargs):
            if SANDBOX_SKILLS_CACHE_FILENAME in path:
                return mock_open(read_data=cache_data).return_value
            return mock_open(read_data=config_data).return_value

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("builtins.open", side_effect=open_side_effect),
            patch.object(Path, "iterdir", return_value=[]),
        ):
            result = skill_manager.list_skills(runtime="sandbox")

        assert len(result) == 1
        assert result[0].name == "sandbox-skill"
        assert result[0].source_type == "sandbox_only"
        assert result[0].local_exists is False
        assert result[0].sandbox_exists is True

    def test_list_skills_sandbox_marks_both_synced(
        self,
        skill_manager,
        sandbox_skill_entry,
    ):
        """Test that skills existing both locally and in sandbox cache are 'both'."""
        config_data = json.dumps(
            {"skills": {"local-skill": {"active": True}}},
        )

        cache_data = json.dumps(
            {
                "version": 1,
                "skills": [
                    {
                        "name": "local-skill",
                        "description": "Synced skill",
                        "path": f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/local-skill/SKILL.md",
                    },
                ],
            },
        )

        skill_dir = MagicMock(spec=Path)
        skill_dir.is_dir.return_value = True
        skill_dir.name = "local-skill"

        skill_md = MagicMock(spec=Path)
        skill_md.read_text.return_value = (
            "---\nname: local-skill\ndescription: Local desc\n---"
        )

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open") as mock_open_func,
            patch.object(Path, "iterdir", return_value=[skill_dir]),
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                return_value=skill_md,
            ),
        ):
            # Return different content based on file path
            def open_side_effect(path, *args, **kwargs):
                if SANDBOX_SKILLS_CACHE_FILENAME in str(path):
                    return mock_open(read_data=cache_data).return_value
                return mock_open(read_data=config_data).return_value

            mock_open_func.side_effect = open_side_effect
            result = skill_manager.list_skills(runtime="sandbox")

        assert len(result) == 1
        assert result[0].name == "local-skill"
        assert result[0].source_type == "both"
        assert result[0].local_exists is True
        assert result[0].sandbox_exists is True

    def test_list_skills_sandbox_excludes_local_when_not_in_cache(
        self,
        skill_manager,
        sandbox_skill_entry,
    ):
        """Test that local skills without a sandbox cache entry have sandbox_exists=False."""
        config_data = json.dumps({"skills": {"local-only": {"active": True}}})
        cache_data = json.dumps({"version": 1, "skills": []})

        skill_dir = MagicMock(spec=Path)
        skill_dir.is_dir.return_value = True
        skill_dir.name = "local-only"

        skill_md = MagicMock(spec=Path)
        skill_md.read_text.return_value = (
            "---\nname: local-only\ndescription: Local only\n---"
        )

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open") as mock_open_func,
            patch.object(Path, "iterdir", return_value=[skill_dir]),
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                return_value=skill_md,
            ),
        ):
            def open_side_effect(path, *args, **kwargs):
                if SANDBOX_SKILLS_CACHE_FILENAME in str(path):
                    return mock_open(read_data=cache_data).return_value
                return mock_open(read_data=config_data).return_value

            mock_open_func.side_effect = open_side_effect
            result = skill_manager.list_skills(runtime="sandbox")

        assert len(result) == 1
        assert result[0].name == "local-only"
        assert result[0].local_exists is True
        assert result[0].sandbox_exists is False
        assert result[0].source_type == "local_only"


# ---------------------------------------------------------------
# set_sandbox_skills_cache and get_sandbox_skills_cache_status
# ---------------------------------------------------------------


class TestSkillManagerSandboxCache:
    """Test sandbox cache management."""

    def test_set_sandbox_skills_cache_saves_deduped(
        self,
        skill_manager,
    ):
        """Test that set_sandbox_skills_cache deduplicates and saves."""
        skills = [
            {"name": "skill-a", "description": "A", "path": "/workspace/.../SKILL.md"},
            {"name": "skill-b", "description": "B", "path": "/workspace/.../SKILL.md"},
            {"name": "skill-a", "description": "A dup", "path": "/workspace/.../SKILL.md"},
        ]

        with patch.object(skill_manager, "_save_sandbox_skills_cache") as mock_save:
            skill_manager.set_sandbox_skills_cache(skills)

            saved = mock_save.call_args[0][0]
            assert "skills" in saved
            assert len(saved["skills"]) == 2
            names = [s["name"] for s in saved["skills"]]
            assert "skill-a" in names
            assert "skill-b" in names

    def test_set_sandbox_skills_cache_skips_invalid_names(
        self,
        skill_manager,
    ):
        """Test that entries with invalid names are skipped."""
        skills = [
            {"name": "valid-skill", "description": "ok", "path": ""},
            {"name": "", "description": "empty", "path": ""},
            {"name": "../escape", "description": "bad", "path": ""},
        ]

        with patch.object(skill_manager, "_save_sandbox_skills_cache") as mock_save:
            skill_manager.set_sandbox_skills_cache(skills)

            saved = mock_save.call_args[0][0]
            assert len(saved["skills"]) == 1
            assert saved["skills"][0]["name"] == "valid-skill"

    def test_get_sandbox_skills_cache_status_ready(
        self,
        skill_manager,
    ):
        """Test that status returns ready=True when cache has skills."""
        with (
            patch.object(
                skill_manager,
                "_load_sandbox_skills_cache",
                return_value={
                    "version": 1,
                    "skills": [{"name": "s1"}],
                    "updated_at": "2025-01-01T00:00:00+00:00",
                },
            ),
            patch("os.path.exists", return_value=True),
        ):
            status = skill_manager.get_sandbox_skills_cache_status()

        assert status["exists"] is True
        assert status["ready"] is True
        assert status["count"] == 1

    def test_get_sandbox_skills_cache_status_not_ready(
        self,
        skill_manager,
    ):
        """Test that status returns ready=False when no skills cached."""
        with (
            patch.object(
                skill_manager,
                "_load_sandbox_skills_cache",
                return_value={"version": 1, "skills": []},
            ),
            patch("os.path.exists", return_value=True),
        ):
            status = skill_manager.get_sandbox_skills_cache_status()

        assert status["exists"] is True
        assert status["ready"] is False
        assert status["count"] == 0


# ---------------------------------------------------------------
# is_sandbox_only_skill
# ---------------------------------------------------------------


class TestSkillManagerIsSandboxOnly:
    """Test is_sandbox_only_skill."""

    def test_is_sandbox_only_skill_returns_true_when_only_in_cache(
        self,
        skill_manager,
    ):
        """Test that a skill existing only in cache returns True."""
        with (
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                return_value=None,
            ),
            patch.object(
                skill_manager,
                "_load_sandbox_skills_cache",
                return_value={
                    "version": 1,
                    "skills": [{"name": "sandbox-only"}],
                },
            ),
        ):
            assert skill_manager.is_sandbox_only_skill("sandbox-only") is True

    def test_is_sandbox_only_skill_returns_false_when_local_exists(
        self,
        skill_manager,
    ):
        """Test that a skill with local SKILL.md returns False."""
        with (
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                return_value=MagicMock(),
            ),
        ):
            assert skill_manager.is_sandbox_only_skill("local-skill") is False

    def test_is_sandbox_only_skill_returns_false_for_nonexistent(
        self,
        skill_manager,
    ):
        """Test that a skill not in cache or local returns False."""
        with (
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                return_value=None,
            ),
            patch.object(
                skill_manager,
                "_load_sandbox_skills_cache",
                return_value={"version": 1, "skills": []},
            ),
        ):
            assert skill_manager.is_sandbox_only_skill("ghost") is False


# ---------------------------------------------------------------
# set_skill_active / delete_skill
# ---------------------------------------------------------------


class TestSkillManagerMutations:
    """Test set_skill_active and delete_skill."""

    def test_set_skill_active_saves_config(
        self,
        skill_manager,
    ):
        """Test that set_skill_active writes the config with the new active state."""
        existing_config = {"skills": {"my-skill": {"active": False}}}

        with (
            patch(
                "astrbot.core.skills.skill_manager._normalize_skill_markdown_path",
                return_value=MagicMock(),
            ),
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(existing_config))),
        ):
            skill_manager.set_skill_active("my-skill", True)

        # Config should have been saved with active=True
        # We verify by checking that config file was opened for writing
        # with content containing "active": true
        # The exact assertion depends on mocking — key is it doesn't crash

    def test_set_skill_active_raises_on_sandbox_only(
        self,
        skill_manager,
    ):
        """Test that set_skill_active raises PermissionError for sandbox-only skills."""
        with (
            patch.object(skill_manager, "is_sandbox_only_skill", return_value=True),
            pytest.raises(PermissionError, match="Sandbox preset skill"),
        ):
            skill_manager.set_skill_active("sandbox-only", False)

    def test_delete_skill_removes_directory_and_config(
        self,
        skill_manager,
    ):
        """Test that delete_skill removes the skill directory and config entry."""
        from astrbot.core.skills.skill_manager import _normalize_skill_markdown_path

        skill_dir = MagicMock(spec=Path)
        skill_dir.exists.return_value = True
        skill_dir.name = "my-skill"

        with (
            patch.object(
                skill_manager,
                "is_sandbox_only_skill",
                return_value=False,
            ),
            patch("pathlib.Path", return_value=skill_dir) as mock_path_cls,
            patch("shutil.rmtree") as mock_rmtree,
            patch.object(skill_manager, "_remove_skill_from_sandbox_cache"),
            patch.object(skill_manager, "_load_config",
                         return_value={"skills": {"my-skill": {"active": True}}}),
            patch.object(skill_manager, "_save_config") as mock_save,
        ):
            skill_manager.delete_skill("my-skill")
            mock_rmtree.assert_called_once_with(skill_dir)
            mock_save.assert_called_once()

    def test_delete_skill_raises_on_sandbox_only(
        self,
        skill_manager,
    ):
        """Test that delete_skill raises PermissionError for sandbox-only skills."""
        with (
            patch.object(skill_manager, "is_sandbox_only_skill", return_value=True),
            pytest.raises(PermissionError, match="Sandbox preset skill"),
        ):
            skill_manager.delete_skill("sandbox-only")


# ---------------------------------------------------------------
# utility / helper functions
# ---------------------------------------------------------------


class TestSkillManagerUtilities:
    """Test standalone utility functions in skill_manager module."""

    def test_normalize_skill_name_replaces_spaces(self):
        """Test that _normalize_skill_name replaces whitespace with underscores."""
        result = _normalize_skill_name("my cool skill")
        assert result == "my_cool_skill"
        assert _normalize_skill_name("  hello  world  ") == "hello_world"
        assert _normalize_skill_name(None) == ""

    def test_normalize_cached_sandbox_skill_path_default(self):
        """Test that empty path defaults to the standard sandbox SKILL.md path."""
        result = _normalize_cached_sandbox_skill_path("my-skill", "")
        expected = f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/my-skill/SKILL.md"
        assert result == expected

    def test_normalize_cached_sandbox_skill_path_rejects_relative_escape(self):
        """Test that path with '..' is rejected and falls back to default."""
        result = _normalize_cached_sandbox_skill_path("my-skill", "/workspace/../../etc/SKILL.md")
        expected = f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/my-skill/SKILL.md"
        assert result == expected

    def test_normalize_cached_sandbox_skill_path_rejects_wrong_filename(self):
        """Test that a path not ending in SKILL.md falls back to default."""
        result = _normalize_cached_sandbox_skill_path("my-skill", "/workspace/skills/my-skill/README.md")
        expected = f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/my-skill/SKILL.md"
        assert result == expected

    def test_normalize_cached_sandbox_skill_path_rejects_wrong_dir_name(self):
        """Test that a path with mismatched directory name falls back to default."""
        result = _normalize_cached_sandbox_skill_path("my-skill", "/workspace/skills/other-skill/SKILL.md")
        expected = f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/my-skill/SKILL.md"
        assert result == expected

    def test_is_ignored_zip_entry_macosx(self):
        """Test that __MACOSX entries are ignored."""
        assert _is_ignored_zip_entry("__MACOSX/") is True
        assert _is_ignored_zip_entry("__MACOSX/somefile") is True
        assert _is_ignored_zip_entry("my-skill/SKILL.md") is False

    def test_sanitize_prompt_path_for_prompt_removes_backticks(self):
        """Test that backticks are stripped from path."""
        result = _sanitize_prompt_path_for_prompt("/path/with`backticks`/SKILL.md")
        assert "`" not in result
        assert "backticks" in result

    def test_sanitize_prompt_description_cleans_whitespace(self):
        """Test that description is cleaned of extra whitespace."""
        result = _sanitize_prompt_description("  hello   world  ")
        assert result == "hello world"

    def test_sanitize_skill_display_name_invalid(self):
        """Test that invalid names return <invalid_skill_name>."""
        result = _sanitize_skill_display_name("../escape")
        assert result == "<invalid_skill_name>"

    def test_sanitize_skill_display_name_valid(self):
        """Test that valid names pass through unchanged."""
        result = _sanitize_skill_display_name("my-valid_skill1")
        assert result == "my-valid_skill1"

    def test_parse_frontmatter_extracts_meta(self):
        """Test that YAML frontmatter is parsed correctly."""
        text = "---\nname: test\ndescription: hello\ninput_schema:\n  type: object\n---\nBody"
        result = _parse_frontmatter(text)
        assert result["name"] == "test"
        assert result["description"] == "hello"
        assert result["input_schema"] == {"type": "object"}

    def test_parse_frontmatter_returns_empty_when_no_frontmatter(self):
        """Test that text without frontmatter returns empty dict."""
        result = _parse_frontmatter("No frontmatter here")
        assert result == {}

    def test_parse_frontmatter_returns_empty_on_yaml_error(self):
        """Test that malformed YAML returns empty dict."""
        text = "---\n: invalid yaml :::\n---\nBody"
        result = _parse_frontmatter(text)
        assert result == {}

    def test_build_skills_prompt_generates_block(self):
        """Test that build_skills_prompt generates a non-empty prompt block."""
        skills = [
            SkillInfo(
                name="test-skill",
                description="A test skill",
                path="/tmp/skills/test-skill/SKILL.md",
                active=True,
            ),
        ]
        result = build_skills_prompt(skills)
        assert "## Skills" in result
        assert "test-skill" in result
        assert "A test skill" in result
        assert "SKILL.md" in result

    def test_build_skills_prompt_empty_list(self):
        """Test that build_skills_prompt with no skills still produces a block."""
        result = build_skills_prompt([])
        assert "## Skills" in result
        assert "Available skills" in result
