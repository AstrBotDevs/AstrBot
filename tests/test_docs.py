"""Tests for documentation consistency and integrity."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Project root is 2 levels up from tests/
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DOCS_ROOT = PROJECT_ROOT / "docs"


class TestDocStructure:
    """Test that documentation structure is consistent across languages."""

    def test_docs_directory_exists(self):
        """docs directory should exist."""
        assert DOCS_ROOT.exists(), "docs/ directory not found"
        assert DOCS_ROOT.is_dir(), "docs/ should be a directory"

    def test_zh_docs_exist(self):
        """Chinese docs directory should exist."""
        zh_docs = DOCS_ROOT / "zh"
        assert zh_docs.exists(), "docs/zh/ directory not found"

    def test_en_docs_exist(self):
        """English docs directory should exist."""
        en_docs = DOCS_ROOT / "en"
        assert en_docs.exists(), "docs/en/ directory not found"

    def test_zh_en_mirror_structure(self):
        """zh and en docs should have the same subdirectory structure."""
        zh_dirs = set(_get_all_dirs(DOCS_ROOT / "zh"))
        en_dirs = set(_get_all_dirs(DOCS_ROOT / "en"))

        # Get relative paths from the language root
        zh_rel = {d.relative_to(DOCS_ROOT / "zh") for d in zh_dirs}
        en_rel = {d.relative_to(DOCS_ROOT / "en") for d in en_dirs}

        missing_in_en = zh_rel - en_rel
        missing_in_zh = en_rel - zh_rel

        # Filter out known language-specific docs
        known_diffs = {
            Path("deploy/astrbot/desktop.md"),
            Path("deploy/astrbot/rainyun.md"),
            Path("dev/star/plugin.md"),
            Path("dev/star/guides/other.md"),
            Path("others/github-proxy.md"),
            Path("others/ipv6.md"),
            Path("use/knowledge-base-old.md"),
            Path("config/model-config.md"),
            Path("use/astrbot-sandbox.md"),
            Path("config"),  # en has config dir, zh doesn't
        }

        unexpected_missing_en = missing_in_en - known_diffs
        unexpected_missing_zh = missing_in_zh - known_diffs

        assert not unexpected_missing_en, f"Missing in en docs: {unexpected_missing_en}"
        assert not unexpected_missing_zh, f"Missing in zh docs: {unexpected_missing_zh}"


class TestCoreDocs:
    """Test that core documentation files exist and have content."""

    def test_readme_exists_all_languages(self):
        """README files should exist for all languages."""
        readme_files = [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "README_zh.md",
            PROJECT_ROOT / "README_zh-TW.md",
            PROJECT_ROOT / "README_ja.md",
            PROJECT_ROOT / "README_fr.md",
            PROJECT_ROOT / "README_ru.md",
        ]
        for readme in readme_files:
            assert readme.exists(), f"{readme.name} not found"
            assert readme.stat().st_size > 0, f"{readme.name} is empty"

    def test_readme_has_sponsors_section(self):
        """README files should contain Sponsors section."""
        readme_files = [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "README_zh.md",
        ]
        for readme in readme_files:
            content = readme.read_text(encoding="utf-8")
            assert "Sponsors" in content or "sponsors" in content.lower(), \
                f"{readme.name} missing Sponsors section"

    def test_agents_md_exists(self):
        """AGENTS.md should exist."""
        agents_md = PROJECT_ROOT / "AGENTS.md"
        assert agents_md.exists(), "AGENTS.md not found"
        assert agents_md.stat().st_size > 0, "AGENTS.md is empty"

    def test_claude_md_exists(self):
        """CLAUDE.md should exist for AI coding guidelines."""
        claude_md = PROJECT_ROOT / "CLAUDE.md"
        assert claude_md.exists(), "CLAUDE.md not found"
        assert claude_md.stat().st_size > 0, "CLAUDE.md is empty"

    def test_startup_guide_exists(self):
        """Startup guide should exist in both languages."""
        startup_zh = DOCS_ROOT / "zh" / "startup.md"
        startup_en = DOCS_ROOT / "en" / "startup.md"
        assert startup_zh.exists(), "docs/zh/startup.md not found"
        assert startup_en.exists(), "docs/en/startup.md not found"

    def test_core_docs_have_content(self):
        """Core documentation files should have minimum content."""
        min_lines = 10
        core_docs = [
            DOCS_ROOT / "zh" / "startup.md",
            DOCS_ROOT / "en" / "startup.md",
            PROJECT_ROOT / "CLAUDE.md",
        ]
        for doc in core_docs:
            if doc.exists():
                lines = [l for l in doc.read_text(encoding="utf-8").splitlines() if l.strip()]
                assert len(lines) >= min_lines, f"{doc.name} has less than {min_lines} lines"


class TestDocLinks:
    """Test for broken links in documentation."""

    def test_no_broken_internal_links_readme(self):
        """README.md should not have obviously broken internal links."""
        readme = PROJECT_ROOT / "README.md"
        if not readme.exists():
            pytest.skip("README.md not found")

        content = readme.read_text(encoding="utf-8")

        # Check for common broken patterns
        broken_patterns = [
            r"\[.*\]\(\s*\)",  # Empty links: [text]()
            r"\[.*\]\(\s*#\s*\)",  # Empty anchor: [text](#)
        ]

        for pattern in broken_patterns:
            matches = re.findall(pattern, content)
            assert not matches, f"Found broken link pattern: {pattern}"

    def test_readme_has_valid_structure(self):
        """README.md should have key sections."""
        readme = PROJECT_ROOT / "README.md"
        if not readme.exists():
            pytest.skip("README.md not found")

        content = readme.read_text(encoding="utf-8")

        required_sections = [
            "Key Features",
            "Supported",
            "Deployment",
        ]

        for section in required_sections:
            assert section in content, f"README.md missing '{section}' section"


class TestDocFormatting:
    """Test documentation formatting standards."""

    def test_markdown_files_have_no_trailing_whitespace(self):
        """Markdown files should not have trailing whitespace on lines."""
        md_files = list(DOCS_ROOT.glob("**/*.md"))
        if not md_files:
            pytest.skip("No markdown files found in docs/")

        files_with_issues = []
        for md_file in md_files[:20]:  # Check first 20 files
            content = md_file.read_text(encoding="utf-8")
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                if line.rstrip() != line:
                    files_with_issues.append(f"{md_file.relative_to(PROJECT_ROOT)}:{i}")
                    break

        assert not files_with_issues, \
            f"Files with trailing whitespace: {files_with_issues}"

    def test_readme_files_end_with_newline(self):
        """README files should end with a newline."""
        readme_files = list(PROJECT_ROOT.glob("README*.md"))
        files_without_newline = []

        for readme in readme_files:
            content = readme.read_text(encoding="utf-8")
            if content and not content.endswith("\n"):
                files_without_newline.append(readme.name)

        assert not files_without_newline, \
            f"Files without trailing newline: {files_without_newline}"


class TestSkillDocs:
    """Test that skill documentation exists."""

    def test_dev_guide_skill_exists(self):
        """Developer guide skill should exist in docs/skills."""
        skill_doc = DOCS_ROOT / "skills" / "astrbot-dev-guide.md"
        assert skill_doc.exists(), "docs/skills/astrbot-dev-guide.md not found"
        content = skill_doc.read_text(encoding="utf-8")
        assert len(content) > 100, "Skill doc is too short"

    def test_skill_doc_has_frontmatter(self):
        """Skill doc should have frontmatter with name and description."""
        skill_doc = DOCS_ROOT / "skills" / "astrbot-dev-guide.md"
        if not skill_doc.exists():
            pytest.skip("Skill doc not found")

        content = skill_doc.read_text(encoding="utf-8")
        assert "---" in content, "Skill doc missing frontmatter delimiter"
        assert "name:" in content, "Skill doc missing 'name' in frontmatter"
        assert "description:" in content, "Skill doc missing 'description' in frontmatter"


# Helper functions

def _get_all_dirs(root: Path) -> list[Path]:
    """Get all directories under root, including root itself."""
    dirs = [root]
    for item in root.rglob("*"):
        if item.is_dir() and not _is_ignored_dir(item):
            dirs.append(item)
    return dirs


def _is_ignored_dir(path: Path) -> bool:
    """Check if path is an ignored directory (like node_modules)."""
    ignored_names = {"node_modules", ".ignored", "__pycache__", ".git"}
    return any(part in ignored_names for part in path.parts)
