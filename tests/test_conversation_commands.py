import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageEventResult
from astrbot.builtin_stars.builtin_commands.commands import (
    conversation as conversation_module,
)


class FakeCompactEvent:
    """Minimal event implementation for manual compression command tests."""

    def __init__(
        self,
        *,
        group_id: str = "",
        role: str = "member",
        platform_name: str = "webchat",
        extras: dict | None = None,
        fail_stats_send: bool = False,
        stopped: bool = False,
    ) -> None:
        self.unified_msg_origin = "webchat:private:test"
        self.role = role
        self.group_id = group_id
        self.platform_name = platform_name
        self.extras = extras or {}
        self.fail_stats_send = fail_stats_send
        self.stopped = stopped
        self.result = None
        self.sent = []

    def get_group_id(self) -> str:
        return self.group_id

    def get_platform_name(self) -> str:
        return self.platform_name

    def get_extra(self, key: str, default=None):
        return self.extras.get(key, default)

    def is_stopped(self) -> bool:
        return self.stopped

    def plain_result(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)

    def set_result(self, result: MessageEventResult) -> None:
        self.result = result

    async def send(self, chain) -> None:
        self.sent.append(chain)
        if self.fail_stats_send and chain.type == "agent_stats":
            raise RuntimeError("stats transport failed")


class FakeCompressionProvider:
    """Compression provider returning a configurable summary."""

    def __init__(
        self,
        summary: str = "Concise summary.",
        *,
        fail: bool = False,
    ) -> None:
        self.provider_config = {}
        self.summary = summary
        self.fail = fail
        self.call_count = 0

    async def text_chat(self, **kwargs):
        _ = kwargs
        self.call_count += 1
        if self.fail:
            raise RuntimeError("summary provider failed")
        return SimpleNamespace(completion_text=self.summary)


def _compact_history() -> list[dict]:
    """Build two complete rounds with a checkpoint on the latest round."""
    return [
        {"role": "user", "content": "old question " * 120},
        {"role": "assistant", "content": "old answer " * 120},
        {"role": "_checkpoint", "content": {"id": "cp-old"}},
        {"role": "user", "content": "latest question"},
        {"role": "assistant", "content": "latest answer"},
        {"role": "_checkpoint", "content": {"id": "cp-latest"}},
    ]


def _compact_context(
    history: list[dict],
    *,
    settings: dict | None = None,
    unique_session: bool = False,
):
    """Create a command context and mocked conversation manager.

    Args:
        history: Persisted conversation history.
        settings: Provider setting overrides.
        unique_session: Whether group conversations are isolated by member.

    Returns:
        The fake command context and its conversation manager.
    """
    provider_settings = {
        "enable": True,
        "enable_manual_context_compression": True,
        "agent_runner_type": "local",
        "context_limit_reached_strategy": "llm_compress",
        "llm_compress_keep_recent_ratio": 0.15,
    }
    provider_settings.update(settings or {})
    conversation = SimpleNamespace(history=json.dumps(history))
    manager = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="cid-1"),
        get_conversation=AsyncMock(return_value=conversation),
        update_conversation=AsyncMock(),
    )
    context = SimpleNamespace(
        conversation_manager=manager,
        get_config=lambda **kwargs: {
            "provider_settings": provider_settings,
            "platform_settings": {"unique_session": unique_session},
        },
    )
    return context, manager


def _result_text(event: FakeCompactEvent) -> str:
    """Return the plain-text command result."""
    assert event.result is not None
    return event.result.get_plain_text()


