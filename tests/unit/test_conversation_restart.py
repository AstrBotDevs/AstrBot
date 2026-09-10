import copy
import importlib.util
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
from astrbot.core.star import base as star_base
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.register import star_handler as handler_registration
from astrbot.core.star.star_handler import StarHandlerRegistry


@pytest.fixture
def restart_handlers(monkeypatch):
    """Load real command decorators into isolated registries.

    Args:
        monkeypatch: Fixture used to restore registration targets after loading.

    Returns:
        Fresh built-in command handlers indexed by handler name.
    """
    registry = StarHandlerRegistry()
    path = (
        Path(__file__).resolve().parents[2]
        / "astrbot/builtin_stars/builtin_commands/main.py"
    )
    spec = importlib.util.spec_from_file_location(Main.__module__, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as patch:
        patch.setattr(handler_registration, "star_handlers_registry", registry)
        patch.setattr(star_base, "star_map", {})
        patch.setattr(star_base, "star_registry", [])
        # Execute the decorators without replacing the cached production module.
        spec.loader.exec_module(module)
    return {handler.handler_name: handler for handler in registry}


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
async def test_restart_permission_matrix(
    restart, restart_handlers, entry, group, admin, isolated
):
    restart.event.get_group_id.return_value = "group" if group else ""
    restart.event.is_admin.return_value = admin
    restart.config["platform_settings"] = {
        "unique_session": isolated,
    }
    handler = restart_handlers[entry]
    permission = next(
        f for f in handler.event_filters if isinstance(f, PermissionTypeFilter)
    )
    allowed = permission.filter(restart.event, restart.config)
    assert allowed == (admin or not group)
    if allowed:
        await handler.handler(restart.plugin, restart.event)
    restart.manager.update_conversation.assert_not_awaited()
    if not allowed:
        restart.stop.assert_not_called()
        restart.manager.get_curr_conversation_id.assert_not_awaited()
        restart.manager.new_conversation.assert_not_awaited()
        assert not restart.extras
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


def test_config_preserves_isolation(tmp_path):
    path = tmp_path / "config.json"
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["platform_settings"]["unique_session"] = True
    path.write_text(json.dumps(config), encoding="utf-8")
    loaded = AstrBotConfig(str(path))
    assert loaded["platform_settings"]["unique_session"] is True


@pytest.mark.parametrize("locale", ["zh-CN", "en-US", "ru-RU", "ja-JP"])
def test_restart_config_metadata_and_translations(locale):
    key = "allow_member_new_conversation"
    assert key not in DEFAULT_CONFIG["platform_settings"]
    assert (
        key
        not in CONFIG_METADATA_2["platform_group"]["metadata"]["platform_settings"][
            "items"
        ]
    )
    assert (
        f"platform_settings.{key}"
        not in CONFIG_METADATA_3["platform_group"]["metadata"]["general"]["items"]
    )
    path = (
        Path(__file__).resolve().parents[2]
        / "dashboard/src/i18n/locales"
        / locale
        / "features"
    )
    metadata = json.loads((path / "config-metadata.json").read_text(encoding="utf-8"))
    settings = metadata["platform_group"]["general"]["platform_settings"]
    assert key not in settings
    assert settings["unique_session"]["description"]
    permissions = json.loads((path / "command.json").read_text(encoding="utf-8-sig"))[
        "permission"
    ]
    assert permissions["groupAdmin"]
    assert permissions["groupAdminHint"]
