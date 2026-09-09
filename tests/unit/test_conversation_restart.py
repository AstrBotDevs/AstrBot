import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.builtin_stars.astrbot.main import Main as CorePlugin
from astrbot.builtin_stars.builtin_commands.commands import conversation as commands
from astrbot.builtin_stars.builtin_commands.main import Main
from astrbot.core import conversation_mgr
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    DEFAULT_CONFIG,
)
from astrbot.core.star.filter.permission import PermissionType, PermissionTypeFilter


@pytest.fixture
def restart(monkeypatch):
    context = MagicMock()
    config = {
        "agent_runner": {"runner_type": "local"},
        "platform_settings": {},
    }
    context.get_config.return_value = config
    manager = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="old-id"),
        get_conversation=AsyncMock(return_value=SimpleNamespace(persona_id="persona")),
        new_conversation=AsyncMock(return_value="new-id"),
        update_conversation=AsyncMock(),
    )
    context.conversation_manager = manager
    plugin = Main.__new__(Main)
    plugin.conversation_c = commands.ConversationCommands(context)
    event = MagicMock()
    event.unified_msg_origin = "qq:GroupMessage:member_group"
    event.get_group_id.return_value = "group"
    event.get_platform_id.return_value = "qq"
    event.is_admin.return_value = True
    extras = {}
    event.set_extra.side_effect = extras.__setitem__
    event.get_extra.side_effect = extras.get
    stop = MagicMock()
    monkeypatch.setattr(commands.active_event_registry, "stop_all", stop)
    return SimpleNamespace(
        plugin=plugin,
        event=event,
        context=context,
        manager=manager,
        config=config,
        stop=stop,
        extras=extras,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["new_conv", "reset"])
@pytest.mark.parametrize("group", [False, True])
@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("isolated", [False, True])
@pytest.mark.parametrize("allow", [False, True])
async def test_restart_permission_matrix(restart, entry, group, admin, isolated, allow):
    restart.event.get_group_id.return_value = "group" if group else ""
    restart.event.is_admin.return_value = admin
    restart.config["platform_settings"] = {
        "unique_session": isolated,
        "allow_member_new_conversation": allow,
    }
    await getattr(restart.plugin, entry)(restart.event)
    restart.context.get_config.assert_called_once_with(
        umo=restart.event.unified_msg_origin
    )
    restart.manager.update_conversation.assert_not_awaited()
    if group and not admin and not allow:
        restart.stop.assert_not_called()
        restart.manager.get_curr_conversation_id.assert_not_awaited()
        restart.manager.new_conversation.assert_not_awaited()
        assert not restart.extras
        assert (
            "administrators"
            in restart.event.set_result.call_args.args[0].get_plain_text()
        )
    else:
        restart.stop.assert_called_once_with(
            restart.event.unified_msg_origin, exclude=restart.event
        )
        restart.manager.new_conversation.assert_awaited_once_with(
            restart.event.unified_msg_origin,
            "qq",
            persona_id="persona",
        )
        assert restart.extras["_clean_group_context_session"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["new_conv", "reset"])
async def test_restart_without_provider_or_current_conversation(restart, entry):
    restart.manager.get_curr_conversation_id.return_value = None
    restart.context.get_using_provider_async = AsyncMock(return_value=None)
    await getattr(restart.plugin, entry)(restart.event)
    restart.manager.new_conversation.assert_awaited_once_with(
        restart.event.unified_msg_origin,
        "qq",
        persona_id=None,
    )
    restart.context.get_using_provider_async.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("runner", ["local", *commands.THIRD_PARTY_AGENT_RUNNER_KEY])
