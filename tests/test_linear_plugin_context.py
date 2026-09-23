"""Plugin attribution and legacy mutation behavior for the linear journal."""

from types import SimpleNamespace

import pytest
import pytest_asyncio

from astrbot.core.agent.conversation_events import (
    ConversationEventWriter,
    active_conversation_writer,
    active_plugin_id,
)
from astrbot.core.agent.message import Message
from astrbot.core.agent.response import AgentResponse
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.pipeline import context_utils
from astrbot.core.star.star_handler import EventType
from astrbot.dashboard.services.conversation_service import ConversationService


@pytest_asyncio.fixture
async def database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "plugin-events.db"))
    await db.initialize()
    yield db
    await db.engine.dispose()


@pytest.fixture
def install_hook(monkeypatch):
    def install(handler):
        monkeypatch.setattr(
            context_utils.star_handlers_registry,
            "get_handlers_by_event_type",
            lambda *args, **kwargs: [
                SimpleNamespace(
                    handler=handler,
                    handler_module_path="test.memory",
                    handler_name="mutate",
                )
            ],
        )
        monkeypatch.setitem(
            context_utils.star_map, "test.memory", SimpleNamespace(name="memory")
        )

    return install


@pytest.mark.asyncio
async def test_iris_clear_is_plugin_reset_and_previous_body_is_reclaimed(
    database, install_hook
):
    store = database.conversation_store
    conv = await store.create(
        umo="umo", platform_id="p", content=[{"role": "user", "content": "old"}]
    )

    async def clear(event, req):
        req.contexts = []

    install_hook(clear)
    resets = []
    for index in range(2):
        snapshot = await store.read(conv.conversation_id)
        writer = ConversationEventWriter(store, snapshot)
        writer.request = SimpleNamespace(contexts=snapshot.messages, conversation=conv)
        event = SimpleNamespace(
            conversation_events=writer, plugins_name=None, is_stopped=lambda: False
        )
        await writer.start_turn({"kind": "test"})
        await context_utils.call_event_hook(
            event, EventType.OnLLMRequestEvent, writer.request
        )
        history = [
            {"role": "user", "content": "private memory", "_no_save": True},
            {"role": "user", "content": f"question {index}"},
            {"role": "assistant", "content": f"reply {index}"},
        ]
        await writer.save_history(history)
        pending_events = await store.events(conv.conversation_id)
        reset = next(
            e
            for e in pending_events
            if e.type == "context.rebased"
            and e.payload is not None
            and e.payload.get("turn_id") == writer.turn_id
        )
        assert reset.payload["origin"] == "plugin"
        assert reset.payload["reason"] == "reset"
        assert reset.payload["messages"] == []
        resets.append(reset.event_id)
        await writer.finish_turn("completed")
        assert (await store.read(conv.conversation_id)).messages == history[1:]

    events = {e.event_id: e for e in await store.events(conv.conversation_id)}
    assert events[resets[0]].payload is None
    assert events[resets[1]].payload is not None
    excluded = [
        e
        for e in events.values()
        if e.type == "message.appended" and e.payload.get("include_in_context") is False
    ]
    assert len(excluded) == 2
    assert all(e.payload["message"]["content"] == "private memory" for e in excluded)


@pytest.mark.asyncio
async def test_pre_hook_changes_stay_unknown_and_done_hook_changes_are_plugin(
    database, install_hook
):
    store = database.conversation_store
    conv = await store.create(
        umo="umo", platform_id="p", content=[{"role": "user", "content": "old"}]
    )
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    writer.runtime_context = SimpleNamespace(
        messages=[Message(role="user", content="custom runner changed history")]
    )
    event = SimpleNamespace(
        conversation_events=writer, plugins_name=None, is_stopped=lambda: False
    )

    async def edit_history(event, context):
        context.messages[0] = Message(role="user", content="plugin edited history")

    install_hook(edit_history)
    await writer.start_turn({"kind": "test"})
    await context_utils.call_event_hook(
        event, EventType.OnAgentDoneEvent, writer.runtime_context
    )
    await writer.save_history([{"role": "user", "content": "plugin edited history"}])
    await writer.finish_turn("completed")
    rebases = [
        e
        for e in await store.events(conv.conversation_id)
        if e.type == "context.rebased"
    ]
    assert any(
        e.payload
        and e.payload.get("origin") == "unknown"
        and e.payload["messages"][0]["message"]["content"]
        == "custom runner changed history"
        for e in rebases
    )
    assert any(e.payload and e.payload.get("origin") == "plugin" for e in rebases)


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["user", "system", "unknown"])
async def test_non_plugin_rebases_survive_later_plugin_replacements(database, origin):
    store = database.conversation_store
    conv = await store.create(
        umo="umo", platform_id="p", content=[{"role": "user", "content": "old"}]
    )
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await writer.save_history([{"role": "user", "content": origin}], origin=origin)
    protected_id = writer.leaf_event_id
    await writer.save_history(
        [{"role": "user", "content": "plugin 1"}], origin="plugin"
    )
    await writer.save_history(
        [{"role": "user", "content": "plugin 2"}], origin="plugin"
    )
    events = {e.event_id: e for e in await store.events(conv.conversation_id)}
    assert events[protected_id].payload["origin"] == origin


