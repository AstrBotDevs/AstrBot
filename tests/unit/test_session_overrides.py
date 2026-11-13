"""Behavioral coverage for explicit overrides and legacy migration."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from astrbot.core import session_overrides as overrides
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.migration import migra_session_overrides as migration
from astrbot.core.event_bus import EventBus
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.pipeline.session_status_check.stage import SessionStatusCheckStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import ProviderType
from astrbot.core.star.context import Context
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.dashboard.services import session_management_service as service_module

UMO = "test:GroupMessage:42"


@pytest_asyncio.fixture
async def override_environment(temp_db, tmp_path, monkeypatch):
    """Provide a real isolated database and profile manager for every test."""
    await temp_db.initialize()
    prefs = SharedPreferences(temp_db)
    await prefs.initialize()
    monkeypatch.setattr(overrides, "sp", prefs)
    monkeypatch.setattr(overrides, "_locks", [asyncio.Lock() for _ in range(64)])
    monkeypatch.setattr(migration, "sp", prefs)
    monkeypatch.setattr("astrbot.core.conversation_mgr.sp", prefs)
    monkeypatch.setattr(service_module, "sp", prefs)
    config = AstrBotConfig(str(tmp_path / "profile.json"), deepcopy(DEFAULT_CONFIG))
    router = UmopConfigRouter(prefs)
    acm = AstrBotConfigManager(config, router, prefs)
    acm.abconf_data = {}
    yield prefs, acm, temp_db
    await prefs.close()


@pytest.fixture
def pipeline_environment(override_environment):
    """Provide a real pipeline context and configuration access without plugins."""
    _, acm, _ = override_environment
    plugin_context = object.__new__(Context)
    plugin_context._config = acm.default_conf
    plugin_context.astrbot_config_mgr = acm
    ctx = PipelineContext(
        acm.default_conf, SimpleNamespace(context=plugin_context), "default"
    )
    return acm, ctx, PipelineScheduler(ctx)


@pytest.fixture
def make_message():
    """Create independent group messages for concurrent and nested executions."""
    def create(session_id="42"):
        message = AstrBotMessage()
        message.type = MessageType.GROUP_MESSAGE
        message.group_id = session_id
        message.sender = MessageMember(user_id="alice")
        message.message = []
        event = AstrMessageEvent(
            "hello", message, PlatformMetadata("aiocqhttp", "test", "test"), session_id
        )
        event.is_at_or_wake_command = True
        event.set_extra("activated_handlers", [])
        return event
    return create


@pytest.mark.asyncio
@pytest.mark.parametrize("has_overrides", [False, True])
async def test_runtime_config_rejects_both_save_methods_without_touching_profile(
    pipeline_environment, has_overrides,
):
    acm, _, _ = pipeline_environment
    if has_overrides:
        await overrides.update_overrides(UMO, {"wake_prefix": ["!"]})
    base = acm.default_conf
    profile = Path(base.config_path)
    original = profile.read_bytes()
    config, _ = acm._create_message_config(UMO)
    before = deepcopy(dict(config))
    with pytest.raises(ValueError, match="session override"):
        config.save_config({"wake_prefix": ["blocked"]})
    with pytest.raises(ValueError, match="session override"):
        await config.save_config_async({"wake_prefix": ["blocked"]})
    assert config == before
    assert profile.read_bytes() == original
    # File-backed profiles retain their existing save behavior.
    await base.save_config_async({"wake_prefix": ["saved"]})
    assert json.loads(profile.read_text(encoding="utf-8-sig"))["wake_prefix"] == ["saved"]
    assert config == before


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_persona", [False, True])
async def test_persona_inheritance_uses_message_override_metadata(
    pipeline_environment, override_environment, make_message, explicit_persona,
):
    acm, _, scheduler = pipeline_environment
    _, _, db = override_environment
    path = "agent.config.persona.persona_id"
    acm.default_conf["agent"]["config"]["persona"]["persona_id"] = "default"
    if explicit_persona:
        await overrides.update_overrides(UMO, {path: "default"})
    personas = PersonaManager(db, acm)
    personas.personas_v3 = [{"name": "default", "prompt": "Profile persona"}]

    async def process(event):
        before = await personas.resolve_selected_persona(
            umo=UMO, platform_name="webchat"
        )
        assert before[2] is (not explicit_persona)
        await overrides.update_overrides(UMO, {path: None if explicit_persona else "default"})
        after = await personas.resolve_selected_persona(
            umo=UMO, platform_name="webchat"
        )
        assert after == before

    scheduler.stages = [SimpleNamespace(process=process)]
    await scheduler.execute(make_message())
    resolved = await personas.resolve_selected_persona(
        umo=UMO, platform_name="webchat"
    )
    assert resolved[2] is explicit_persona


@pytest.mark.asyncio
@pytest.mark.parametrize("has_overrides", [False, True])
async def test_pipeline_copies_configuration_once_per_message(
    pipeline_environment, make_message, has_overrides,
):
    """Visit nested profile data only once while keeping same-UMO messages isolated."""
    acm, ctx, scheduler = pipeline_environment
    copies = []

    class TrackedConfig(dict):
        def __deepcopy__(self, memo):
            copies.append(self)
            return TrackedConfig(deepcopy(dict(self), memo))

    acm.default_conf["plugin_config"] = TrackedConfig({"items": ["base"]})
    if has_overrides:
        await overrides.update_overrides(UMO, {"wake_prefix": ["!"]})
    snapshots = []
    ready = asyncio.Event()

    async def process(event):
        config = ctx.astrbot_config
        assert config is acm.get_conf(UMO)
        assert config["plugin_config"]["items"] == ["base"]
        config["plugin_config"]["items"].append("local")
        snapshots.append(config)
        if len(snapshots) == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 2)
        assert config["plugin_config"]["items"] == ["base", "local"]

    scheduler.stages = [SimpleNamespace(process=process)]
    await asyncio.gather(scheduler.execute(make_message()), scheduler.execute(make_message()))
    assert len(copies) == 2
    assert snapshots[0] is not snapshots[1]
    assert acm.default_conf["plugin_config"]["items"] == ["base"]
    assert ctx.astrbot_config is acm.default_conf


@pytest.mark.asyncio
async def test_pipeline_config_isolates_concurrent_messages_and_ai_gate(
    pipeline_environment, make_message,
):
    acm, ctx, scheduler = pipeline_environment
    acm.default_conf["provider_settings"]["enable"] = False
    await overrides.update_overrides(UMO, {"provider_settings.enable": True})
    events = [make_message(), make_message("43")]
    snapshots = {}
    both_started = asyncio.Event()
    invoked = []

    async def inspect(event):
        config = ctx.astrbot_config
        assert config is ctx.plugin_manager.context.get_config(event.unified_msg_origin)
        assert acm.get_conf(None) is acm.default_conf
        snapshots[event.unified_msg_origin] = config
        if len(snapshots) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), 2)
        assert ctx.astrbot_config is config
        config["wake_prefix"].append(event.session_id)
        assert config["wake_prefix"][-1] == event.session_id
        assert len(config["wake_prefix"]) == len(acm.default_conf["wake_prefix"]) + 1

    async def invoke(event):
        invoked.append(event.unified_msg_origin)
        yield

    process = ProcessStage()
    process.ctx = ctx
    process.agent_sub_stage = SimpleNamespace(process=invoke)
    scheduler.stages = [SimpleNamespace(process=inspect), process]
    await asyncio.gather(*(scheduler.execute(event) for event in events))
    assert invoked == [UMO]
    assert snapshots[UMO] is not snapshots[events[1].unified_msg_origin]
    assert ctx.astrbot_config is acm.default_conf
    assert acm.default_conf["provider_settings"]["enable"] is False


@pytest.mark.asyncio
async def test_pipeline_snapshot_stays_stable_until_next_message(
    pipeline_environment, make_message,
):
    acm, ctx, scheduler = pipeline_environment
    acm.default_conf["provider_settings"]["enable"] = False
    entered = False

    async def process(event):
        nonlocal entered
        snapshot = ctx.astrbot_config
        if entered:
            assert snapshot["provider_settings"]["enable"] is True
            return
        entered = True
        assert snapshot["provider_settings"]["enable"] is False
        await overrides.update_overrides(UMO, {"provider_settings.enable": True})
        assert acm.get_conf(UMO) is snapshot
        assert snapshot["provider_settings"]["enable"] is False
        # A new nested message for the same UMO gets fresh values; its parent
        # retains the original snapshot when the nested execution returns.
        await scheduler.execute(make_message())
        assert ctx.astrbot_config is snapshot
        assert acm.get_conf(UMO) is snapshot

    scheduler.stages = [SimpleNamespace(process=process)]
    await scheduler.execute(make_message())
    assert ctx.astrbot_config is acm.default_conf
    assert acm.get_conf(UMO)["provider_settings"]["enable"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("completion", ["success", "error", "cancel"])
async def test_pipeline_scope_cleans_up_including_inherited_tasks(
    pipeline_environment, make_message, completion,
):
    acm, ctx, scheduler = pipeline_environment
    await overrides.update_overrides(UMO, {"wake_prefix": ["old"]})
    started = asyncio.Event()
    released = asyncio.Event()
    children = []

    async def inherited():
        assert ctx.astrbot_config["wake_prefix"] == ["old"]
        started.set()
        await released.wait()
        assert ctx.astrbot_config is acm.default_conf
        assert acm.get_conf(UMO)["wake_prefix"] == ["new"]

    async def process(event):
        children.append(asyncio.create_task(inherited()))
        await started.wait()
        if completion == "error":
            raise RuntimeError("failed")
        if completion == "cancel":
            raise asyncio.CancelledError

    scheduler.stages = [SimpleNamespace(process=process)]
    try:
        if completion == "success":
            await scheduler.execute(make_message())
        else:
            with pytest.raises(RuntimeError if completion == "error" else asyncio.CancelledError):
                await scheduler.execute(make_message())
        assert ctx.astrbot_config is acm.default_conf
        await overrides.update_overrides(UMO, {"wake_prefix": ["new"]})
    finally:
        released.set()
        await asyncio.gather(*children)


@pytest.mark.asyncio
async def test_event_bus_routes_final_session_to_matching_pipeline(
    pipeline_environment, make_message, tmp_path,
):
    acm, ctx, default_scheduler = pipeline_environment
    acm.default_conf["platform_settings"]["unique_session"] = True
    isolated_umo = "test:GroupMessage:alice_42"
    config = AstrBotConfig(str(tmp_path / "isolated.json"), deepcopy(DEFAULT_CONFIG))
    config["wake_prefix"] = ["isolated"]
    acm.confs["isolated"] = config
    acm.abconf_data["isolated"] = {"name": "Isolated", "path": "isolated.json"}
    await overrides.update_overrides(
        isolated_umo, {"wake_prefix": ["override"]},
        profile_id="isolated", update_profile=True,
    )
    isolated_ctx = PipelineContext(config, ctx.plugin_manager, "isolated")
    scheduler = PipelineScheduler(isolated_ctx)
    finished = asyncio.Event()

    async def process(event):
        assert event.unified_msg_origin == isolated_umo
        assert isolated_ctx.astrbot_config is acm.get_conf(isolated_umo)
        assert isolated_ctx.astrbot_config["wake_prefix"] == ["override"]
        finished.set()

    scheduler.stages = [SimpleNamespace(process=process)]
    default_scheduler._process_stages = AsyncMock()
    queue = asyncio.Queue()
    await queue.put(make_message())
    bus = EventBus(queue, {"default": default_scheduler, "isolated": scheduler}, acm)
    task = asyncio.create_task(bus.dispatch())
    try:
        await asyncio.wait_for(finished.wait(), 2)
        default_scheduler._process_stages.assert_not_called()
    finally:
        task.cancel()
        await asyncio.gather(task, *bus._pending_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_explicit_switches_lists_restore_and_profile_changes(
    override_environment,
):
    prefs, acm, _ = override_environment
    acm.default_conf["provider_settings"]["enable"] = False
    acm.default_conf["kb_names"] = ["Shared"]
    await overrides.update_overrides(
        UMO,
        {
            "provider_settings.enable": True,
            "kb_names": [],
            "disabled_plugins": ["weather"],
        },
    )
    effective = acm.get_conf(UMO)
    assert effective["provider_settings"]["enable"] is True
    assert effective["kb_names"] == []
    assert acm.default_conf["provider_settings"]["enable"] is False
    assert acm.default_conf["kb_names"] == ["Shared"]
    effective["platform_settings"]["id_whitelist"].append("other")
    assert acm.default_conf["platform_settings"]["id_whitelist"] == []
    await overrides.update_overrides(UMO, {"kb_names": None})
    acm.default_conf["kb_names"] = ["Updated"]
    assert acm.get_conf(UMO)["kb_names"] == ["Updated"]
    assert acm.get_conf("test:GroupMessage:43")["provider_settings"]["enable"] is False
    assert "kb_names" not in await overrides.get_overrides(UMO)

    with pytest.raises(ValueError):
        await overrides.update_overrides(UMO, {"provider_settings.enable": "false"})
    with pytest.raises(ValueError):
        await overrides.update_overrides(UMO, {"admins_id": ["unexpected"]})


@pytest.mark.asyncio
async def test_model_and_persona_writes_use_same_overrides(override_environment):
    prefs, acm, db = override_environment
    manager = ProviderManager.__new__(ProviderManager)
    manager.inst_map = {"model-B": object()}
    manager._notify_provider_changed = MagicMock()
    await manager.set_provider("model-B", ProviderType.CHAT_COMPLETION, UMO)
    conversation = ConversationManager(db, acm)
    cid = await conversation.new_conversation(UMO)
    await conversation.update_conversation(UMO, cid, persona_id="B")
    values = await overrides.get_overrides(UMO)
    assert values == {
        "agent.config.model.provider_id": "model-B",
        "agent.config.persona.persona_id": "B",
    }
    personas = PersonaManager(db, acm)
    personas.personas_v3 = [{"name": "B", "prompt": "B"}, {"name": "C", "prompt": "C"}]
    resolved = await personas.resolve_selected_persona(
        umo=UMO,
        platform_name="test",
    )
    assert resolved[0] == "B"
    await overrides.update_overrides(UMO, {"agent.config.persona.persona_id": "C"})
    resolved = await personas.resolve_selected_persona(
        umo=UMO,
        platform_name="test",
    )
    assert resolved[0] == "C"
    assert await prefs.session_get(UMO, "provider_perf_chat_completion") is None


@pytest.mark.asyncio
async def test_blacklist_blocks_admin_and_restore(override_environment):
    _, acm, _ = override_environment
    event = MagicMock()
    event.unified_msg_origin = UMO
    event.role = "admin"
    event.get_group_id.return_value = "42"
    context = SimpleNamespace(
        get_config=lambda umo: acm.get_conf(umo),
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value="cid")
        ),
    )
    stage = SessionStatusCheckStage()
    await stage.initialize(
        SimpleNamespace(plugin_manager=SimpleNamespace(context=context))
    )
    acm.default_conf["platform_settings"]["id_blacklist"] = ["42"]
    await stage.process(event)
    event.stop_event.assert_called_once()
    event.stop_event.reset_mock()
    await overrides.update_overrides(UMO, {"platform_settings.id_blacklist": []})
    await stage.process(event)
    event.stop_event.assert_not_called()


@pytest.mark.asyncio
async def test_migration_preserves_alias_groups_and_unrelated_preferences(
    override_environment,
):
    prefs, acm, db = override_environment
    group = {"work": {"name": "Work", "umos": [UMO]}}
    await prefs.put_async("unknown", "unknown", "session_groups", group)
    await prefs.session_put(UMO, "session_variables", {"keep": "value"})
    conv = await db.create_conversation(
        user_id=UMO, platform_id="test", persona_id="conversation-persona"
    )
    await prefs.session_put(UMO, "sel_conv_id", conv.conversation_id)
    await prefs.session_put(
        UMO,
        "session_service_config",
        {
            "session_enabled": False,
            "llm_enabled": True,
            "tts_enabled": False,
            "persona_id": "rule-persona",
            "custom_name": "Legacy alias",
        },
    )
    await prefs.session_put(
        UMO, "session_plugin_config", {UMO: {"disabled_plugins": ["weather"]}}
    )
    await prefs.session_put(
        UMO, "kb_config", {"kb_ids": ["kb1"], "top_k": 3, "enable_rerank": False}
    )
    await prefs.session_put(UMO, "provider_perf_chat_completion", "model-B")
    await db.upsert_umo_alias(UMO, "owner", "Auto name", "Existing alias")
    await migration.migrate_session_overrides(acm, db)
    values = await overrides.get_overrides(UMO)
    assert values == {
        "agent.config.persona.persona_id": "rule-persona",
        "provider_tts_settings.enable": False,
        "platform_settings.id_blacklist": [UMO],
        "disabled_plugins": ["weather"],
        "kb_names": ["kb1"],
        "kb_final_top_k": 3,
        "agent.config.model.provider_id": "model-B",
    }
    assert (await db.get_umo_aliases([UMO]))[0].user_alias == "Existing alias"
    assert await prefs.get_async("unknown", "unknown", "session_groups") == group
    assert await prefs.session_get(UMO, "session_variables") == {"keep": "value"}
    assert await prefs.session_get(UMO, "sel_conv_id") == conv.conversation_id
    assert await prefs.session_get(UMO, "kb_config") is None
    await overrides.update_overrides(UMO, {"agent.config.persona.persona_id": None})
    await migration.migrate_session_overrides(acm, db)
    assert "agent.config.persona.persona_id" not in await overrides.get_overrides(UMO)


@pytest.mark.asyncio
@pytest.mark.parametrize("kb_ids", [["kb1", "not-loaded"], []])
async def test_migration_keeps_kb_ids_until_instances_become_available(
    override_environment, kb_ids
):
    """Keep references across unavailable KBs, later loading and renaming."""
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    prefs, acm, db = override_environment
    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.kb_insts = {}
    manager.retrieval_manager = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    await prefs.session_put(UMO, "kb_config", {"kb_ids": kb_ids, "top_k": 3})

    await migration.migrate_session_overrides(acm, db)
    values = await overrides.get_overrides(UMO)
    assert values["kb_names"] == kb_ids
    assert await prefs.session_get(UMO, "kb_config") is None
    assert await manager.retrieve("question", values["kb_names"]) == {}

    if kb_ids:
        helper = SimpleNamespace(
            kb=SimpleNamespace(kb_id="kb1", kb_name="Renamed handbook"),
            init_error=None,
        )
        manager.kb_insts["kb1"] = helper
        await manager.retrieve("question", acm.get_conf(UMO)["kb_names"])
        manager.retrieval_manager.retrieve.assert_awaited_once()
        assert manager.retrieval_manager.retrieve.call_args.kwargs["kb_ids"] == ["kb1"]
    await migration.migrate_session_overrides(acm, db)
    assert (await overrides.get_overrides(UMO))["kb_names"] == kb_ids


@pytest.mark.asyncio
async def test_migration_moves_legacy_alias_and_keeps_auto_metadata(
    override_environment,
):
    prefs, acm, db = override_environment
    await db.upsert_umo_auto_name(UMO, "sender", "Auto name")
    await prefs.session_put(UMO, "session_service_config", {"custom_name": "Work"})
    await migration.migrate_session_overrides(acm, db)
    alias = (await db.get_umo_aliases([UMO]))[0]
    assert alias.user_alias == "Work"
    assert alias.auto_name == "Auto name"
    assert alias.creator_sender_id == "sender"


@pytest.mark.asyncio
async def test_binding_migration_keeps_route_order_and_dynamic_base(override_environment, tmp_path):
    from astrbot.core.config_bindings import BINDING_KEY

    prefs, acm, _ = override_environment
    acm.abconf_data = {
        name: {"name": name, "path": f"{name}.json"} for name in ("broad", "exact")
    }
    acm.confs["broad"] = AstrBotConfig(str(tmp_path / "broad.json"), deepcopy(DEFAULT_CONFIG))
    acm.confs["exact"] = AstrBotConfig(str(tmp_path / "exact.json"), deepcopy(DEFAULT_CONFIG))
    acm.confs["broad"]["kb_names"] = ["Broad"]
    acm.confs["exact"]["kb_names"] = ["Exact"]
    await prefs.global_put("umop_config_routing", {"test::*": "broad", UMO: "exact"})
    await prefs.session_put(UMO, "config_overrides", {"provider_settings.enable": False})
    await acm.ucr.initialize()
    assert list(acm.ucr.umop_to_conf_id) == ["test::*", UMO]
    assert acm.get_conf_info(UMO)["id"] == "broad"
    assert acm.get_conf(UMO)["provider_settings"]["enable"] is False
    assert await prefs.session_get(UMO, BINDING_KEY) == {
        "profile_id": None, "overrides": {"provider_settings.enable": False}
    }
    assert await prefs.global_get("umop_config_routing") is None
    assert await prefs.session_get(UMO, "config_overrides") is None
    await acm.ucr.update_routing_data({UMO: "exact", "test::*": "broad"})
    assert acm.get_conf(UMO)["kb_names"] == ["Exact"]
    assert acm.get_conf(UMO)["provider_settings"]["enable"] is False
    await acm.ucr.initialize()
    assert list(acm.ucr.umop_to_conf_id) == [UMO, "test::*"]
    await acm.ucr.delete_route(UMO)
    await acm.ucr.initialize()
    assert acm.get_conf_info(UMO)["id"] == "broad"


@pytest.mark.asyncio
async def test_profile_binding_follow_explicit_default_and_patch_survival(override_environment, tmp_path):
    from astrbot.core.config_bindings import BINDING_KEY

    prefs, acm, db = override_environment
    acm.abconf_data = {"B": {"name": "B", "path": "B.json"}}
    acm.confs["B"] = AstrBotConfig(str(tmp_path / "B.json"), deepcopy(DEFAULT_CONFIG))
    acm.confs["B"]["kb_names"] = ["Shared"]
    await acm.ucr.update_route("test::*", "B")
    service = service_module.SessionManagementService(SimpleNamespace(astrbot_config_mgr=acm), db)
    response = await service.update_session_rule({
        "umo": UMO, "rule_key": overrides.OVERRIDE_KEY,
        "profile_id": "default", "rule_value": {"provider_settings.enable": False},
    })
    assert response["profile_id"] == "default"
    assert response["profile"]["id"] == "default"
    assert response["routing_profile"]["id"] == "B"
    assert acm.get_conf_info(UMO)["id"] == "default"
    preview = await service.get_session_overrides(UMO, "")
    assert preview["profile"]["id"] == "B"
    assert preview["inherited"]["kb_names"] == ["Shared"]
    assert acm.get_conf_info(UMO)["id"] == "default"
    await service.update_session_rule({
        "umo": UMO, "rule_key": overrides.OVERRIDE_KEY,
        "profile_id": None, "rule_value": {},
    })
    assert acm.get_conf_info(UMO)["id"] == "B"
    assert acm.get_conf(UMO)["provider_settings"]["enable"] is False
    with pytest.raises(service_module.SessionManagementServiceError):
        await service.update_session_rule({
            "umo": UMO, "rule_key": overrides.OVERRIDE_KEY,
            "profile_id": "missing", "rule_value": {"kb_names": []},
        })
    assert "kb_names" not in await overrides.get_overrides(UMO)
    await overrides.update_overrides(UMO, {}, profile_id="B", update_profile=True)
    await service.delete_session_rule({"umo": UMO})
    assert await prefs.session_get(UMO, BINDING_KEY) == {"profile_id": "B", "overrides": {}}
    await overrides.update_overrides(UMO, {}, profile_id=None, update_profile=True)
    assert await prefs.session_get(UMO, BINDING_KEY) is None


@pytest.mark.asyncio
async def test_concurrent_profile_and_command_updates_preserve_binding(override_environment):
    from astrbot.core.config_bindings import BINDING_KEY

    prefs, _, _ = override_environment
    await asyncio.gather(
        overrides.update_overrides(UMO, {}, profile_id="default", update_profile=True),
        overrides.update_overrides(UMO, {"agent.config.model.provider_id": "C"}),
        overrides.update_overrides(UMO, {"provider_tts_settings.enable": False}),
    )
    assert await prefs.session_get(UMO, BINDING_KEY) == {
        "profile_id": "default", "overrides": {
            "agent.config.model.provider_id": "C", "provider_tts_settings.enable": False,
        },
    }


@pytest.mark.asyncio
async def test_partial_migration_retry_keeps_existing_binding_and_groups(override_environment):
    from astrbot.core.config_bindings import BINDING_KEY

    prefs, acm, _ = override_environment
    await prefs.global_put("umop_config_routing", {"test::*": "old"})
    await prefs.put_async("umop", "test::*", BINDING_KEY, {
        "profile_id": "new", "overrides": {}, "order": 0,
    })
    await prefs.session_put(UMO, "config_overrides", {
        "provider_settings.enable": False, "kb_names": ["Legacy"],
    })
    await overrides.update_overrides(UMO, {"provider_settings.enable": True},
                                     profile_id="default", update_profile=True)
    groups = {"work": {"name": "Work", "umos": [UMO]}}
    await prefs.put_async("unknown", "unknown", "session_groups", groups)
    await acm.ucr.initialize()
    await acm.ucr.initialize()
    assert acm.ucr.umop_to_conf_id == {"test::*": "new"}
    assert await prefs.session_get(UMO, BINDING_KEY) == {
        "profile_id": "default",
        "overrides": {"provider_settings.enable": True, "kb_names": ["Legacy"]},
    }
    assert await prefs.get_async("unknown", "unknown", "session_groups") == groups


@pytest.mark.asyncio
async def test_routing_updates_are_atomic_and_concurrent_routes_survive(override_environment):
    from sqlalchemy import event

    from astrbot.core.config_bindings import BINDING_KEY
    from astrbot.core.db.po import Preference

    prefs, acm, _ = override_environment
    await acm.ucr.update_route("test::*", "default")

    def fail_insert(mapper, connection, target):
        if target.scope == "umop" and target.scope_id == "new::*":
            raise RuntimeError("Injected route write failure")

    event.listen(Preference, "before_insert", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="Injected"):
            await acm.ucr.update_routing_data({"new::*": "default"})
    finally:
        event.remove(Preference, "before_insert", fail_insert)
    assert acm.ucr.umop_to_conf_id == {"test::*": "default"}
    assert await prefs.get_async("umop", "new::*", BINDING_KEY) is None
    assert (await prefs.get_async("umop", "test::*", BINDING_KEY))["profile_id"] == "default"
    await acm.ucr.initialize()
    assert acm.ucr.umop_to_conf_id == {"test::*": "default"}
    await asyncio.gather(
        acm.ucr.update_route("first::*", "default"),
        acm.ucr.update_route("second::*", "default"),
    )
    await acm.ucr.initialize()
    assert set(acm.ucr.umop_to_conf_id) == {"test::*", "first::*", "second::*"}


@pytest.mark.asyncio
async def test_mapping_list_includes_base_only_and_following_sessions(override_environment):
    prefs, acm, db = override_environment
    service = service_module.SessionManagementService(
        SimpleNamespace(astrbot_config_mgr=acm, provider_manager=SimpleNamespace()), db
    )
    await overrides.update_overrides(UMO, {}, profile_id="default", update_profile=True)
    following = "test:GroupMessage:following"
    await overrides.update_overrides(following, {"provider_settings.enable": False})
    await db.upsert_umo_alias(UMO, "owner", None, "Project chat")
    result = await service.list_session_rules(page=1, page_size=100, search="")
    rows = {row["umo"]: row for row in result["rules"]}
    assert result["total"] == 2
    assert rows[UMO]["profile_id"] == "default"
    assert rows[UMO]["rules"] == {"config_overrides": {}}
    assert rows[UMO]["display_name"] == "Project chat"
    assert rows[following]["profile_id"] is None
    assert rows[following]["rules"]["config_overrides"]["provider_settings.enable"] is False
    result = await service.list_session_rules(page=1, page_size=100, search="Project")
    assert [row["umo"] for row in result["rules"]] == [UMO]


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
async def test_remove_mapping_preserves_unrelated_session_data(override_environment, batch):
    from astrbot.core.config_bindings import BINDING_KEY

    prefs, acm, db = override_environment
    service = service_module.SessionManagementService(SimpleNamespace(astrbot_config_mgr=acm), db)
    await overrides.update_overrides(UMO, {"provider_settings.enable": False},
                                     profile_id="default", update_profile=True)
    await prefs.session_put(UMO, "session_variables", {"keep": True})
    groups = {"work": {"name": "Work", "umos": [UMO]}}
    await prefs.put_async("unknown", "unknown", "session_groups", groups)
    await db.upsert_umo_alias(UMO, "owner", None, "Work chat")
    target = {"umos": [UMO]} if batch else {"umo": UMO}
    await service.delete_session_rules({**target, "rule_key": BINDING_KEY})
    assert await prefs.session_get(UMO, BINDING_KEY) is None
    assert await prefs.session_get(UMO, "session_variables") == {"keep": True}
    assert await prefs.get_async("unknown", "unknown", "session_groups") == groups
    assert (await db.get_umo_aliases([UMO]))[0].user_alias == "Work chat"


@pytest.mark.asyncio
async def test_legacy_exact_route_is_listed_once_and_replaced_on_profile_edit(
    override_environment, tmp_path
):
    from astrbot.core.config_bindings import BINDING_KEY

    prefs, acm, db = override_environment
    acm.abconf_data = {"B": {"name": "B", "path": "B.json"}}
    acm.confs["B"] = AstrBotConfig(str(tmp_path / "B.json"), deepcopy(DEFAULT_CONFIG))
    service = service_module.SessionManagementService(
        SimpleNamespace(astrbot_config_mgr=acm, provider_manager=SimpleNamespace()), db
    )
    await acm.ucr.update_routing_data({"test:*:*": "default", UMO: "B"})
    await overrides.update_overrides(UMO, {"provider_settings.enable": False})
    await db.upsert_umo_alias(UMO, "owner", None, "Legacy chat")
    result = await service.list_session_rules(page=1, page_size=100, search="")
    assert result["total"] == 1
    assert result["rules"][0]["display_name"] == "Legacy chat"
    assert result["rules"][0]["profile_id"] == "default"
    assert acm.ucr.umop_to_conf_id == {"test:*:*": "default", UMO: "B"}
    assert (await prefs.session_get(UMO, BINDING_KEY))["profile_id"] is None

    await service.update_session_rule({
        "umo": UMO, "rule_key": "config_overrides", "rule_value": {"kb_names": []}
    })
    assert UMO in acm.ucr.umop_to_conf_id
    await service.update_session_rule({
        "umo": UMO, "rule_key": "config_overrides", "rule_value": {}, "profile_id": "B"
    })
    assert acm.get_conf_info(UMO)["id"] == "B"
    assert acm.ucr.umop_to_conf_id == {"test:*:*": "default"}
    assert await prefs.session_get(UMO, BINDING_KEY) == {
        "profile_id": "B", "overrides": {"provider_settings.enable": False, "kb_names": []}
    }
    result = await service.list_session_rules(page=1, page_size=100, search="")
    assert result["total"] == 1
    assert result["rules"][0]["profile_id"] == "B"
    await service.update_session_rule({
        "umo": UMO, "rule_key": "config_overrides", "rule_value": {}, "profile_id": None
    })
    assert acm.get_conf_info(UMO)["id"] == "default"
    assert await overrides.get_overrides(UMO) == {"provider_settings.enable": False, "kb_names": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
async def test_delete_legacy_exact_mapping_keeps_bot_route(override_environment, batch):
    prefs, acm, db = override_environment
    service = service_module.SessionManagementService(
        SimpleNamespace(astrbot_config_mgr=acm, provider_manager=SimpleNamespace()), db
    )
    await acm.ucr.update_routing_data({UMO: "default", "test:*:*": "default"})
    await prefs.session_put(UMO, "session_variables", {"keep": True})
    result = await service.list_session_rules(page=1, page_size=100, search="")
    assert result["total"] == 1
    assert result["rules"][0]["umo"] == UMO
    target = {"umos": [UMO]} if batch else {"umo": UMO}
    await service.delete_session_rules({**target, "rule_key": "config_binding"})
    assert acm.ucr.umop_to_conf_id == {"test:*:*": "default"}
    assert await prefs.session_get(UMO, "session_variables") == {"keep": True}
    result = await service.list_session_rules(page=1, page_size=100, search="")
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_wake_prefix_overrides_are_session_scoped_and_restore(
    override_environment, monkeypatch
):
    """Apply prefix edits immediately without changing other sessions or mentions."""
    from astrbot.core.message.components import At, Plain
    from astrbot.core.pipeline.waking_check.stage import WakingCheckStage

    _, acm, _ = override_environment
    stage = WakingCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=acm.default_conf,
            astrbot_config_id="default",
            db_helper=MagicMock(),
            plugin_manager=SimpleNamespace(
                context=SimpleNamespace(get_config=acm.get_conf)
            ),
        )
    )
    stage._umo_auto_name_recorder = MagicMock()
    monkeypatch.setattr(
        "astrbot.core.pipeline.waking_check.stage.star_handlers_registry.get_handlers_by_event_type",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr("astrbot.core.pipeline.waking_check.stage.FILTERS", [])
    other_umo = "test:GroupMessage:other"
    scenarios = [
        (["!", "小助手"], UMO, "!hello", False, True, "hello"),
        (["!", "小助手"], UMO, "小助手 hello", False, True, "hello"),
        (["!"], UMO, "/hello", False, False, "/hello"),
        (["!"], other_umo, "/hello", False, True, "hello"),
        (["!"], other_umo, "!hello", False, False, "!hello"),
        ([], UMO, "/hello", False, False, "/hello"),
        ([], UMO, "hello", True, True, "hello"),
        (None, UMO, "/hello", False, True, "hello"),
    ]
    for prefixes, umo, message, mention, expected_wake, expected_text in scenarios:
        await overrides.update_overrides(UMO, {"wake_prefix": prefixes})
        event = MagicMock()
        event.unified_msg_origin = umo
        event.message_str = message
        event.is_wake = False
        event.get_button_interaction.return_value = None
        event.is_button_interaction.return_value = False
        event.is_private_chat.return_value = False
        event.get_platform_name.return_value = "test"
        event.get_self_id.return_value = "bot"
        event.get_messages.return_value = (
            [At(qq="bot"), Plain(message)] if mention else [Plain(message)]
        )
        event.get_extra.side_effect = lambda key=None, default=None: default
        await stage.process(event)
        assert event.is_wake is expected_wake
        assert event.message_str == expected_text
        assert event.stop_event.called is not expected_wake
        assert acm.default_conf["wake_prefix"] == ["/"]
    assert "wake_prefix" not in await overrides.get_overrides(UMO)
    with pytest.raises(ValueError):
        await overrides.update_overrides(UMO, {"wake_prefix": [42]})


@pytest.mark.asyncio
async def test_ai_prefix_normalization_uses_each_sessions_wake_prefix(
    override_environment, monkeypatch
):
    """Normalize additional AI prefixes per event rather than caching a profile value."""
    from astrbot.core.pipeline.process_stage.method.agent_request import (
        AgentRequestSubStage,
        InternalAgentSubStage,
    )

    _, acm, _ = override_environment
    acm.default_conf["provider_settings"]["wake_prefix"] = "!ask"
    monkeypatch.setattr(InternalAgentSubStage, "initialize", AsyncMock())
    stage = AgentRequestSubStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=acm.default_conf,
            agent_runtimes={"astrbot": object()},
            plugin_manager=SimpleNamespace(
                context=SimpleNamespace(get_config=acm.get_conf)
            ),
        )
    )

    async def capture_prefix(event, prefix):
        """Return the prefix passed to the runtime.

        Args:
            event: Incoming message event.
            prefix: Resolved additional AI wake prefix.

        Yields:
            The prefix received by the runtime.
        """
        yield prefix

    stage.agent_sub_stage = SimpleNamespace(process=capture_prefix)
    await overrides.update_overrides(UMO, {"wake_prefix": ["!"]})
    event = MagicMock()
    for umo, expected in [(UMO, "ask"), ("test:GroupMessage:other", "!ask")]:
        event.unified_msg_origin = umo
        assert [value async for value in stage.process(event)] == [expected]
    await overrides.update_overrides(UMO, {"wake_prefix": None})
    event.unified_msg_origin = UMO
    assert [value async for value in stage.process(event)] == ["!ask"]
