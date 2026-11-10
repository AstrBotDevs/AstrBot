import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import mcp
import pytest

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor
from astrbot.core.astr_agent_runtime.tools.computer_tools.shell import ShellSessionTool
from astrbot.core.message.components import Image
from astrbot.core.provider.func_tool_manager import (
    FunctionToolManager,
    _PermissionGuardedTool,
)
from astrbot.core.utils.active_event_registry import (
    ActiveEventRegistry,
)


class _DummyEvent:
    def __init__(self, message_components: list[object] | None = None) -> None:
        self.unified_msg_origin = "webchat:FriendMessage:webchat!user!session"
        self.message_obj = SimpleNamespace(message=message_components or [])
        self.role = "member"
        self.extras: dict[str, object] = {}

    def get_extra(self, key: str):
        return self.extras.get(key)

    def set_extra(self, key: str, value: object) -> None:
        self.extras[key] = value


class _DummyTool:
    def __init__(self) -> None:
        self.name = "transfer_to_subagent"
        self.agent = SimpleNamespace(name="subagent")


def _build_run_context(message_components: list[object] | None = None):
    event = _DummyEvent(message_components=message_components)
    ctx = SimpleNamespace(event=event, context=SimpleNamespace())
    return ContextWrapper(context=ctx)


@pytest.mark.asyncio
async def test_legacy_agent_registration_executes_nested_tool(monkeypatch):
    """An existing plugin can register an Agent and execute its nested tools."""
    from astrbot.api import agent
    from astrbot.core.astr_agent_runtime import tool_executor as executor
    from astrbot.core.star.register import register_agent
    from astrbot.core.star.register import star_handler as registration
    from astrbot.core.star.star_manager import PluginManager

    assert agent is register_agent
    manager = FunctionToolManager()
    monkeypatch.setattr(registration, "llm_tools", manager)
    monkeypatch.setattr(executor, "llm_tools", manager)

    @agent(name="legacy_expert", instruction="Use the nested lookup tool.")
    async def legacy_expert():
        pass

    @legacy_expert.llm_tool(name="legacy_lookup")
    async def lookup(event, query: str):
        """Look up the requested value.

        Args:
            query(string): Value to look up.
        """
        return f"found: {query}"

    handoff = manager.get_func("transfer_to_legacy_expert")
    assert isinstance(handoff, HandoffTool)
    nested_tools = list(PluginManager._iter_concrete_llm_tools(handoff))
    assert [tool.name for tool in nested_tools] == ["legacy_lookup"]
    assert manager.get_func("legacy_lookup") is None

    event = _DummyEvent()

    async def run_expert(**kwargs):
        assert kwargs["prompt"] == "example"
        assert kwargs["system_prompt"] == "Use the nested lookup tool."
        nested = kwargs["tools"].get_tool("legacy_lookup")
        assert nested is nested_tools[0]
        result = await nested.handler(event, query=kwargs["prompt"])
        return SimpleNamespace(completion_text=result)

    context = SimpleNamespace(
        get_current_chat_provider_id=AsyncMock(return_value="test-provider"),
        get_config=lambda **_kwargs: {"provider_settings": {}},
        get_llm_tool_manager=lambda: manager,
        tool_loop_agent=run_expert,
    )
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))
    results = [
        result
        async for result in FunctionToolExecutor.execute(
            handoff, run_context, input="example"
        )
    ]
    assert results[0].content[0].text == "found: example"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["poll", "write", "write_line", "interrupt"])
@pytest.mark.parametrize(
    ("yield_time_ms", "configured_timeout", "expected_timeout"),
    [(300_000, 120, 305), (5_000, 120, 120), (300_000, 600, 600)],
)
async def test_shell_session_wait_fits_inside_tool_timeout(
    monkeypatch, action, yield_time_ms, configured_timeout, expected_timeout
):
    from astrbot.core.astr_agent_runtime import tool_executor as tool_exec

    tool = ShellSessionTool()
    monkeypatch.setattr(tool, "call", AsyncMock(return_value="output"))
    run_context = _build_run_context()
    run_context.tool_call_timeout = configured_timeout
    wait_for = AsyncMock(wraps=asyncio.wait_for)
    monkeypatch.setattr(tool_exec.asyncio, "wait_for", wait_for)

    results = [
        result
        async for result in FunctionToolExecutor._execute_local(
            tool,
            run_context,
            action=action,
            session_id="sh_test",
            yield_time_ms=yield_time_ms,
        )
    ]

    assert results[0].content[0].text == "output"
    assert all(
        call.kwargs["timeout"] == expected_timeout for call in wait_for.await_args_list
    )