@pytest.mark.asyncio
async def test_manager_uses_invocation_identity_without_guessing_external_callers(
    database,
):
    store = database.conversation_store
    manager = ConversationManager(database)
    conv = await store.create(
        umo="umo", platform_id="p", content=[{"role": "user", "content": "old"}]
    )
    await manager.update_conversation(
        "umo", conv.conversation_id, history=[{"role": "user", "content": "external"}]
    )
    external = (await store.events(conv.conversation_id))[-1]
    assert external.payload["origin"] == "unknown"
    plugin_token = active_plugin_id.set("memory")
    try:
        await manager.update_conversation("umo", conv.conversation_id, history=[])
    finally:
        active_plugin_id.reset(plugin_token)
    assert (await store.events(conv.conversation_id))[-1].payload["origin"] == "plugin"
    writer = await manager.event_writer("umo", conv.conversation_id)
    writer_token = active_conversation_writer.set(writer)
    try:
        await writer.append_message({"role": "user", "content": "restore"})
        await manager.update_conversation("umo", conv.conversation_id, history=[])
    finally:
        active_conversation_writer.reset(writer_token)
    assert (await store.events(conv.conversation_id))[-1].payload["origin"] == "unknown"


@pytest.mark.asyncio
async def test_runner_context_source_is_explicit_and_linear_fork_is_independent(
    database,
):
    store = database.conversation_store
    manager = ConversationManager(database)
    conv = await store.create(
        umo="umo", platform_id="p", content=[{"role": "user", "content": "old"}]
    )
    writer = await manager.event_writer("umo", conv.conversation_id)
    await writer.consume(
        AgentResponse(
            "context.updated",
            {
                "messages": [{"role": "user", "content": "summary"}],
                "reason": "compaction",
                "origin": "system",
            },
        )
    )
    await writer.save_history([{"role": "user", "content": "summary"}])
    baseline = (await store.events(conv.conversation_id))[-1]
    assert baseline.payload["origin"] == "system"
    fork_id = await manager.fork_conversation("umo", baseline.event_id)
    await store.delete(cid=conv.conversation_id)
    assert (await store.read(fork_id)).messages == [
        {"role": "user", "content": "summary"}
    ]


@pytest.mark.asyncio
async def test_transcript_only_runner_does_not_clear_history_on_request_hook(
    database, install_hook
):
    store = database.conversation_store
    history = [{"role": "user", "content": "previous transcript"}]
    conv = await store.create(umo="umo", platform_id="p", content=history)
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    writer.request = SimpleNamespace(contexts=[], conversation=None)
    event = SimpleNamespace(
        conversation_events=writer, plugins_name=None, is_stopped=lambda: False
    )

    async def inject_remote_context(event, req):
        req.contexts = [{"role": "user", "content": "remote-only memory"}]

    install_hook(inject_remote_context)
    await context_utils.call_event_hook(
        event, EventType.OnLLMRequestEvent, writer.request
    )
    await writer.save_history([entry["message"] for entry in writer._entries])
    assert (await store.read(conv.conversation_id)).messages == history


@pytest.mark.asyncio
async def test_dashboard_history_edit_is_user_owned_and_survives_plugin_cleanup(
    database,
):
    store = database.conversation_store
    manager = ConversationManager(database)
    service = ConversationService(
        database, SimpleNamespace(conversation_manager=manager)
    )
    conv = await store.create(
        umo="umo", platform_id="p", content=[{"role": "user", "content": "old"}]
    )
    edited = [{"role": "user", "content": "manually edited"}]
    await service.update_history(
        {
            "user_id": "umo",
            "cid": conv.conversation_id,
            "history": edited,
        }
    )
    user_baseline = (await store.events(conv.conversation_id))[-1]
    assert user_baseline.type == "context.rebased"
    assert user_baseline.payload["origin"] == "user"
    writer = await manager.event_writer("umo", conv.conversation_id)
    await writer.save_history(
        [{"role": "user", "content": "memory 1"}], origin="plugin"
    )
    old_plugin_id = writer.leaf_event_id
    await writer.save_history(
        [{"role": "user", "content": "memory 2"}], origin="plugin"
    )
    events = {e.event_id: e for e in await store.events(conv.conversation_id)}
    assert events[old_plugin_id].payload is None
    assert events[user_baseline.event_id].payload == user_baseline.payload
    fork_id = await manager.fork_conversation("umo", user_baseline.event_id)
    assert (await store.read(fork_id)).messages == edited
