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
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.message.components import Image
from astrbot.core.provider.func_tool_manager import (
    FunctionToolManager,
    _PermissionGuardedTool,
)
from astrbot.core.tools.computer_tools import ExecuteShellTool
from astrbot.core.tools.computer_tools.shell import ShellSessionTool
from astrbot.core.utils.active_event_registry import ActiveEventRegistry


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
@pytest.mark.parametrize("action", ["poll", "write", "write_line", "interrupt"])
@pytest.mark.parametrize(
    ("yield_time_ms", "configured_timeout", "expected_timeout"),
    [(300_000, 120, 305), (5_000, 120, 120), (300_000, 600, 600)],
)
async def test_shell_session_wait_fits_inside_tool_timeout(
    monkeypatch, action, yield_time_ms, configured_timeout, expected_timeout
):
    from astrbot.core import astr_agent_tool_exec as tool_exec

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


class _DoneRunner:
    async def step_until_done(self, _max_step):
        for item in ():
            yield item

    def get_final_llm_resp(self):
        return SimpleNamespace(role="assistant", completion_text="done")


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


def _whitelist_run_context(runtime: str, extra_provider_settings: dict | None = None):
    provider_settings = {"computer_use_runtime": runtime}
    if extra_provider_settings:
        provider_settings.update(extra_provider_settings)
    event = _DummyEvent()
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {"provider_settings": provider_settings},
        get_llm_tool_manager=lambda: FunctionToolManager(),
    )
    return ContextWrapper(context=SimpleNamespace(event=event, context=context))


def test_build_handoff_toolset_whitelist_keeps_computer_use_tools(monkeypatch):
    # The persona whitelist only lists plugin/MCP tools, but the builtin
    # computer-use tools must stay available, mirroring the main agent where
    # they are applied after the persona whitelist narrowing and never pass
    # through it.
    plugin_tool = FunctionTool(
        name="plugin_tool",
        description="plugin tool",
        parameters={"type": "object", "properties": {}},
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_tool_exec.llm_tools.func_list", [plugin_tool]
    )

    toolset = FunctionToolExecutor._build_handoff_toolset(
        _whitelist_run_context("sandbox"), tools=["plugin_tool"]
    )

    assert toolset is not None
    assert toolset.get_tool("plugin_tool") is not None
    assert toolset.get_tool("astrbot_execute_ipython") is not None
    assert toolset.get_tool("astrbot_execute_shell") is not None


def test_build_handoff_toolset_whitelist_warns_and_skips_unknown_names(
    monkeypatch, caplog
):
    monkeypatch.setattr("astrbot.core.astr_agent_tool_exec.llm_tools.func_list", [])

    with caplog.at_level("WARNING"):
        toolset = FunctionToolExecutor._build_handoff_toolset(
            _whitelist_run_context("none"), tools=["missing_tool"]
        )

    assert toolset is None
    assert any("missing_tool" in rec.message for rec in caplog.records)
    assert any("empty toolset" in rec.message for rec in caplog.records)


def test_build_handoff_toolset_whitelist_warns_on_inactive_tool(monkeypatch, caplog):
    inactive_tool = FunctionTool(
        name="off_tool",
        description="disabled plugin tool",
        parameters={"type": "object", "properties": {}},
    )
    inactive_tool.active = False
    monkeypatch.setattr(
        "astrbot.core.astr_agent_tool_exec.llm_tools.func_list", [inactive_tool]
    )

    with caplog.at_level("WARNING"):
        toolset = FunctionToolExecutor._build_handoff_toolset(
            _whitelist_run_context("none"), tools=["off_tool", "astrbot_grep_tool"]
        )

    # The inactive plugin tool is skipped with a warning, while an explicit
    # builtin name still resolves through llm_tools.get_func.
    assert toolset is not None
    assert toolset.get_tool("off_tool") is None
    assert toolset.get_tool("astrbot_grep_tool") is not None
    assert any("off_tool" in rec.message for rec in caplog.records)


def test_build_handoff_toolset_empty_whitelist_keeps_runtime_tools(caplog):
    # An empty whitelist narrows the plugin tools to nothing but keeps the
    # runtime computer-use tools, same as an empty persona whitelist on the
    # main agent.
    with caplog.at_level("WARNING"):
        toolset = FunctionToolExecutor._build_handoff_toolset(
            _whitelist_run_context("sandbox"), tools=[]
        )

    assert toolset is not None
    assert toolset.get_tool("astrbot_execute_shell") is not None
    assert toolset.get_tool("astrbot_execute_ipython") is not None
    assert not any("empty toolset" in rec.message for rec in caplog.records)