@pytest.mark.asyncio
async def test_clear_third_party_agent_runner_state_deletes_deerflow_thread_before_local_state(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[object] = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        async def delete_thread(self, thread_id: str, timeout: float = 20):
            calls.append(("delete", thread_id, timeout))

        async def close(self):
            calls.append(("close",))

    async def fake_get_async(*args, **kwargs):
        _ = args, kwargs
        return "thread-123"

    async def fake_remove_async(*args, **kwargs):
        calls.append(("remove", kwargs["scope"], kwargs["scope_id"], kwargs["key"]))

    context = SimpleNamespace(
        get_config=lambda **kwargs: {
            "agent_runner": {
                "runner_type": "deerflow",
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

    assert ("delete", "thread-123", 20) in calls
    assert (
        "remove",
        "umo",
        "umo-1",
        conversation_module.DEERFLOW_THREAD_ID_KEY,
    ) in calls
    assert calls.index(("delete", "thread-123", 20)) < calls.index(
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

        async def delete_thread(self, thread_id: str, timeout: float = 20):
            _ = thread_id, timeout
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
            "agent_runner": {
                "runner_type": "deerflow",
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
            "agent_runner": {
                "runner_type": "deerflow",
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
    ("settings", "group_id", "role", "unique_session", "expected"),
    [
        ({"enable": False}, "", "member", False, "AI features are disabled"),
        ({"enable_manual_context_compression": False}, "", "member", False, "disabled"),
        ({"agent_runner_type": "dify"}, "", "member", False, "local agent"),
        (
            {"context_limit_reached_strategy": "truncate_by_turns"},
            "",
            "member",
            False,
            "LLM context compression strategy",
        ),
        ({}, "group-1", "member", False, "admin permission"),
        ({}, "", "member", False, "No LLM provider"),
        ({}, "group-1", "member", True, "No LLM provider"),
    ],
)
async def test_compact_rejects_unsupported_configuration_and_shared_group_members(
    monkeypatch: pytest.MonkeyPatch,
    settings: dict,
    group_id: str,
    role: str,
    unique_session: bool,
    expected: str,
):
    context, manager = _compact_context(
        _compact_history(),
        settings=settings,
        unique_session=unique_session,
    )
    event = FakeCompactEvent(group_id=group_id, role=role)
    provider_resolver = AsyncMock(return_value=None)

    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        provider_resolver,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    assert expected in _result_text(event)
    manager.update_conversation.assert_not_awaited()
    assert event.sent == []
    if expected != "No LLM provider":
        provider_resolver.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform_name", "sent_types"),
    [("webchat", ["webchat_ephemeral", "agent_stats"]), ("telegram", [None])],
)
async def test_compact_writes_reduced_checkpoint_history_and_expected_stats(
    monkeypatch: pytest.MonkeyPatch,
    platform_name: str,
    sent_types: list[str | None],
):
    history = _compact_history()
    context, manager = _compact_context(history)
    event = FakeCompactEvent(platform_name=platform_name)
    provider = FakeCompressionProvider()

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_awaited_once()
    update_call = manager.update_conversation.await_args
    assert update_call.args == (event.unified_msg_origin, "cid-1")
    saved_history = update_call.kwargs["history"]
    assert update_call.kwargs["token_usage"] == 0
    assert {"role": "_checkpoint", "content": {"id": "cp-latest"}} in saved_history
    assert {"role": "_checkpoint", "content": {"id": "cp-old"}} not in saved_history
    assert provider.call_count == 1
    assert [chain.type for chain in event.sent] == sent_types
    assert event.sent[0].get_plain_text() == "⏳ Compressing context..."
    if platform_name == "webchat":
        assert event.sent[1].chain[0].data["current_context_tokens"] > 0
    assert _result_text(event) == "✅ Context compressed."


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_failure", [False, True])
async def test_compact_does_not_write_when_summary_fails_or_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    provider_failure: bool,
):
    history = _compact_history()
    context, manager = _compact_context(history)
    event = FakeCompactEvent()
    provider = FakeCompressionProvider(summary="", fail=provider_failure)

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_not_awaited()
    assert "original context was preserved" in _result_text(event)
    assert [chain.type for chain in event.sent] == ["webchat_ephemeral"]


@pytest.mark.asyncio
async def test_compact_reports_single_complete_round_as_not_enough_history(
    monkeypatch: pytest.MonkeyPatch,
):
    history = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
        {"role": "_checkpoint", "content": {"id": "cp-latest"}},
    ]
    context, manager = _compact_context(history)
    event = FakeCompactEvent()
    provider = FakeCompressionProvider()

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_not_awaited()
    assert provider.call_count == 0
    assert "not enough conversation history" in _result_text(event)


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["cid", "history"])
async def test_compact_does_not_write_when_conversation_changes(
    monkeypatch: pytest.MonkeyPatch,
    conflict: str,
):
    history = _compact_history()
    context, manager = _compact_context(history)
    event = FakeCompactEvent()
    provider = FakeCompressionProvider()

    if conflict == "cid":
        manager.get_curr_conversation_id.side_effect = ["cid-1", "cid-1", "cid-2"]
    else:
        changed = SimpleNamespace(
            history=json.dumps([*history, {"role": "user", "content": "new"}])
        )
        manager.get_conversation.side_effect = [
            SimpleNamespace(history=json.dumps(history)),
            changed,
        ]

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_not_awaited()
    assert "changed during compression" in _result_text(event)


@pytest.mark.asyncio
async def test_compact_checks_force_stop_after_final_history_read(
    monkeypatch: pytest.MonkeyPatch,
):
    history = _compact_history()
    context, manager = _compact_context(history)
    event = FakeCompactEvent()
    provider = FakeCompressionProvider()
    read_count = 0

    async def get_conversation(*args, **kwargs):
        nonlocal read_count
        _ = args, kwargs
        read_count += 1
        if read_count == 2:
            event.stopped = True
        return SimpleNamespace(history=json.dumps(history))

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    manager.get_conversation.side_effect = get_conversation
    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_not_awaited()
    assert read_count == 2
    assert event.result is None


@pytest.mark.asyncio
async def test_compact_does_not_write_after_stop_request(
    monkeypatch: pytest.MonkeyPatch,
):
    context, manager = _compact_context(_compact_history())
    event = FakeCompactEvent(extras={"agent_stop_requested": True})
    provider = FakeCompressionProvider()

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_not_awaited()
    assert provider.call_count == 0
    assert "cancelled" in _result_text(event)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_during_summary", [False, True])
async def test_compact_force_stop_returns_without_setting_a_result(
    monkeypatch: pytest.MonkeyPatch,
    stop_during_summary: bool,
):
    context, manager = _compact_context(_compact_history())
    event = FakeCompactEvent(stopped=not stop_during_summary)
    provider = FakeCompressionProvider()

    if stop_during_summary:

        async def stop_event_during_summary(**kwargs):
            _ = kwargs
            event.stopped = True
            return SimpleNamespace(completion_text="Concise summary.")

        provider.text_chat = stop_event_during_summary

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_not_awaited()
    assert event.result is None
    assert [chain.type for chain in event.sent] == ["webchat_ephemeral"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("verification_state", "expected"),
    [
        ("target", "Context compressed"),
        ("original", "original context was preserved"),
        ("other", "Context state is unknown"),
        ("error", "Context state is unknown"),
    ],
)
async def test_compact_verifies_history_after_storage_update_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    verification_state: str,
    expected: str,
):
    history = _compact_history()
    context, manager = _compact_context(history)
    event = FakeCompactEvent()
    provider = FakeCompressionProvider()
    stored_history = json.dumps(history)
    read_count = 0

    async def get_conversation(*args, **kwargs):
        nonlocal read_count
        _ = args, kwargs
        read_count += 1
        if verification_state == "error" and read_count == 3:
            raise RuntimeError("secret-history verification failure")
        return SimpleNamespace(history=stored_history)

    async def update_conversation(*args, history, **kwargs):
        nonlocal stored_history
        _ = args, kwargs
        if verification_state == "target":
            stored_history = json.dumps(history)
        elif verification_state == "other":
            stored_history = json.dumps(
                [{"role": "user", "content": "concurrent update"}]
            )
        raise RuntimeError("secret-history internal readback failure")

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    manager.get_conversation.side_effect = get_conversation
    manager.update_conversation.side_effect = update_conversation
    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_awaited_once()
    assert expected in _result_text(event)
    if verification_state == "target":
        assert [chain.type for chain in event.sent] == [
            "webchat_ephemeral",
            "agent_stats",
        ]
    else:
        assert [chain.type for chain in event.sent] == ["webchat_ephemeral"]
    assert "secret-history" not in caplog.text
    assert "Traceback" not in caplog.text
    assert event.unified_msg_origin not in caplog.text


@pytest.mark.asyncio
async def test_compact_pre_update_error_log_does_not_expose_history(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    context, manager = _compact_context(_compact_history())
    manager.get_conversation.return_value = SimpleNamespace(
        history='{"secret-history": invalid}'
    )
    event = FakeCompactEvent()
    provider = FakeCompressionProvider()

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_not_awaited()
    assert "original context was preserved" in _result_text(event)
    assert "secret-history" not in caplog.text
    assert "Traceback" not in caplog.text
    assert event.unified_msg_origin not in caplog.text


@pytest.mark.asyncio
async def test_compact_stats_failure_does_not_change_success_result(
    monkeypatch: pytest.MonkeyPatch,
):
    context, manager = _compact_context(_compact_history())
    event = FakeCompactEvent(fail_stats_send=True)
    provider = FakeCompressionProvider()

    async def get_provider(*args, **kwargs):
        _ = args, kwargs
        return provider

    monkeypatch.setattr(
        conversation_module,
        "get_context_compression_provider",
        get_provider,
    )

    await conversation_module.ConversationCommands(context).compact(event)

    manager.update_conversation.assert_awaited_once()
    assert [chain.type for chain in event.sent] == [
        "webchat_ephemeral",
        "agent_stats",
    ]
    assert _result_text(event) == "✅ Context compressed."
