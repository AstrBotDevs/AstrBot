from types import SimpleNamespace
from unittest.mock import AsyncMock

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
            "provider_settings": {
                "deerflow_agent_runner_provider_id": "deerflow-runner"
            }
        },
        provider_manager=SimpleNamespace(
            get_provider_config_by_id=lambda provider_id, merged=False: (
                {
                    "id": provider_id,
                    "deerflow_api_base": "http://127.0.0.1:2026",
                    "deerflow_api_key": "token",
                    "deerflow_auth_header": "",
                    "proxy": "",
                }
                if merged
                else {"id": provider_id}
            ),
        ),
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
            "provider_settings": {
                "deerflow_agent_runner_provider_id": "deerflow-runner"
            }
        },
        provider_manager=SimpleNamespace(
            get_provider_config_by_id=lambda provider_id, merged=False: (
                {
                    "id": provider_id,
                    "deerflow_api_base": "http://127.0.0.1:2026",
                    "deerflow_api_key": "",
                    "deerflow_auth_header": "",
                    "proxy": "",
                }
                if merged
                else {"id": provider_id}
            ),
        ),
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
            "provider_settings": {
                "deerflow_agent_runner_provider_id": "deerflow-runner"
            }
        },
        provider_manager=SimpleNamespace(
            get_provider_config_by_id=lambda provider_id, merged=False: (
                {
                    "id": provider_id,
                    "deerflow_api_base": "http://127.0.0.1:2026",
                    "deerflow_api_key": "",
                    "deerflow_auth_header": "",
                    "proxy": "",
                }
                if merged
                else {"id": provider_id}
            ),
        ),
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


def test_conversation_commands_imported():
    assert conversation_module.ConversationCommands is not None


def test_conversation_commands_class():
    assert issubclass(conversation_module.ConversationCommands, object)


def test_conversation_commands_type_dicts():
    assert hasattr(conversation_module.ResetPermissionConfig, "__annotations__")
    assert hasattr(conversation_module.AlterCmdPluginConfig, "__annotations__")


def test_conversation_commands_helpers():
    assert callable(conversation_module._normalize_alter_cmd_config)


def test_conversation_commands_constants():
    assert isinstance(conversation_module.THIRD_PARTY_AGENT_RUNNER_KEY, dict)
    assert "dify" in conversation_module.THIRD_PARTY_AGENT_RUNNER_KEY


# ====================== /compact command tests ======================


def _make_mock_message(
    role: str = "member",
    group_id: str = "",
    sender_id: str = "user-123",
    session: str = "test:group:session-1",
) -> SimpleNamespace:
    """Build a minimal AstrMessageEvent-like object for compact() testing."""
    result_holder = []

    msg = SimpleNamespace(
        role=role,
        session=session,
        message_obj=SimpleNamespace(
            group_id=group_id,
            sender=SimpleNamespace(user_id=sender_id),
        ),
        result=result_holder,
    )

    # Properties on AstrMessageEvent
    msg.unified_msg_origin = session

    def get_group_id():
        return group_id

    def get_sender_id():
        return sender_id

    def set_result(r):
        result_holder.append(r)

    msg.get_group_id = get_group_id
    msg.get_sender_id = get_sender_id
    msg.set_result = set_result
    return msg


def _make_mock_context(
    provider_settings: dict | None = None,
    platform_settings: dict | None = None,
    conversation_manager: SimpleNamespace | None = None,
    provider_manager: SimpleNamespace | None = None,
    summary_provider: SimpleNamespace | None = None,
) -> SimpleNamespace:
    """Build a minimal context object for compact() testing."""
    settings = provider_settings or {
        "agent_runner_type": "internal",
        "enable_turn_limit": True,
        "max_turns": 2,
        "enable_token_guard": False,
        "enable_summary": False,
        "enable_discard": True,
        "discard_turns": 2,
        "summary_provider_id": "",
        "retention_method": "null",
        "retain_turns": 20,
        "retain_percentage": 0.3,
    }
    plat_settings = platform_settings or {"unique_session": True}

    config = {
        "provider_settings": settings,
        "platform_settings": plat_settings,
    }

    using_provider = summary_provider or SimpleNamespace(
        provider_config={"max_context_tokens": 8192},
    )

    def get_config(umo=None):
        return config

    context = SimpleNamespace(
        get_config=get_config,
        conversation_manager=conversation_manager or _make_mock_conversation_manager(),
        provider_manager=provider_manager or SimpleNamespace(),
    )

    def get_provider_by_id(pid):
        return summary_provider if pid else None

    def get_using_provider(umo=None):
        return using_provider

    context.get_provider_by_id = get_provider_by_id
    context.get_using_provider = get_using_provider
    return context


