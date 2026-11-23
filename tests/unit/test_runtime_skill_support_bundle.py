"""Shared built-in skill dependencies survive sandbox bundle creation."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from astrbot.core.astr_agent_runtime.computer import computer_client


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["builtin", "plugin", "lookalike"])
async def test_shared_skill_support_is_bundled_once_only_for_builtin_sources(
    monkeypatch, tmp_path: Path, source: str
):
    builtin_root = tmp_path / "builtin"
    skills_root = builtin_root / "astrbot" / "skills"
    support = skills_root / "_astrbot_skill_support"
    support.mkdir(parents=True)
    (support / "__init__.py").write_text("MARKER = 'shared'\n")
    (support / "office.py").write_text("OFFICE = True\n")
    if source == "plugin":
        selected_root = tmp_path / "plugins" / "astrbot" / "skills"
    elif source == "lookalike":
        selected_root = builtin_root / "astrbot" / "skills-extra"
    else:
        selected_root = skills_root
    selected = []
    for name in ("documents", "spreadsheets"):
        skill = selected_root / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# {name}\n")
        selected.append((name, skill))

    monkeypatch.setattr(computer_client, "_collect_sync_skill_dirs", lambda: selected)
    monkeypatch.setattr(
        computer_client, "get_astrbot_builtin_plugin_path", lambda: str(builtin_root)
    )
    monkeypatch.setattr(
        computer_client, "get_astrbot_temp_path", lambda: str(tmp_path / "temp")
    )
    apply = AsyncMock()
    monkeypatch.setattr(computer_client, "_apply_skills_to_sandbox", apply)
    monkeypatch.setattr(
        computer_client, "_scan_sandbox_skills", AsyncMock(return_value={"skills": []})
    )
    monkeypatch.setattr(
        computer_client, "_update_sandbox_skills_cache", lambda _payload: None
    )
    uploaded = []

    async def upload(path, remote):
        with ZipFile(path) as bundle:
            uploaded.append(bundle.namelist())
        assert remote.endswith("/skills.zip")
        return {"success": True}

    booter = SimpleNamespace(
        shell=SimpleNamespace(exec=AsyncMock()), upload_file=upload
    )
    await computer_client._sync_skills_to_sandbox(booter)
    assert len(uploaded) == 1
    names = uploaded[0]
    assert "documents/SKILL.md" in names and "spreadsheets/SKILL.md" in names
    assert names.count("_astrbot_skill_support/__init__.py") == (source == "builtin")
    assert ("_astrbot_skill_support/office.py" in names) is (source == "builtin")
    apply.assert_awaited_once_with(booter)
    assert not list((tmp_path / "temp").iterdir())
