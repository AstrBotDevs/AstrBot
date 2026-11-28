import json
from types import SimpleNamespace

import pytest
from mcp.types import Tool

from astrbot.core import resource_settings
from astrbot.core.agent.mcp_client import MCPClient, MCPTool
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.resource_settings import ResourceRef, resolve_tools, tool_ref
from astrbot.core.utils.shared_preferences import SharedPreferences


@pytest.mark.asyncio
async def test_migration_copies_rules_before_retiring_the_old_storage(
    tmp_path, monkeypatch
):
    database = SQLiteDatabase(str(tmp_path / "data_v4.db"))
    await database.initialize()
    preferences = SharedPreferences(database, json_storage_path=tmp_path / "old.json")
    monkeypatch.setattr(resource_settings, "sp", preferences)
    try:
        await preferences.global_put("inactivated_plugins", ["data.plugins.notes.main"])
        await preferences.global_put("inactivated_llm_tools", ["search"])
        await preferences.global_put(
            "tool_permissions", {"_default": {"search": "admin"}}
        )
        skills = tmp_path / "skills.json"
        old_switches = json.dumps({"skills": {"research": {"active": False}}})
        skills.write_text(old_switches)

        await resource_settings.migrate_legacy_settings(skills)
        for key in ("inactivated_plugins", "inactivated_llm_tools", "tool_permissions"):
            assert await preferences.global_get(key) is None
        assert not skills.exists()
        assert not skills.with_suffix(".json.migrated").exists()

        skills.write_text(old_switches)
        await resource_settings.migrate_legacy_settings(skills)
        assert not skills.exists()

        replacement = json.dumps({"skills": {"research": {"active": True}}})
        skills.write_text(replacement)
        await resource_settings.migrate_legacy_settings(skills)
        assert skills.read_text() == replacement
        assert await resource_settings.legacy_setting("inactivated_plugins", []) == [
            "data.plugins.notes.main"
        ]
        assert await resource_settings.legacy_setting("inactivated_llm_tools", []) == [
            "search"
        ]
        assert await resource_settings.legacy_setting("tool_permissions", {}) == {
            "_default": {"search": "admin"}
        }
        assert await resource_settings.legacy_setting(
            resource_settings.LEGACY_SKILLS_KEY, {}
        ) == {"research": {"active": False}}
    finally:
        await preferences.close()
        await database.engine.dispose()


def test_grouped_selection_pins_the_source_even_with_a_legacy_name():
    first = SimpleNamespace(
        name="search",
        active=True,
        resource_ref=ResourceRef("tool", "plugin", "alice/notes", "search"),
    )
    second = SimpleNamespace(
        name="search",
        active=True,
        resource_ref=ResourceRef("tool", "plugin", "bob/notes", "search"),
    )
    groups = [
        "search",
        {
            "kind": "tool",
            "source": "plugin",
            "source_id": "alice/notes",
            "items": ["search"],
        },
    ]
    assert first.resource_ref.key == "plugin/alice%2Fnotes/tools/search"
    assert resolve_tools(["search"], [first, second]) == [second]
    assert resolve_tools(groups, [first, second]) == [first]
    assert resolve_tools(groups[1:], [second]) == []


def test_mcp_selection_and_settings_key_use_the_server_and_raw_tool_names():
    tool = MCPTool(
        Tool(name="issues.list", inputSchema={"type": "object"}),
        MCPClient(),
        "modelscope/github",
    )
    ref = tool_ref(tool)
    assert ref.source_id == "modelscope/github"
    assert ref.key == "mcp_servers/modelscope%2Fgithub/tools/issues.list"
    selection = [
        {
            "kind": "tool",
            "source": "mcp",
            "source_id": "modelscope/github",
            "items": ["issues.list"],
        },
    ]
    assert resolve_tools(selection, [tool]) == [tool]
