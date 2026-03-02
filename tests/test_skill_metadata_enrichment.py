"""Tests for skill metadata: frontmatter parsing, prompt generation, absolute paths."""

from __future__ import annotations

from pathlib import Path

from astrbot.core.skills.skill_manager import (
    SkillInfo,
    SkillManager,
    _parse_frontmatter_description,
    build_skills_prompt,
)


# ---------- _parse_frontmatter_description tests ----------


def test_parse_frontmatter_description():
    text = (
        "---\n"
        "name: screenshot-capture\n"
        "description: Captures full-page screenshots of web pages. "
        "Use when user asks to screenshot, take a picture of a page, "
        "截图, or needs a visual snapshot of any URL.\n"
        "---\n"
        "# Screenshot Skill\n"
    )
    desc = _parse_frontmatter_description(text)
    assert "Captures full-page screenshots" in desc
    assert "截图" in desc


def test_parse_frontmatter_description_only():
    text = "---\ndescription: legacy skill\n---\n# Title\n"
    assert _parse_frontmatter_description(text) == "legacy skill"


def test_parse_frontmatter_empty():
    assert _parse_frontmatter_description("no frontmatter") == ""
    assert _parse_frontmatter_description("") == ""


def test_parse_frontmatter_missing_end_delimiter():
    text = "---\ndescription: broken\n"
    assert _parse_frontmatter_description(text) == ""


def test_parse_frontmatter_quoted_description():
    text = '---\ndescription: "quoted value"\n---\n'
    assert _parse_frontmatter_description(text) == "quoted value"


# ---------- build_skills_prompt tests ----------


def test_build_skills_prompt_basic_format():
    skills = [
        SkillInfo(
            name="screenshot",
            description="Take screenshots of web pages",
            path="/abs/skills/screenshot/SKILL.md",
            active=True,
        )
    ]
    prompt = build_skills_prompt(skills)
    assert "**screenshot**" in prompt
    assert "Take screenshots of web pages" in prompt
    assert "`/abs/skills/screenshot/SKILL.md`" in prompt


def test_build_skills_prompt_absolute_path_in_example():
    """The mandatory grounding example should show the absolute path."""
    skills = [
        SkillInfo(
            name="foo",
            description="do foo",
            path="/home/pan/AstrBot/skills/foo/SKILL.md",
            active=True,
        ),
    ]
    prompt = build_skills_prompt(skills)
    assert "cat /home/pan/AstrBot/skills/foo/SKILL.md" in prompt


def test_build_skills_prompt_progressive_disclosure_rules():
    """The prompt should contain the key progressive disclosure rules."""
    skills = [
        SkillInfo(
            name="test",
            description="test skill",
            path="/skills/test/SKILL.md",
            active=True,
        )
    ]
    prompt = build_skills_prompt(skills)
    # Numbered rules
    assert "1." in prompt  # Discovery
    assert "2." in prompt  # When to trigger
    assert "3." in prompt  # Mandatory grounding
    assert "4." in prompt  # Progressive disclosure
    # Key concepts
    assert "Mandatory grounding" in prompt
    assert "Progressive disclosure" in prompt
    assert "SKILL.md" in prompt


def test_build_skills_prompt_no_custom_fields():
    """Prompt should NOT contain triggers/capabilities/output labels."""
    skills = [
        SkillInfo(
            name="test",
            description="test skill",
            path="/skills/test/SKILL.md",
            active=True,
        )
    ]
    prompt = build_skills_prompt(skills)
    assert "Triggers:" not in prompt
    assert "Capabilities:" not in prompt
    assert "Output:" not in prompt


# ---------- list_skills with description ----------


def test_list_skills_parses_description_from_local(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    temp_dir = tmp_path / "temp"
    skills_root = tmp_path / "skills"
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    skill_dir = skills_root / "screencap"
    skill_dir.mkdir()
    skill_dir.joinpath("SKILL.md").write_text(
        "---\n"
        "name: screencap\n"
        "description: Capture screenshots of web pages. "
        "Use when user asks to screenshot, 截图, or capture a page.\n"
        "---\n"
        "# Screenshot\n",
        encoding="utf-8",
    )

    mgr = SkillManager(skills_root=str(skills_root))
    skills = mgr.list_skills()
    assert len(skills) == 1
    s = skills[0]
    assert "Capture screenshots" in s.description
    assert "截图" in s.description
    # SkillInfo should NOT have triggers/capabilities/output attributes
    assert not hasattr(s, "triggers")
    assert not hasattr(s, "capabilities")
    assert not hasattr(s, "output")


def test_list_skills_description_from_sandbox_cache(
    monkeypatch, tmp_path: Path
):
    data_dir = tmp_path / "data"
    temp_dir = tmp_path / "temp"
    skills_root = tmp_path / "skills"
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skills_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    mgr = SkillManager(skills_root=str(skills_root))
    mgr.set_sandbox_skills_cache(
        [
            {
                "name": "web-scrape",
                "description": "Scrape web pages and extract structured data. "
                "Use when user needs to extract content from URLs.",
                "path": "/home/pan/AstrBot/skills/web-scrape/SKILL.md",
            }
        ]
    )

    skills = mgr.list_skills(runtime="sandbox", show_sandbox_path=False)
    assert len(skills) == 1
    s = skills[0]
    assert "Scrape web pages" in s.description
    # Path should be the absolute path from cache
    assert "/home/pan/AstrBot/skills/web-scrape/SKILL.md" in s.path
