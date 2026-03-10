import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import mcp
import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.message.components import Image
from astrbot.core.subagent.background_notifier import (
    wake_main_agent_for_background_result,
)
from astrbot.core.subagent.handoff_executor import HandoffExecutor
from astrbot.core.subagent.models import SubagentTaskData


class _DummyEvent:
    def __init__(self, message_components: list[object] | None = None) -> None:
        self.unified_msg_origin = "webchat:FriendMessage:webchat!user!session"
        self.message_obj = SimpleNamespace(message=message_components or [])
        self.role = "assistant"
        self._extras: dict[str, object] = {}

    def get_extra(self, key: str):
        return self._extras.get(key)

    def set_extra(self, key: str, value: object) -> None:
        self._extras[key] = value


class _DummyTool:
    def __init__(self) -> None:
        self.name = "transfer_to_subagent"
        self.agent = SimpleNamespace(name="subagent")


def _build_run_context(message_components: list[object] | None = None):
    event = _DummyEvent(message_components=message_components)
    ctx = SimpleNamespace(event=event, context=SimpleNamespace())
    return ContextWrapper(context=ctx)


@pytest.mark.asyncio
async def test_collect_handoff_image_urls_normalizes_filters_and_appends_event_image(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        return "/tmp/event_image.png"

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls_input = (
        " https://example.com/a.png ",
        "/tmp/not_an_image.txt",
        "/tmp/local.webp",
        123,
    )

    image_urls = await HandoffExecutor.collect_handoff_image_urls(
        run_context,
        image_urls_input,
    )

    assert image_urls == [
        "https://example.com/a.png",
        "/tmp/local.webp",
        "/tmp/event_image.png",
    ]


@pytest.mark.asyncio
async def test_collect_handoff_image_urls_skips_failed_event_image_conversion(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls = await HandoffExecutor.collect_handoff_image_urls(
        run_context,
        ["https://example.com/a.png"],
    )

    assert image_urls == ["https://example.com/a.png"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image_refs", "expected_supported_refs"),
    [
        pytest.param(
            (
                "https://example.com/valid.png",
                "base64://iVBORw0KGgoAAAANSUhEUgAAAAUA",
                "file:///tmp/photo.heic",
                "file://localhost/tmp/vector.svg",
                "file://fileserver/share/image.webp",
                "file:///tmp/not-image.txt",
                "mailto:user@example.com",
                "random-string-without-scheme-or-extension",
            ),
            {
                "https://example.com/valid.png",
                "base64://iVBORw0KGgoAAAANSUhEUgAAAAUA",
                "file:///tmp/photo.heic",
                "file://localhost/tmp/vector.svg",
                "file://fileserver/share/image.webp",
            },
            id="mixed_supported_and_unsupported_refs",
        ),
    ],
)
async def test_collect_handoff_image_urls_filters_supported_schemes_and_extensions(
    image_refs: tuple[str, ...],
    expected_supported_refs: set[str],
):
    run_context = _build_run_context([])
    result = await HandoffExecutor.collect_handoff_image_urls(run_context, image_refs)
    assert set(result) == expected_supported_refs


@pytest.mark.asyncio
async def test_collect_handoff_image_urls_collects_event_image_when_args_is_none(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        return "/tmp/event_only.png"

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls = await HandoffExecutor.collect_handoff_image_urls(
        run_context,
        None,
    )

    assert image_urls == ["/tmp/event_only.png"]


@pytest.mark.asyncio
async def test_execute_handoff_skips_renormalize_when_image_urls_prepared(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    def _boom(_items):
        raise RuntimeError("normalize should not be called")

    async def _fake_get_current_chat_provider_id(_umo):
        return "provider-id"

    async def _fake_tool_loop_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(completion_text="ok")

    context = SimpleNamespace(
        get_current_chat_provider_id=_fake_get_current_chat_provider_id,
        tool_loop_agent=_fake_tool_loop_agent,
        get_config=lambda **_kwargs: {"provider_settings": {}},
    )
    event = _DummyEvent([])
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))
    tool = SimpleNamespace(
        name="transfer_to_subagent",
        provider_id=None,
        agent=SimpleNamespace(
            name="subagent",
            tools=[],
            instructions="subagent-instructions",
            begin_dialogs=[],
            run_hooks=None,
        ),
    )

    monkeypatch.setattr(
        "astrbot.core.subagent.handoff_executor.normalize_and_dedupe_strings", _boom
    )

    results = []
    async for result in HandoffExecutor.execute_foreground(
        tool,
        run_context,
        image_urls_prepared=True,
        input="hello",
        image_urls=["https://example.com/raw.png"],
    ):
        results.append(result)

    assert len(results) == 1
    assert captured["image_urls"] == ["https://example.com/raw.png"]


@pytest.mark.asyncio
async def test_execute_handoff_uses_subagent_max_steps_override(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    async def _fake_get_current_chat_provider_id(_umo):
        return "provider-id"

    async def _fake_tool_loop_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(completion_text="ok")

    context = SimpleNamespace(
        get_current_chat_provider_id=_fake_get_current_chat_provider_id,
        tool_loop_agent=_fake_tool_loop_agent,
        get_config=lambda **_kwargs: {"provider_settings": {"max_agent_step": 30}},
    )
    event = _DummyEvent([])
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))
    tool = SimpleNamespace(
        name="transfer_to_subagent",
        provider_id=None,
        max_steps=5,
        agent=SimpleNamespace(
            name="subagent",
            tools=[],
            instructions="subagent-instructions",
            begin_dialogs=[],
            run_hooks=None,
        ),
    )

    results = []
    async for result in HandoffExecutor.execute_foreground(
        tool,
        run_context,
        input="hello",
        image_urls=[],
    ):
        results.append(result)

    assert len(results) == 1
    assert captured["max_steps"] == 5


@pytest.mark.asyncio
async def test_execute_handoff_forwards_run_context_tool_call_timeout():
    captured: dict = {}

    async def _fake_get_current_chat_provider_id(_umo):
        return "provider-id"

    async def _fake_tool_loop_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(completion_text="ok")

    context = SimpleNamespace(
        get_current_chat_provider_id=_fake_get_current_chat_provider_id,
        tool_loop_agent=_fake_tool_loop_agent,
        get_config=lambda **_kwargs: {"provider_settings": {"max_agent_step": 30}},
    )
    event = _DummyEvent([])
    run_context = ContextWrapper(
        context=SimpleNamespace(event=event, context=context),
        tool_call_timeout=321,
    )
    tool = SimpleNamespace(
        name="transfer_to_subagent",
        provider_id=None,
        max_steps=None,
        agent=SimpleNamespace(
            name="subagent",
            tools=[],
            instructions="subagent-instructions",
            begin_dialogs=[],
            run_hooks=None,
        ),
    )

    results = []
    async for result in HandoffExecutor.execute_foreground(
        tool,
        run_context,
        input="hello",
        image_urls=[],
    ):
        results.append(result)

    assert len(results) == 1
    assert captured["tool_call_timeout"] == 321


@pytest.mark.asyncio
async def test_execute_queued_task_uses_prepared_image_urls_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    class _FakeAstrAgentContext:
        def __init__(self, *, context, event):
            self.context = context
            self.event = event

    class _FakeAgentContextWrapper:
        def __init__(self, *, context, tool_call_timeout):
            self.context = context
            self.tool_call_timeout = tool_call_timeout

    async def _fake_execute_foreground(*_args, **kwargs):
        assert kwargs["image_urls_prepared"] is True
        assert kwargs["image_urls"] == ["https://example.com/a.png"]
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="done from queued task")]
        )

    async def _fake_notify(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(HandoffExecutor, "execute_foreground", _fake_execute_foreground)
    monkeypatch.setattr(
        "astrbot.core.subagent.handoff_executor.wake_main_agent_for_background_result",
        _fake_notify,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_context.AstrAgentContext",
        _FakeAstrAgentContext,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_context.AgentContextWrapper",
        _FakeAgentContextWrapper,
    )

    task = SubagentTaskData(
        task_id="task_queued_1",
        idempotency_key="idem",
        umo="webchat:FriendMessage:webchat!user!session",
        subagent_name="subagent",
        handoff_tool_name="transfer_to_subagent",
        status="running",
        attempt=1,
        max_attempts=3,
        next_run_at=None,
        payload_json=json.dumps(
            {
                "_meta": {"background_note": "finished", "tool_call_timeout": 90},
                "tool_args": {
                    "image_urls": ["https://example.com/a.png"],
                    "input": "hello",
                },
            }
        ),
        error_class=None,
        last_error=None,
        result_text=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        finished_at=None,
    )
    plugin_context = SimpleNamespace()
    handoff = SimpleNamespace(
        name="transfer_to_subagent",
        agent=SimpleNamespace(
            name="subagent",
            tools=[],
            instructions="subagent-instructions",
            begin_dialogs=[],
            run_hooks=None,
        ),
        provider_id=None,
        max_steps=None,
    )

    result = await HandoffExecutor.execute_queued_task(
        task=task,
        plugin_context=plugin_context,
        handoff=handoff,
    )

    assert "done from queued task" in result
    assert captured["task_id"] == "task_queued_1"
    assert captured["note"] == "finished"
    assert captured["tool_args"]["image_urls"] == ["https://example.com/a.png"]


@pytest.mark.asyncio
async def test_execute_queued_task_restores_nested_depth_from_meta(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    class _FakeAstrAgentContext:
        def __init__(self, *, context, event):
            self.context = context
            self.event = event

    class _FakeAgentContextWrapper:
        def __init__(self, *, context, tool_call_timeout):
            self.context = context
            self.tool_call_timeout = tool_call_timeout

    async def _fake_execute_foreground(_tool, run_context, **kwargs):
        captured["depth"] = run_context.context.event.get_extra(
            "subagent_handoff_depth"
        )
        captured["timeout"] = run_context.tool_call_timeout
        captured["kwargs"] = kwargs
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="done from queued depth")]
        )

    async def _fake_notify(**kwargs):
        captured["notify"] = kwargs

    monkeypatch.setattr(HandoffExecutor, "execute_foreground", _fake_execute_foreground)
    monkeypatch.setattr(
        "astrbot.core.subagent.handoff_executor.wake_main_agent_for_background_result",
        _fake_notify,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_context.AstrAgentContext",
        _FakeAstrAgentContext,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_context.AgentContextWrapper",
        _FakeAgentContextWrapper,
    )

    task = SubagentTaskData(
        task_id="task_queued_depth",
        idempotency_key="idem_depth",
        umo="webchat:FriendMessage:webchat!user!session",
        subagent_name="subagent",
        handoff_tool_name="transfer_to_subagent",
        status="running",
        attempt=1,
        max_attempts=3,
        next_run_at=None,
        payload_json=json.dumps(
            {
                "_meta": {
                    "background_note": "finished",
                    "tool_call_timeout": 222,
                    "subagent_handoff_depth": 2,
                },
                "tool_args": {"image_urls": [], "input": "hello"},
            }
        ),
        error_class=None,
        last_error=None,
        result_text=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        finished_at=None,
    )

    handoff = SimpleNamespace(
        name="transfer_to_subagent",
        agent=SimpleNamespace(
            name="subagent",
            tools=[],
            instructions="subagent-instructions",
            begin_dialogs=[],
            run_hooks=None,
        ),
        provider_id=None,
        max_steps=None,
    )

    result = await HandoffExecutor.execute_queued_task(
        task=task,
        plugin_context=SimpleNamespace(),
        handoff=handoff,
    )

    assert "done from queued depth" in result
    assert captured["depth"] == 2
    assert captured["timeout"] == 222