def test_build_handoff_toolset_empty_whitelist_without_runtime_warns(caplog):
    with caplog.at_level("WARNING"):
        toolset = FunctionToolExecutor._build_handoff_toolset(
            _whitelist_run_context("none"), tools=[]
        )

    assert toolset is None
    assert any("empty toolset" in rec.message for rec in caplog.records)


def test_build_handoff_toolset_whitelist_skips_deactivated_runtime_tools(caplog):
    mgr = FunctionToolManager()
    mgr.get_builtin_tool(ExecuteShellTool).active = False

    event = _DummyEvent()
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {"computer_use_runtime": "sandbox"}
        },
        get_llm_tool_manager=lambda: mgr,
    )
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))

    with caplog.at_level("WARNING"):
        toolset = FunctionToolExecutor._build_handoff_toolset(run_context, tools=[])

    assert toolset is not None
    assert toolset.get_tool("astrbot_execute_shell") is None
    assert toolset.get_tool("astrbot_execute_ipython") is not None
    assert any(
        "deactivated runtime tools" in rec.message
        and "astrbot_execute_shell" in rec.message
        for rec in caplog.records
    )


@pytest.mark.parametrize(
    ("booter_state", "expect_browser"),
    [
        pytest.param("not_booted", True, id="capabilities_unknown_before_first_boot"),
        pytest.param("browser", True, id="profile_supports_browser"),
        pytest.param("shell_only", False, id="profile_without_browser"),
    ],
)
def test_build_handoff_toolset_seeds_browser_tools_like_main_agent(
    monkeypatch, booter_state, expect_browser
):
    from astrbot.core.computer.computer_client import session_booter

    umo = _DummyEvent().unified_msg_origin
    if booter_state == "not_booted":
        monkeypatch.delitem(session_booter, umo, raising=False)
    elif booter_state == "browser":
        monkeypatch.setitem(
            session_booter, umo, SimpleNamespace(capabilities=["browser", "shell"])
        )
    else:
        monkeypatch.setitem(
            session_booter, umo, SimpleNamespace(capabilities=["shell", "python"])
        )

    toolset = FunctionToolExecutor._build_handoff_toolset(
        _whitelist_run_context("sandbox", {"sandbox": {"booter": "shipyard_neo"}}),
        tools=[],
    )

    assert toolset is not None
    assert toolset.get_tool("astrbot_execute_shell") is not None
    assert (toolset.get_tool("astrbot_execute_browser") is not None) == expect_browser
    assert (
        toolset.get_tool("astrbot_execute_browser_batch") is not None
    ) == expect_browser
    assert (toolset.get_tool("astrbot_run_browser_skill") is not None) == expect_browser


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

    async def _fake_wake(cls, run_context, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        FunctionToolExecutor,
        "_execute_handoff",
        classmethod(_fake_execute_handoff),
    )
    monkeypatch.setattr(
        FunctionToolExecutor,
        "_wake_main_agent_for_background_result",
        classmethod(_fake_wake),
    )

    run_context = _build_run_context()
    await FunctionToolExecutor._do_handoff_background(
        tool=_DummyTool(),
        run_context=run_context,
        task_id="task-id",
        input="hello",
        image_urls="https://example.com/raw.png",
    )

    assert captured["tool_args"]["image_urls"] == ["https://example.com/raw.png"]


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
        "astrbot.core.astr_agent_tool_exec.normalize_and_dedupe_strings", _boom
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
        "astrbot.core.astr_agent_tool_exec.get_astrbot_temp_path", lambda: "/tmp"
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
        "astrbot.core.astr_agent_tool_exec.get_astrbot_temp_path", lambda: "/tmp"
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
@pytest.mark.parametrize("stop_phase", [None, "before", "history", "build"])
async def test_background_wakeup_passes_history_and_provider_settings_to_main_agent(
    monkeypatch: pytest.MonkeyPatch,
    stop_phase,
):
    """Test background wakeup keeps structured history and provider settings."""
    provider_settings = {
        "fallback_chat_models": ["fallback-provider"],
        "request_max_retries": 3,
        "stream": True,
    }
    history = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
    ]
    captured: dict = {}

    async def _fake_get_session_conv(**_kwargs):
        if stop_phase == "history":
            stop_signal.set()
        return SimpleNamespace(history=json.dumps(history))

    async def _fake_build_main_agent(**kwargs):
        captured.update(kwargs)
        if stop_phase == "build":
            stop_signal.set()
        return SimpleNamespace(agent_runner=_DoneRunner())

    monkeypatch.setattr(
        "astrbot.core.astr_main_agent._get_session_conv",
        _fake_get_session_conv,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_main_agent.build_main_agent",
        _fake_build_main_agent,
    )
    persist = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.astr_agent_tool_exec.persist_agent_history",
        persist,
    )

    send_tool = FunctionTool(
        name="send_message_to_user",
        description="send",
        parameters={"type": "object", "properties": {}},
    )
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {"provider_settings": provider_settings},
        get_llm_tool_manager=lambda: SimpleNamespace(
            get_builtin_tool=lambda _tool_cls: send_tool
        ),
        conversation_manager=SimpleNamespace(),
    )
    run_context = ContextWrapper(
        context=SimpleNamespace(event=_DummyEvent([]), context=context),
        tool_call_timeout=456,
    )
    stop_signal = asyncio.Event()
    run_context.context.event.set_extra("_background_stop_signal", stop_signal)
    if stop_phase == "before":
        stop_signal.set()

    await FunctionToolExecutor._wake_main_agent_for_background_result(
        run_context,
        task_id="task-id",
        tool_name="long_tool",
        result_text="ok",
        tool_args={},
        note="task finished",
        summary_name="BackgroundTask",
    )

    if stop_phase in ("before", "history"):
        assert not captured
        persist.assert_not_awaited()
        return
    config = captured["config"]
    assert config.tool_call_timeout == 456
    assert config.streaming_response == provider_settings["stream"]
    assert config.provider_settings == provider_settings
    assert config.provider_settings["fallback_chat_models"] == ["fallback-provider"]
    request = captured["req"]
    assert "old question" not in request.system_prompt
    assert "old answer" not in request.system_prompt
    assert request.contexts == history
    assert captured["event"].get_extra("_background_stop_signal") is stop_signal
    assert "_background_stop_signal" not in request.system_prompt
    assert persist.await_count == (0 if stop_phase == "build" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_settings", "expected_max_step"),
    [
        pytest.param({"max_agent_step": 50}, 50, id="configured"),
        pytest.param({}, 128, id="missing_falls_back_to_default"),
        pytest.param({"max_agent_step": True}, 128, id="boolean_falls_back_to_default"),
        pytest.param({"max_agent_step": "50"}, 50, id="numeric_string_coerced"),
        pytest.param({"max_agent_step": 0}, 1, id="zero_clamped_to_min"),
    ],
)
async def test_background_wakeup_applies_max_agent_step(
    monkeypatch: pytest.MonkeyPatch,
    provider_settings: dict,
    expected_max_step: int,
):
    class _StepCapturingRunner:
        def __init__(self):
            self.captured_max_step = None

        async def step_until_done(self, max_step):
            self.captured_max_step = max_step
            if False:
                yield

        def get_final_llm_resp(self):
            return SimpleNamespace(role="assistant", completion_text="done")

    runner = _StepCapturingRunner()

    async def _fake_get_session_conv(**_kwargs):
        return SimpleNamespace(history="[]")

    async def _fake_build_main_agent(**_kwargs):
        return SimpleNamespace(agent_runner=runner)

    monkeypatch.setattr(
        "astrbot.core.astr_main_agent._get_session_conv",
        _fake_get_session_conv,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_main_agent.build_main_agent",
        _fake_build_main_agent,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_tool_exec.persist_agent_history",
        AsyncMock(),
    )

    send_tool = FunctionTool(
        name="send_message_to_user",
        description="send",
        parameters={"type": "object", "properties": {}},
    )
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {
                    "misc": {"max_steps": provider_settings.get("max_agent_step", 128)}
                },
            },
        },
        get_llm_tool_manager=lambda: SimpleNamespace(
            get_builtin_tool=lambda _tool_cls: send_tool
        ),
        conversation_manager=SimpleNamespace(),
    )
    run_context = ContextWrapper(
        context=SimpleNamespace(event=_DummyEvent([]), context=context),
        tool_call_timeout=120,
    )

    await FunctionToolExecutor._wake_main_agent_for_background_result(
        run_context,
        task_id="task-id",
        tool_name="long_tool",
        result_text="ok",
        tool_args={},
        note="task finished",
        summary_name="BackgroundTask",
    )

    assert runner.captured_max_step == expected_max_step


@pytest.mark.asyncio
async def test_collect_handoff_image_urls_filters_extensionless_file_outside_temp_root(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_convert_to_file_path(self):
        return "/var/tmp/astrbot-handoff-image"

    monkeypatch.setattr(Image, "convert_to_file_path", _fake_convert_to_file_path)
    monkeypatch.setattr(
        "astrbot.core.astr_agent_tool_exec.get_astrbot_temp_path", lambda: "/tmp"
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
        "astrbot.core.astr_agent_tool_exec.active_event_registry", registry
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
    monkeypatch.setattr(
        FunctionToolExecutor, "_wake_main_agent_for_background_result", wakeup
    )
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
        if phase == "failure":
            assert "tool failed" in wakeup.call_args.kwargs["result_text"]
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
