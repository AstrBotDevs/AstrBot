import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_command_config_upsert_applies_defaults_and_preserves_on_none_updates(
    temp_db: SQLiteDatabase,
):
    created = await temp_db.upsert_command_config(
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha",
        module_path="plugin.alpha",
        original_command="hello",
    )

    assert created.enabled is True
    assert created.keep_original_alias is False
    assert created.conflict_key == "hello"
    assert created.auto_managed is False

    updated = await temp_db.upsert_command_config(
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha 2",
        module_path="plugin.alpha.v2",
        original_command="hello",
        resolved_command="/hello",
        enabled=False,
        note="updated",
        auto_managed=True,
    )
    preserved = await temp_db.upsert_command_config(
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha 3",
        module_path="plugin.alpha.v3",
        original_command="hello",
        resolved_command=None,
        enabled=None,
        note=None,
        auto_managed=None,
    )

    assert updated.resolved_command == "/hello"
    assert updated.enabled is False
    assert updated.note == "updated"
    assert updated.auto_managed is True
    assert preserved.plugin_name == "Alpha 3"
    assert preserved.module_path == "plugin.alpha.v3"
    assert preserved.resolved_command == "/hello"
    assert preserved.enabled is False
    assert preserved.note == "updated"
    assert preserved.auto_managed is True

    await temp_db.delete_command_configs(["plugin.alpha.handler"])
    assert await temp_db.get_command_config("plugin.alpha.handler") is None
    await temp_db.delete_command_configs([])


@pytest.mark.asyncio
async def test_command_conflict_upsert_filter_and_delete(temp_db: SQLiteDatabase):
    pending = await temp_db.upsert_command_conflict(
        conflict_key="hello",
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha",
    )
    resolved = await temp_db.upsert_command_conflict(
        conflict_key="hello",
        handler_full_name="plugin.beta.handler",
        plugin_name="Beta",
        status="resolved",
        resolution="rename",
        resolved_command="/hello_beta",
        auto_generated=True,
    )
    updated_pending = await temp_db.upsert_command_conflict(
        conflict_key="hello",
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha v2",
        status="ignored",
        note="manual override",
    )

    assert pending.status == "pending"
    assert resolved.status == "resolved"
    assert resolved.auto_generated is True
    assert updated_pending.plugin_name == "Alpha v2"
    assert updated_pending.status == "ignored"
    assert updated_pending.note == "manual override"

    ignored_rows = await temp_db.list_command_conflicts(status="ignored")
    assert [row.handler_full_name for row in ignored_rows] == ["plugin.alpha.handler"]

    await temp_db.delete_command_conflicts([pending.id, resolved.id])
    remaining = await temp_db.list_command_conflicts()
    assert remaining == []
    await temp_db.delete_command_conflicts([])