@pytest.mark.asyncio
async def test_execute_queued_task_restores_handoff_from_snapshot_when_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    class _FakeAstrAgentContext:
        def __init__(self, *, context, event):
            self.context = context
            self.event = event

    class _FakeAgentContextWrapper:
        def __init__(self, *, context, tool_call_timeout):
            self.context = context
            self.tool_call_timeout = tool_call_timeout

    async def _fake_execute_foreground(tool, *_args, **kwargs):
        captured["tool"] = tool
        captured["kwargs"] = kwargs
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="done from snapshot")]
        )

    async def _fake_notify(**kwargs):
        captured["notify"] = kwargs

    monkeypatch.setattr(HandoffExecutor, "execute_foreground", _fake_execute_foreground)
    monkeypatch.setattr(
        "astrbot.core.subagent.handoff_executor.wake_main_agent_for_background_result",
        _fake_notify,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_context.AstrAgentContext",
        _FakeAstrAgentContext,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_context.AgentContextWrapper",
        _FakeAgentContextWrapper,
    )

    task = SubagentTaskData(
        task_id="task_queued_snapshot",
        idempotency_key="idem_snapshot",
        umo="webchat:FriendMessage:webchat!user!session",
        subagent_name="subagent",
        handoff_tool_name="transfer_to_subagent",
        status="running",
        attempt=1,
        max_attempts=3,
        next_run_at=None,
        payload_json=json.dumps(
            {
                "_handoff_snapshot": {
                    "name": "transfer_to_subagent",
                    "agent_name": "subagent",
                    "agent_display_name": "Sub Agent",
                    "instructions": "snapshot prompt",
                    "tools": ["tool_a"],
                    "begin_dialogs": [{"role": "assistant", "content": "hello"}],
                    "provider_id": "provider-x",
                    "max_steps": 9,
                    "tool_description": "snapshot desc",
                },
                "_meta": {"background_note": "done", "tool_call_timeout": 60},
                "tool_args": {
                    "image_urls": ["https://example.com/a.png"],
                    "input": "hi",
                },
            }
        ),
        error_class=None,
        last_error=None,
        result_text=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        finished_at=None,
    )

    result = await HandoffExecutor.execute_queued_task(
        task=task,
        plugin_context=SimpleNamespace(),
        handoff=None,
    )

    restored_tool = captured["tool"]
    assert restored_tool.name == "transfer_to_subagent"
    assert restored_tool.provider_id == "provider-x"
    assert restored_tool.max_steps == 9
    assert restored_tool.agent_display_name == "Sub Agent"
    assert restored_tool.agent.instructions == "snapshot prompt"
    assert restored_tool.agent.tools == ["tool_a"]
    assert restored_tool.agent.begin_dialogs == [
        {"role": "assistant", "content": "hello"}
    ]
    assert "done from snapshot" in result


