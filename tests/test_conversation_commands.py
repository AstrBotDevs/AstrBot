from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.builtin_stars.builtin_commands.commands import (
    conversation as conversation_module,
)


@pytest.mark.asyncio
async def test_clear_third_party_agent_runner_state_deletes_deerflow_thread_before_local_state(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[object] = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        async def delete_thread(self, thread_id: str):
            calls.append(("delete", thread_id))

        async def close(self):
            calls.append(("close",))

    async def fake_get_async(*args, **kwargs):
        _ = args, kwargs
        return "thread-123"

    async def fake_remove_async(*args, **kwargs):
        calls.append(("remove", kwargs["scope"], kwargs["scope_id"], kwargs["key"]))

    context = SimpleNamespace(
        get_config=lambda **kwargs: {
            "agent": {
                "runtime": "deerflow",
                "config": {
                    "deerflow_api_base": "http://127.0.0.1:2026",
                    "deerflow_api_key": "token",
                    "deerflow_auth_header": "",
                    "proxy": "",
                },
            }
        },
    )

    monkeypatch.setattr(conversation_module, "DeerFlowAPIClient", FakeClient)
    monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)
    monkeypatch.setattr(conversation_module.sp, "remove_async", fake_remove_async)

    await conversation_module._clear_third_party_agent_runner_state(
        context,
        "umo-1",
        conversation_module.DEERFLOW_PROVIDER_TYPE,
    )

    assert ("delete", "thread-123") in calls
    assert (
        "remove",
        "umo",
        "umo-1",
        conversation_module.DEERFLOW_THREAD_ID_KEY,
    ) in calls
    assert calls.index(("delete", "thread-123")) < calls.index(
        ("remove", "umo", "umo-1", conversation_module.DEERFLOW_THREAD_ID_KEY)
    )


@pytest.mark.asyncio
async def test_clear_third_party_agent_runner_state_removes_local_state_when_deerflow_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[object] = []

    class FakeClient:
        def __init__(self, **kwargs):
            _ = kwargs

        async def delete_thread(self, thread_id: str):
            _ = thread_id
            raise RuntimeError("gateway down")

        async def close(self):
            calls.append(("close",))

    async def fake_get_async(*args, **kwargs):
        _ = args, kwargs
        return "thread-456"

    async def fake_remove_async(*args, **kwargs):
        calls.append(("remove", kwargs["scope"], kwargs["scope_id"], kwargs["key"]))

    context = SimpleNamespace(
        get_config=lambda **kwargs: {
            "agent": {
                "runtime": "deerflow",
                "config": {
                    "deerflow_api_base": "http://127.0.0.1:2026",
                    "deerflow_api_key": "",
                    "deerflow_auth_header": "",
                    "proxy": "",
                },
            }
        },
    )

    monkeypatch.setattr(conversation_module, "DeerFlowAPIClient", FakeClient)
    monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)
    monkeypatch.setattr(conversation_module.sp, "remove_async", fake_remove_async)

    await conversation_module._clear_third_party_agent_runner_state(
        context,
        "umo-2",
        conversation_module.DEERFLOW_PROVIDER_TYPE,
    )

    assert (
        "remove",
        "umo",
        "umo-2",
        conversation_module.DEERFLOW_THREAD_ID_KEY,
    ) in calls


@pytest.mark.asyncio
async def test_clear_third_party_agent_runner_state_removes_local_state_when_deerflow_client_init_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[object] = []

    class FakeClient:
        def __init__(self, **kwargs):
            _ = kwargs
            raise RuntimeError("invalid deerflow config")

    async def fake_get_async(*args, **kwargs):
        _ = args, kwargs
        return "thread-789"

    async def fake_remove_async(*args, **kwargs):
        calls.append(("remove", kwargs["scope"], kwargs["scope_id"], kwargs["key"]))

    context = SimpleNamespace(
        get_config=lambda **kwargs: {
            "agent": {
                "runtime": "deerflow",
                "config": {
                    "deerflow_api_base": "http://127.0.0.1:2026",
                    "deerflow_api_key": "",
                    "deerflow_auth_header": "",
                    "proxy": "",
                },
            }
        },
    )

    monkeypatch.setattr(conversation_module, "DeerFlowAPIClient", FakeClient)
    monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)
    monkeypatch.setattr(conversation_module.sp, "remove_async", fake_remove_async)

    await conversation_module._clear_third_party_agent_runner_state(
        context,
        "umo-3",
        conversation_module.DEERFLOW_PROVIDER_TYPE,
    )

    assert (
        "remove",
        "umo",
        "umo-3",
        conversation_module.DEERFLOW_THREAD_ID_KEY,
    ) in calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime", "key"),
    [
        ("dify", "dify_conversation_id"),
        ("coze", "coze_conversation_id"),
        ("dashscope", "dashscope_conversation_id"),
    ],
)
async def test_external_runtime_cleanup_only_removes_the_selected_session_key(
    shared_preferences, monkeypatch, runtime, key
):
    target = "bot:FriendMessage:alice"
    other = "bot:FriendMessage:bob"
    await shared_preferences.session_put(target, key, "target-thread")
    await shared_preferences.session_put(other, key, "other-thread")
    await shared_preferences.session_put(target, "sel_conv_id", "local-conversation")
    monkeypatch.setattr(conversation_module, "sp", shared_preferences)
    context = SimpleNamespace(get_config=Mock())

    await conversation_module._clear_third_party_agent_runner_state(
        context, target, runtime
    )

    assert await shared_preferences.session_get(target, key) is None
    assert await shared_preferences.session_get(other, key) == "other-thread"
    assert (
        await shared_preferences.session_get(target, "sel_conv_id")
        == "local-conversation"
    )
    context.get_config.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_runtime_leaves_all_session_state_intact(
    shared_preferences, monkeypatch
):
    umo = "bot:FriendMessage:alice"
    await shared_preferences.session_put(umo, "dify_conversation_id", "keep")
    monkeypatch.setattr(conversation_module, "sp", shared_preferences)
    context = SimpleNamespace(get_config=Mock())

    await conversation_module._clear_third_party_agent_runner_state(
        context, umo, "unregistered-runtime"
    )

    assert await shared_preferences.session_get(umo, "dify_conversation_id") == "keep"
    context.get_config.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [None, "missing-conversation", "current"])
async def test_current_persona_lookup_handles_no_selection_missing_and_existing_conversations(
    selection,
):
    manager = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value=selection),
        get_conversation=AsyncMock(
            return_value=SimpleNamespace(persona_id="persona")
            if selection == "current"
            else None
        ),
    )
    commands = conversation_module.ConversationCommands(
        SimpleNamespace(conversation_manager=manager)
    )
    result = await commands._get_current_persona_id("bot:FriendMessage:alice")

    assert result == ("persona" if selection == "current" else None)
    manager.get_curr_conversation_id.assert_awaited_once_with("bot:FriendMessage:alice")
    if selection is None:
        manager.get_conversation.assert_not_awaited()
    else:
        manager.get_conversation.assert_awaited_once_with(
            "bot:FriendMessage:alice", selection
        )