async def test_missing_setting_denies_before_external_cleanup(
    restart, monkeypatch, runner
):
    restart.event.is_admin.return_value = False
    restart.config["agent_runner"]["runner_type"] = runner
    clear = AsyncMock()
    monkeypatch.setattr(commands, "_clear_third_party_agent_runner_state", clear)
    await restart.plugin.reset(restart.event)
    restart.stop.assert_not_called()
    clear.assert_not_awaited()
    restart.manager.new_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_restart_order_and_creation_failure(restart):
    calls = []
    restart.stop.side_effect = lambda *a, **kw: calls.append("stop")
    restart.manager.get_curr_conversation_id.side_effect = lambda *a: (
        calls.append("read") or "old-id"
    )

    async def fail(*args, **kwargs):
        calls.append("create")
        raise RuntimeError("database unavailable")

    restart.manager.new_conversation.side_effect = fail
    with pytest.raises(RuntimeError, match="database unavailable"):
        await restart.plugin.reset(restart.event)
    assert calls == ["stop", "read", "create"]
    restart.event.set_result.assert_not_called()
    assert not restart.extras


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["new_conv", "reset"])
@pytest.mark.parametrize("runner", commands.THIRD_PARTY_AGENT_RUNNER_KEY)
async def test_external_runner_restart(restart, monkeypatch, entry, runner):
    restart.config["agent_runner"]["runner_type"] = runner
    remove = AsyncMock()
    cleanup = AsyncMock()
    monkeypatch.setattr(commands.sp, "remove_async", remove)
    monkeypatch.setattr(commands, "_cleanup_deerflow_thread_if_present", cleanup)
    await getattr(restart.plugin, entry)(restart.event)
    remove.assert_awaited_once_with(
        scope="umo",
        scope_id=restart.event.unified_msg_origin,
        key=commands.THIRD_PARTY_AGENT_RUNNER_KEY[runner],
    )
    assert cleanup.await_count == (runner == commands.DEERFLOW_PROVIDER_TYPE)
    restart.manager.new_conversation.assert_not_awaited()
    restart.manager.update_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_restart_preserves_history_and_late_writes(restart, temp_db, monkeypatch):
    await temp_db.initialize()
    selections = {}
    monkeypatch.setattr(
        conversation_mgr.sp,
        "session_put",
        AsyncMock(
            side_effect=lambda umo, key, value: selections.__setitem__(
                (umo, key), value
            ),
        ),
    )
    monkeypatch.setattr(
        conversation_mgr.sp,
        "session_get",
        AsyncMock(
            side_effect=lambda umo, key, default=None: selections.get(
                (umo, key), default
            ),
        ),
    )
    manager = conversation_mgr.ConversationManager(temp_db)
    restart.context.conversation_manager = manager
    umo = restart.event.unified_msg_origin
    history = [{"role": "user", "content": "Keep this history"}]
    old_id = await manager.new_conversation(
        umo, "qq", content=history, persona_id="persona"
    )
    await restart.plugin.reset(restart.event)
    new_id = await manager.get_curr_conversation_id(umo)
    assert new_id != old_id
    assert json.loads((await manager.get_conversation(umo, old_id)).history) == history
    new = await manager.get_conversation(umo, new_id)
    assert json.loads(new.history) == []
    assert new.persona_id == "persona"
    restored = conversation_mgr.ConversationManager(temp_db)
    assert await restored.get_curr_conversation_id(umo) == new_id
    # A request started earlier saves using its captured conversation ID.
    await manager.update_conversation(
        umo, old_id, history + [{"role": "assistant", "content": "Late reply"}]
    )
    assert json.loads((await manager.get_conversation(umo, new_id)).history) == []
    assert await manager.get_curr_conversation_id(umo) == new_id


@pytest.mark.asyncio
async def test_restart_cleans_only_target_group_cache(restart):
    cache = GroupChatContext(MagicMock(), restart.context)
    target = restart.event.unified_msg_origin
    other = "qq:GroupMessage:another-member_group"
    cache.raw_records[target].append("old target context")
    cache.raw_records[other].append("other context")
    core = CorePlugin.__new__(CorePlugin)
    core.group_chat_context = cache
    core.group_context_enabled = lambda event: True
    await restart.plugin.reset(restart.event)
    assert target in cache.raw_records
    await core.after_message_sent(restart.event)
    assert target not in cache.raw_records
    assert list(cache.raw_records[other]) == ["other context"]


def test_new_setting_does_not_override_command_admin_filter(restart):
    restart.config["platform_settings"]["allow_member_new_conversation"] = True
    restart.event.is_admin.return_value = False
    assert not PermissionTypeFilter(PermissionType.ADMIN).filter(
        restart.event, restart.config
    )


def test_old_config_receives_safe_default_and_preserves_isolation(tmp_path):
    path = tmp_path / "config.json"
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["platform_settings"].pop("allow_member_new_conversation")
    config["platform_settings"]["unique_session"] = True
    path.write_text(json.dumps(config), encoding="utf-8")
    loaded = AstrBotConfig(str(path))
    assert loaded["platform_settings"]["unique_session"] is True
    assert loaded["platform_settings"]["allow_member_new_conversation"] is False
    loaded["platform_settings"]["allow_member_new_conversation"] = True
    loaded.save_config()
    assert (
        AstrBotConfig(str(path))["platform_settings"]["allow_member_new_conversation"]
        is True
    )


@pytest.mark.asyncio
async def test_restart_uses_each_sessions_config(restart):
    restart.event.is_admin.return_value = False
    allowed = copy.deepcopy(restart.config)
    allowed["platform_settings"]["allow_member_new_conversation"] = True
    restart.context.get_config.side_effect = lambda umo: (
        allowed if umo == "qq:GroupMessage:allowed" else restart.config
    )
    restart.event.unified_msg_origin = "qq:GroupMessage:allowed"
    await restart.plugin.reset(restart.event)
    restart.event.unified_msg_origin = "qq:GroupMessage:denied"
    await restart.plugin.new_conv(restart.event)
    assert restart.manager.new_conversation.await_count == 1
    assert restart.stop.call_count == 1


@pytest.mark.parametrize("locale", ["zh-CN", "en-US", "ru-RU", "ja-JP"])
def test_restart_config_metadata_and_translations(locale):
    key = "allow_member_new_conversation"
    assert DEFAULT_CONFIG["platform_settings"][key] is False
    assert (
        CONFIG_METADATA_2["platform_group"]["metadata"]["platform_settings"]["items"][
            key
        ]["type"]
        == "bool"
    )
    assert (
        CONFIG_METADATA_3["platform_group"]["metadata"]["general"]["items"][
            f"platform_settings.{key}"
        ]["type"]
        == "bool"
    )
    path = (
        Path(__file__).resolve().parents[2]
        / "dashboard"
        / "src"
        / "i18n"
        / "locales"
        / locale
        / "features"
        / "config-metadata.json"
    )
    metadata = json.loads(path.read_text(encoding="utf-8"))
    item = metadata["platform_group"]["general"]["platform_settings"][key]
    assert item["description"]
    assert "/new" in item["hint"] and "/reset" in item["hint"]