@pytest.mark.asyncio
async def test_build_handoff_toolset_defaults_runtime_to_none():
    event = _DummyEvent([])
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {"provider_settings": {}},
    )
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))
    toolset = HandoffExecutor.build_handoff_toolset(run_context, [])
    assert toolset is None


@pytest.mark.asyncio
async def test_wake_main_agent_for_background_result_uses_background_overrides(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    class _Runner:
        async def step_until_done(self, _max_steps):
            if False:
                yield None

        def get_final_llm_resp(self):
            return SimpleNamespace(completion_text="done")

    async def _fake_get_session_conv(*, event, plugin_context):
        _ = event
        _ = plugin_context
        return SimpleNamespace(history='[{"role":"user","content":"hello"}]')

    async def _fake_build_main_agent(*, event, plugin_context, config, req):
        captured["event"] = event
        captured["plugin_context"] = plugin_context
        captured["config"] = config
        captured["req"] = req
        return SimpleNamespace(agent_runner=_Runner())

    async def _fake_persist_agent_history(*args, **kwargs):
        _ = args
        _ = kwargs
        return None

    monkeypatch.setattr(
        "astrbot.core.astr_main_agent._get_session_conv",
        _fake_get_session_conv,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_main_agent.build_main_agent",
        _fake_build_main_agent,
    )
    monkeypatch.setattr(
        "astrbot.core.subagent.background_notifier.persist_agent_history",
        _fake_persist_agent_history,
    )

    provider_settings = {
        "tool_call_timeout": 123,
        "streaming_response": False,
        "computer_use_runtime": "none",
        "proactive_capability": {"add_cron_tools": False},
        "llm_safety_mode": True,
    }
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": provider_settings,
            "subagent_orchestrator": {"main_enable": True},
            "kb_agentic_mode": False,
            "timezone": "UTC",
        },
        conversation_manager=SimpleNamespace(),
    )
    event = _DummyEvent([])
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))

    await wake_main_agent_for_background_result(
        run_context=run_context,
        task_id="task_1",
        tool_name="transfer_to_subagent",
        result_text="ok",
        tool_args={"input": "hello"},
        note="background finished",
        summary_name="subagent-summary",
    )

    cfg = captured["config"]
    assert cfg.tool_call_timeout == 900
    assert cfg.computer_use_runtime == "none"
    assert cfg.add_cron_tools is False
    assert cfg.provider_settings["computer_use_runtime"] == "none"
    assert (
        "Below is your and the user's previous conversation history:"
        in captured["req"].system_prompt
    )