@pytest.mark.parametrize("runtime", ["none", "local", "sandbox", None])
def test_build_handoff_toolset_keeps_permission_guards_for_default_tools(runtime):
    mgr = FunctionToolManager()
    plugin_tool = FunctionTool(
        name="admin_only_mcp",
        description="admin tool",
        parameters={"type": "object", "properties": {}},
    )
    handoff = HandoffTool(Agent(name="child"))
    mgr.func_list = [plugin_tool, handoff]

    event = _DummyEvent()
    provider_settings = {} if runtime is None else {"computer_use_runtime": runtime}
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {"provider_settings": provider_settings},
        get_llm_tool_manager=lambda: mgr,
    )
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))

    toolset = FunctionToolExecutor._build_handoff_toolset(run_context, tools=None)

    assert toolset is not None
    assert isinstance(toolset.get_tool("admin_only_mcp"), _PermissionGuardedTool)
    assert toolset.get_tool("transfer_to_child") is None
    assert (toolset.get_tool("astrbot_execute_python") is not None) == (
        runtime == "local"
    )
    assert (toolset.get_tool("astrbot_execute_ipython") is not None) == (
        runtime == "sandbox"
    )
    assert (toolset.get_tool("astrbot_execute_shell") is not None) == (
        runtime in {"local", "sandbox"}
    )


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

    image_urls = await FunctionToolExecutor._collect_handoff_image_urls(
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
    image_urls = await FunctionToolExecutor._collect_handoff_image_urls(
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
    result = await FunctionToolExecutor._collect_handoff_image_urls(
        run_context, image_refs
    )
    assert set(result) == expected_supported_refs


@pytest.mark.asyncio
async def test_collect_handoff_image_urls_collects_event_image_when_args_is_none(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        return "/tmp/event_only.png"

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls = await FunctionToolExecutor._collect_handoff_image_urls(
        run_context,
        None,
    )

    assert image_urls == ["/tmp/event_only.png"]


@pytest.mark.asyncio
async def test_do_handoff_background_reports_prepared_image_urls(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    async def _fake_execute_handoff(
        cls, tool, run_context, image_urls_prepared=False, **tool_args
    ):
        assert image_urls_prepared is True
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="ok")]
        )

    async def _fake_wake(ctx, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        FunctionToolExecutor,
        "_execute_handoff",
        classmethod(_fake_execute_handoff),
    )
    run_context = _build_run_context()
    monkeypatch.setattr("astrbot.core.astr_agent_runtime.tool_executor.wake_main_agent", _fake_wake)
    await FunctionToolExecutor._do_handoff_background(
        tool=_DummyTool(),
        run_context=run_context,
        task_id="task-id",
        input="hello",
        image_urls="https://example.com/raw.png",
    )

    prompt = captured["user_prompt"]
    assert captured["source"] == "background_task"
    assert captured["source_id"] == "task-id"
    assert prompt.startswith("<system_reminder>\n")
    assert prompt.endswith("\n</system_reminder>")
    payload = json.loads(prompt.removesuffix("\n</system_reminder>").rsplit("\n", 1)[1])
    assert payload["tool_args"]["image_urls"] == ["https://example.com/raw.png"]


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
        "astrbot.core.astr_agent_runtime.tool_executor.normalize_and_dedupe_strings", _boom
    )

    results = []
    async for result in FunctionToolExecutor._execute_handoff(
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
async def test_collect_handoff_image_urls_keeps_extensionless_existing_event_file(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        return "/tmp/astrbot-handoff-image"

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)
    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.tool_executor.get_astrbot_temp_path", lambda: "/tmp"
    )
    monkeypatch.setattr(
        "astrbot.core.utils.image_ref_utils.os.path.exists", lambda _: True
    )

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls = await FunctionToolExecutor._collect_handoff_image_urls(
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
        "astrbot.core.astr_agent_runtime.tool_executor.get_astrbot_temp_path", lambda: "/tmp"
    )
    monkeypatch.setattr(
        "astrbot.core.utils.image_ref_utils.os.path.exists", lambda _: False
    )

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls = await FunctionToolExecutor._collect_handoff_image_urls(
        run_context,
        [],
    )

    assert image_urls == []


@pytest.mark.asyncio
async def test_execute_handoff_passes_tool_call_timeout_to_tool_loop_agent(
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
        get_config=lambda **_kwargs: {"provider_settings": {}},
    )
    event = _DummyEvent([])
    run_context = ContextWrapper(
        context=SimpleNamespace(event=event, context=context),
        tool_call_timeout=120,
    )
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

    results = []
    async for result in FunctionToolExecutor._execute_handoff(
        tool,
        run_context,
        image_urls_prepared=True,
        input="hello",
        image_urls=[],
    ):
        results.append(result)

    assert len(results) == 1
    assert captured["tool_call_timeout"] == 120


