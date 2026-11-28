import json
from types import SimpleNamespace

import pytest

from astrbot.core import capabilities
from astrbot.core.capabilities import CapabilityRef, resolve_tools
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.utils.shared_preferences import SharedPreferences


@pytest.mark.asyncio
async def test_migration_copies_rules_before_retiring_the_old_storage(
    tmp_path, monkeypatch
):
    database = SQLiteDatabase(str(tmp_path / "data_v4.db"))
    await database.initialize()
    preferences = SharedPreferences(database, json_storage_path=tmp_path / "old.json")
    monkeypatch.setattr(capabilities, "sp", preferences)
    try:
        await preferences.global_put("inactivated_plugins", ["data.plugins.notes.main"])
        await preferences.global_put("inactivated_llm_tools", ["search"])
        await preferences.global_put("tool_permissions", {"_default": {"search": "admin"}})
        skills = tmp_path / "skills.json"
        skills.write_text(json.dumps({"skills": {"research": {"active": False}}}))

        await capabilities.migrate_legacy_settings(skills)
        await capabilities.migrate_legacy_settings(skills)

        for key in ("inactivated_plugins", "inactivated_llm_tools", "tool_permissions"):
            assert await preferences.global_get(key) is None
        assert not skills.exists()
        assert skills.with_suffix(".json.migrated").is_file()
        assert await capabilities.legacy_setting("inactivated_plugins", []) == [
            "data.plugins.notes.main"
        ]
        assert await capabilities.legacy_setting("inactivated_llm_tools", []) == ["search"]
        assert await capabilities.legacy_setting("tool_permissions", {}) == {
            "_default": {"search": "admin"}
        }
        assert await capabilities.legacy_setting(capabilities.LEGACY_SKILLS_KEY, {}) == {
            "research": {"active": False}
        }
    finally:
        await preferences.close()
        await database.engine.dispose()


def test_grouped_selection_pins_the_source_even_with_a_legacy_name():
    first = SimpleNamespace(
        name="search",
        active=True,
        capability_ref=CapabilityRef("tool", "plugin", "alice/notes", "search"),
    )
    second = SimpleNamespace(
        name="search",
        active=True,
        capability_ref=CapabilityRef("tool", "plugin", "bob/notes", "search"),
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
    assert first.capability_ref.key == "plugin/alice%2Fnotes/tools/search"
    assert resolve_tools(["search"], [first, second]) == [second]
    assert resolve_tools(groups, [first, second]) == [first]
    assert resolve_tools(groups[1:], [second]) == []