@pytest.mark.asyncio
async def test_collect_handoff_image_urls_keeps_extensionless_existing_event_file(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        return "/tmp/astrbot-handoff-image"

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)
    monkeypatch.setattr(
        "astrbot.core.subagent.handoff_executor.get_astrbot_temp_path", lambda: "/tmp"
    )
    monkeypatch.setattr(
        "astrbot.core.utils.image_ref_utils.os.path.exists", lambda _: True
    )

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls = await HandoffExecutor.collect_handoff_image_urls(
        run_context,
        [],
    )

    assert image_urls == ["/tmp/astrbot-handoff-image"]


@pytest.mark.asyncio
async def test_collect_handoff_image_urls_filters_extensionless_missing_event_file(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        return "/tmp/astrbot-handoff-missing-image"

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)
    monkeypatch.setattr(
        "astrbot.core.subagent.handoff_executor.get_astrbot_temp_path", lambda: "/tmp"
    )
    monkeypatch.setattr(
        "astrbot.core.utils.image_ref_utils.os.path.exists", lambda _: False
    )

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls = await HandoffExecutor.collect_handoff_image_urls(
        run_context,
        [],
    )

    assert image_urls == []


@pytest.mark.asyncio
async def test_collect_handoff_image_urls_filters_extensionless_file_outside_temp_root(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        return "/var/tmp/astrbot-handoff-image"

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)
    monkeypatch.setattr(
        "astrbot.core.subagent.handoff_executor.get_astrbot_temp_path", lambda: "/tmp"
    )
    monkeypatch.setattr(
        "astrbot.core.utils.image_ref_utils.os.path.exists", lambda _: True
    )

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls = await HandoffExecutor.collect_handoff_image_urls(
        run_context,
        [],
    )

    assert image_urls == []