@pytest.mark.asyncio
async def test_collect_handoff_image_urls_filters_extensionless_file_outside_temp_root(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        return "/var/tmp/astrbot-handoff-image"

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)
    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.tool_executor.get_astrbot_temp_path", lambda: "/tmp"
    )
    monkeypatch.setattr(
        "astrbot.core.utils.image_ref_utils.os.path.exists", lambda _: True
    )

    run_context = _build_run_context([Image(file="file:///tmp/original.png")])
    image_urls = await FunctionToolExecutor._collect_handoff_image_urls(
        run_context,
        [],
    )

    assert image_urls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["tool", "handoff"])
@pytest.mark.parametrize("foreground_done", [False, True])
@pytest.mark.parametrize("phase", ["tool", "wakeup", "complete", "failure"])
async def test_background_execution_lifecycle(
    monkeypatch, kind, foreground_done, phase
):
    registry = ActiveEventRegistry()
    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.tool_executor.active_event_registry", registry
    )
    run_context = _build_run_context()
    event = run_context.context.event
    started, release, delivered = (asyncio.Event() for _ in range(3))

    async def execute(cls, *args, **kwargs):
        if phase == "failure":
            raise RuntimeError("tool failed")
        if phase == "tool":
            started.set()
            await release.wait()
        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="done")]
        )

    async def wake(**kwargs):
        started.set()
        await release.wait()
        delivered.set()

    wakeup = AsyncMock(side_effect=wake)
    monkeypatch.setattr("astrbot.core.astr_agent_runtime.tool_executor.wake_main_agent", wakeup)
    monkeypatch.setattr(
        FunctionToolExecutor,
        "_execute_local" if kind == "tool" else "_execute_handoff",
        classmethod(execute),
    )
    tool = (
        FunctionTool(
            name="slow",
            description="slow tool",
            parameters={"type": "object", "properties": {}},
            is_background_task=True,
        )
        if kind == "tool"
        else HandoffTool(Agent(name="worker"))
    )
    arguments = {} if kind == "tool" else {"background_task": True}
    registry.register(event)
    results = [
        r async for r in FunctionToolExecutor.execute(tool, run_context, **arguments)
    ]
    task = next(iter(registry._background_tasks[event.unified_msg_origin]))
    try:
        assert "task_id=" in results[0].content[0].text
        await asyncio.wait_for(started.wait(), timeout=1)
        if foreground_done:
            registry.unregister(event)
        cancelled = phase in ("tool", "wakeup")
        if cancelled:
            assert registry.request_agent_stop_all(event.unified_msg_origin) == 1
        release.set()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1)
        assert task.cancelled() == cancelled
        assert delivered.is_set() != cancelled
        assert wakeup.await_count == (0 if phase == "tool" else 1)
        if wakeup.await_count:
            assert wakeup.call_args.kwargs["source"] == "background_task"
            assert wakeup.call_args.kwargs["source_id"] in results[0].content[0].text
            assert wakeup.call_args.kwargs["user_prompt"].startswith(
                "<system_reminder>\n"
            )
            assert wakeup.call_args.kwargs["user_prompt"].endswith(
                "\n</system_reminder>"
            )
        if phase == "failure":
            assert "tool failed" in wakeup.call_args.kwargs["user_prompt"]
        assert not registry._background_tasks
        if cancelled:
            assert [
                r
                async for r in FunctionToolExecutor.execute(
                    tool, run_context, **arguments
                )
            ] == []
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        registry.unregister(event)


@pytest.mark.asyncio
async def test_external_runner_cancel_closes_pending_tool_executor():
    runner = ToolLoopAgentRunner()
    runner._abort_signal = asyncio.Event()
    started, release, closed, side_effect = (asyncio.Event() for _ in range(4))

    async def execute():
        started.set()
        try:
            await release.wait()
            side_effect.set()
            yield "done"
        finally:
            closed.set()

    results = runner._iter_tool_executor_results(execute())
    task = asyncio.create_task(anext(results))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1)
        assert task.cancelled() and closed.is_set()
        assert not side_effect.is_set()
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await results.aclose()


@pytest.mark.asyncio
async def test_tool_specific_timeout_survives_permission_wrapper(monkeypatch):
    from astrbot.core.astr_agent_runtime import tool_executor as executor
    from astrbot.core.provider.func_tool_manager import FunctionToolManager

    manager = FunctionToolManager()
    tool = FunctionTool(
        name="waiting",
        description="Wait",
        parameters={},
        handler=AsyncMock(return_value="done"),
        execution_timeout=65,
    )
    manager.func_list = [tool]
    context = _build_run_context()
    context.tool_call_timeout = 1
    waiting = AsyncMock(wraps=asyncio.wait_for)
    monkeypatch.setattr(executor.asyncio, "wait_for", waiting)
    guarded = manager.get_full_tool_set().get_tool("waiting")
    results = [
        result async for result in FunctionToolExecutor._execute_local(guarded, context)
    ]
    assert results[0].content[0].text == "done"
    assert waiting.await_args_list[0].kwargs["timeout"] == 65
