# ruff: noqa: E402
"""Skills 客户端 Core Bridge 集成测试。

测试覆盖 01_context_api.md 中 ctx.skills 的所有方法：
- register(): 注册一个技能
- unregister(): 注销技能
- list(): 列出当前已注册的技能
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_skills_register_and_list(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 创建临时技能目录
    skill_dir = tmp_path / "skills" / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Hello Skill\n\nA greeting skill.")

    # 注册技能
    skill = await ctx.skills.register(
        name="hello",
        path=str(skill_dir),
        description="A greeting skill",
    )

    assert skill.name == "hello"
    assert skill.description == "A greeting skill"

    # 列出技能
    skills = await ctx.skills.list()
    assert len(skills) == 1
    assert skills[0].name == "hello"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_skills_unregister(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 创建并注册技能
    skill_dir = tmp_path / "skills" / "goodbye"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Goodbye Skill")

    await ctx.skills.register(
        name="goodbye",
        path=str(skill_dir),
        description="Goodbye skill",
    )

    # 确认注册成功
    skills = await ctx.skills.list()
    assert len(skills) == 1

    # 注销技能
    removed = await ctx.skills.unregister("goodbye")
    assert removed is True

    # 确认注销成功
    skills_after = await ctx.skills.list()
    assert len(skills_after) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_skills_unregister_nonexistent_returns_false(
    tmp_path, monkeypatch
):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 注销不存在的技能返回 False
    removed = await ctx.skills.unregister("nonexistent")
    assert removed is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_skills_plugin_isolation(tmp_path, monkeypatch):
    """不同插件的技能是隔离的。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    # 创建技能目录
    skill_dir_a = tmp_path / "skills" / "skill-a"
    skill_dir_a.mkdir(parents=True)
    (skill_dir_a / "SKILL.md").write_text("# Skill A")

    skill_dir_b = tmp_path / "skills" / "skill-b"
    skill_dir_b.mkdir(parents=True)
    (skill_dir_b / "SKILL.md").write_text("# Skill B")

    ctx_a = runtime.make_context("plugin-a")
    ctx_b = runtime.make_context("plugin-b")

    # 各自注册技能
    await ctx_a.skills.register(
        name="skill-a", path=str(skill_dir_a), description="Plugin A skill"
    )
    await ctx_b.skills.register(
        name="skill-b", path=str(skill_dir_b), description="Plugin B skill"
    )

    # 各自只能看到自己的技能
    skills_a = await ctx_a.skills.list()
    skills_b = await ctx_b.skills.list()

    assert len(skills_a) == 1
    assert skills_a[0].name == "skill-a"

    assert len(skills_b) == 1
    assert skills_b[0].name == "skill-b"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_skills_register_with_file_path(tmp_path, monkeypatch):
    """注册技能时可以直接指定 SKILL.md 文件路径。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 创建技能文件
    skill_file = tmp_path / "my_skill.md"
    skill_file.write_text("# My Skill\n\nA custom skill.")

    # 使用文件路径注册
    skill = await ctx.skills.register(
        name="my-skill",
        path=str(skill_file),
        description="Custom skill",
    )

    assert skill.name == "my-skill"
    assert Path(skill.skill_dir) == skill_file.parent