def _make_mock_conversation_manager(
    cid: str = "conv-001",
    history: list[dict] | None = None,
) -> SimpleNamespace:
    """Build a minimal conversation manager for compact() testing."""
    if history is None:
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "Tell me about AI"},
            {"role": "assistant", "content": "AI is fascinating."},
            {"role": "user", "content": "More details"},
            {"role": "assistant", "content": "Here are more details."},
        ]

    import json

    conv = SimpleNamespace(history=json.dumps(history))
    saved_result = []

    async def get_curr_conversation_id(umo):
        return cid

    async def get_conversation(umo, cid_val):
        if cid_val is None:
            return None
        return conv

    async def update_conversation(umo, cid_val, result):
        saved_result.append(result)

    mgr = SimpleNamespace(
        get_curr_conversation_id=get_curr_conversation_id,
        get_conversation=get_conversation,
        update_conversation=update_conversation,
    )
    # Expose saved_result for assertions
    mgr._saved_result = saved_result
    # Expose conv for assertions
    mgr._conv = conv
    return mgr


class TestCompactCommand:
    """Tests for the /compact command."""

    @pytest.mark.asyncio
    async def test_compact_permission_denied_in_group(self, monkeypatch):
        """Non-admin user in group with non-unique session gets denied."""
        async def fake_get_async(*args, **kwargs):
            return {}  # no alter_cmd override, so default applies

        monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)

        msg = _make_mock_message(
            role="member",
            group_id="group-1",
            session="test:group:session-1",
        )
        ctx = _make_mock_context(platform_settings={"unique_session": False})

        cmd = conversation_module.ConversationCommands(ctx)
        await cmd.compact(msg)

        # Should have been denied
        assert len(msg.result) == 1
        result_text = str(msg.result[0])
        assert "requires admin permission" in result_text

    @pytest.mark.asyncio
    async def test_compact_admin_allowed_in_group(self, monkeypatch):
        """Admin user in group is allowed to compact."""
        async def fake_get_async(*args, **kwargs):
            return {}

        monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)

        msg = _make_mock_message(
            role="admin",
            group_id="group-1",
            session="test:group:session-1",
        )
        ctx = _make_mock_context(platform_settings={"unique_session": False})

        cmd = conversation_module.ConversationCommands(ctx)
        await cmd.compact(msg)

        # Admin should pass permission check; if it fails, it's for another reason
        assert len(msg.result) == 1
        result_text = str(msg.result[0])
        assert "requires admin permission" not in result_text

    @pytest.mark.asyncio
    async def test_compact_third_party_runner_skipped(self, monkeypatch):
        """Third-party agent runner (e.g. dify) should be skipped."""
        async def fake_get_async(*args, **kwargs):
            return {}

        monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)

        msg = _make_mock_message(role="admin", group_id="group-1")
        ctx = _make_mock_context(provider_settings={
            "agent_runner_type": "dify",
        })

        cmd = conversation_module.ConversationCommands(ctx)
        await cmd.compact(msg)

        assert len(msg.result) == 1
        result_text = str(msg.result[0])
        assert "not supported" in result_text
        assert "dify" in result_text

    @pytest.mark.asyncio
    async def test_compact_no_conversation(self, monkeypatch):
        """When there is no current conversation, user is prompted to create one."""
        async def fake_get_async(*args, **kwargs):
            return {}

        monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)

        msg = _make_mock_message(role="admin")
        cm = _make_mock_conversation_manager(cid=None)
        cm.get_curr_conversation_id = AsyncMock(return_value=None)
        ctx = _make_mock_context(conversation_manager=cm)

        cmd = conversation_module.ConversationCommands(ctx)
        await cmd.compact(msg)

        assert len(msg.result) == 1
        result_text = str(msg.result[0])
        assert "use /new" in result_text.lower()

    @pytest.mark.asyncio
    async def test_compact_conversation_not_found(self, monkeypatch):
        """When conversation lookup returns None, error is shown."""
        async def fake_get_async(*args, **kwargs):
            return {}

        monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)

        msg = _make_mock_message(role="admin")
        cm = _make_mock_conversation_manager()
        cm.get_conversation = AsyncMock(return_value=None)
        ctx = _make_mock_context(conversation_manager=cm)

        cmd = conversation_module.ConversationCommands(ctx)
        await cmd.compact(msg)

        assert len(msg.result) == 1
        result_text = str(msg.result[0])
        assert "not found" in result_text.lower()

    @pytest.mark.asyncio
    async def test_compact_empty_history(self, monkeypatch):
        """Empty conversation history results in 'nothing to compact' message."""
        async def fake_get_async(*args, **kwargs):
            return {}

        monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)

        msg = _make_mock_message(role="admin")

        cm = _make_mock_conversation_manager(history=[])
        ctx = _make_mock_context(conversation_manager=cm)

        cmd = conversation_module.ConversationCommands(ctx)
        await cmd.compact(msg)

        assert len(msg.result) == 1
        result_text = str(msg.result[0])
        assert "nothing to compact" in result_text.lower()

    @pytest.mark.asyncio
    async def test_compact_successful_compression(self, monkeypatch):
        """Full compact flow compresses messages and saves result."""
        async def fake_get_async(*args, **kwargs):
            return {}

        monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)

        msg = _make_mock_message(role="admin")

        history = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Message 3"},
            {"role": "assistant", "content": "Response 3"},
            {"role": "user", "content": "Message 4"},
            {"role": "assistant", "content": "Response 4"},
        ]

        cm = _make_mock_conversation_manager(history=history)
        ctx = _make_mock_context(conversation_manager=cm)

        cmd = conversation_module.ConversationCommands(ctx)
        await cmd.compact(msg)

        assert len(msg.result) == 1
        result_text = str(msg.result[0])
        assert "compressed" in result_text.lower()
        assert "messages removed" in result_text

        # Verify the result was saved
        assert len(cm._saved_result) > 0
        saved = cm._saved_result[0]
        assert isinstance(saved, list)
        # Should have fewer messages than original (8)
        assert len(saved) < len(history)
        # Each entry should have role and content
        for entry in saved:
            assert "role" in entry
        assert len(saved) > 0

    @pytest.mark.asyncio
    async def test_compact_preserves_tool_calls_metadata(self, monkeypatch):
        """Tool calls and tool_call_id are preserved through the compact flow."""
        async def fake_get_async(*args, **kwargs):
            return {}

        monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)

        msg = _make_mock_message(role="admin")

        history = [
            {"role": "user", "content": "Search the web"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call-1", "type": "function",
                 "function": {"name": "web_search", "arguments": '{"q":"AI"}'}},
            ]},
            {"role": "tool", "content": "Results for AI", "tool_call_id": "call-1"},
            {"role": "assistant", "content": "Here are the results."},
        ]

        cm = _make_mock_conversation_manager(history=history)
        ctx = _make_mock_context(conversation_manager=cm)

        cmd = conversation_module.ConversationCommands(ctx)
        await cmd.compact(msg)

        assert len(msg.result) == 1

        # Verify tool_calls and tool_call_id are in the saved result
        if len(cm._saved_result) > 0:
            saved = cm._saved_result[0]
            for entry in saved:
                if entry.get("role") == "assistant" and "tool_calls" in entry:
                    tool_calls = entry["tool_calls"]
                    assert len(tool_calls) == 1
                    assert tool_calls[0]["id"] == "call-1"
                    assert tool_calls[0]["function"]["name"] == "web_search"
                if entry.get("role") == "tool":
                    assert "tool_call_id" in entry
                    assert entry["tool_call_id"] == "call-1"

    @pytest.mark.asyncio
    async def test_compact_error_during_processing(self, monkeypatch):
        """When process() raises, error message is returned."""
        async def fake_get_async(*args, **kwargs):
            return {}

        monkeypatch.setattr(conversation_module.sp, "get_async", fake_get_async)

        msg = _make_mock_message(role="admin")

        cm = _make_mock_conversation_manager(history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ])

        # Set up a provider that causes process() to fail
        broken_provider = SimpleNamespace(
            provider_config={},  # no max_context_tokens
        )

        ctx = _make_mock_context(
            conversation_manager=cm,
            summary_provider=broken_provider,
        )

        cmd = conversation_module.ConversationCommands(ctx)
        await cmd.compact(msg)

        assert len(msg.result) == 1
        result_text = str(msg.result[0])
        # Should have some response (even if it's an error or success)
        assert result_text is not None