@pytest.mark.asyncio
async def test_execute_handoff_background_strict_failover_without_orchestrator():
    run_context = _build_run_context()
    tool = _DummyTool()

    with patch(
        "astrbot.core.astr_agent_tool_exec.asyncio.create_task"
    ) as create_task_mock:
        results = []
        async for result in HandoffExecutor.submit_background(
            tool,
            run_context,
            tool_call_id="call_1",
            input="hello",
            image_urls=["https://example.com/raw.png"],
        ):
            results.append(result)

    assert len(results) == 1
    assert "error:" in results[0].content[0].text
    create_task_mock.assert_not_called()


@pytest.mark.asyncio
async def test_execute_handoff_background_strict_failover_submit_error():
    orchestrator = SimpleNamespace(
        submit_handoff=AsyncMock(side_effect=RuntimeError("boom"))
    )
    event = _DummyEvent([])
    context = SimpleNamespace(subagent_orchestrator=orchestrator)
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))

    with patch(
        "astrbot.core.astr_agent_tool_exec.asyncio.create_task"
    ) as create_task_mock:
        results = []
        async for result in HandoffExecutor.submit_background(
            _DummyTool(),
            run_context,
            tool_call_id="call_1",
            input="hello",
        ):
            results.append(result)

    assert len(results) == 1
    assert "error:" in results[0].content[0].text
    create_task_mock.assert_not_called()
