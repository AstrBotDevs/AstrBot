"""Plugin attribution and legacy mutation behavior for the linear journal."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.agent.conversation_events import (
    ConversationEventWriter,
)
from astrbot.core.astr_agent_runtime.history import ConversationHistoryObserver
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.conversation import ConversationConflictError
from astrbot.core.pipeline import context_utils
from astrbot.core.star.star_handler import EventType


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
                    handler_full_name="test.memory.mutate",
                    event_type=EventType.OnLLMRequestEvent,
                )
            ],
        )
        monkeypatch.setitem(
            context_utils.star_map,
            "test.memory",
            SimpleNamespace(name="memory", display_name=None),
        )

    return install


@pytest.mark.asyncio
async def test_hook_stages_nested_edits_without_mutating_committed_history(
    database, install_hook
):
    store = database.conversation_store
    history = [{"role": "user", "content": [{"type": "text", "text": "old"}]}]
    conv = await store.create(umo="umo", platform_id="p", content=history)
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    observer = ConversationHistoryObserver(writer)
    observer.request = SimpleNamespace(contexts=history, conversation=conv)
    event = SimpleNamespace(
        plugins_name=None, is_stopped=lambda: False, trace=MagicMock()
    )
    await writer.start_turn({"kind": "test"})

    async def edit(event, req):
        req.contexts[0]["content"][0]["text"] = "edited"

    install_hook(edit)
    await context_utils.call_event_hook(
        event, EventType.OnLLMRequestEvent, observer.request, context_observer=observer
    )
    history[0]["content"][0]["text"] = "later change"
    assert writer.get_messages()[0]["content"][0]["text"] == "edited"
    assert (await store.read(conv.conversation_id)).messages[0]["content"][0][
        "text"
    ] == "old"
    history[0]["content"][0]["text"] = "edited"
    await writer.save_history(history)
    edits = [
        entry.payload
        for entry in await store.events(conv.conversation_id)
        if entry.type == "context.rebased"
        and entry.payload
        and entry.payload.get("origin") == "plugin"
    ]
    assert len(edits) == 1
    assert edits[0]["messages"][0]["message"]["content"][0]["text"] == "edited"


@pytest.mark.asyncio
async def test_manager_writes_are_independent_of_execution_and_keep_unknown_origin(
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
    await manager.update_conversation("umo", conv.conversation_id, history=[])
    assert (await store.events(conv.conversation_id))[-1].payload["origin"] == "unknown"
    writer = await manager.create_event_writer(
        conv.conversation_id, unified_msg_origin="umo"
    )
    await writer.append_message({"role": "user", "content": "restore"})
    await manager.update_conversation("umo", conv.conversation_id, history=[])
    assert (await store.events(conv.conversation_id))[-1].payload["origin"] == "unknown"
    assert [entry["message"] for entry in writer._entries] == [
        {"role": "user", "content": "restore"}
    ]
    with pytest.raises(ConversationConflictError):
        await writer.save_history([{"role": "user", "content": "stale run"}])


@pytest.mark.asyncio
async def test_transcript_only_runner_does_not_clear_history_on_request_hook(
    database, install_hook
):
    store = database.conversation_store
    history = [{"role": "user", "content": "previous transcript"}]
    conv = await store.create(umo="umo", platform_id="p", content=history)
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    observer = ConversationHistoryObserver(writer)
    observer.request = SimpleNamespace(contexts=[], conversation=None)
    event = SimpleNamespace(
        plugins_name=None,
        is_stopped=lambda: False,
        trace=MagicMock(),
    )

    async def inject_remote_context(event, req):
        req.contexts = [{"role": "user", "content": "remote-only memory"}]

    install_hook(inject_remote_context)
    await context_utils.call_event_hook(
        event, EventType.OnLLMRequestEvent, observer.request, context_observer=observer
    )
    await writer.save_history([entry["message"] for entry in writer._entries])
    assert (await store.read(conv.conversation_id)).messages == history
