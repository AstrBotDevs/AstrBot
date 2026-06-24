from types import SimpleNamespace

import mcp
import pytest

from astrbot.core import astr_agent_tool_exec
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_tool_exec import (
    FunctionToolExecutor,
    _is_builtin_tool_instance,
)
from astrbot.core.message.components import Image
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.tools.computer_tools import ExecuteShellTool


class _DummyEvent:
    def __init__(self, message_components: list[object] | None = None) -> None:
        self.unified_msg_origin = "webchat:FriendMessage:webchat!user!session"
        self.message_obj = SimpleNamespace(message=message_components or [])

    def get_extra(self, _key: str):
        return None


class _DummyTool:
    def __init__(self) -> None:
        self.name = "transfer_to_subagent"
        self.agent = SimpleNamespace(name="subagent")


def _build_run_context(message_components: list[object] | None = None):
    event = _DummyEvent(message_components=message_components)
    ctx = SimpleNamespace(event=event, context=SimpleNamespace())
    return ContextWrapper(context=ctx)


def test_build_handoff_toolset_includes_plain_tools_excludes_handoffs():
    """Permission checks now happen in execute(), not here."""
    mgr = FunctionToolManager()
    plugin_tool = FunctionTool(
        name="admin_only_mcp",
        description="admin tool",
        parameters={"type": "object", "properties": {}},
    )
    handoff = HandoffTool(Agent(name="child"))
    mgr.func_list = [plugin_tool, handoff]

    event = _DummyEvent()
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {"computer_use_runtime": "none"}
        },
        get_llm_tool_manager=lambda: mgr,
    )
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))

    toolset = FunctionToolExecutor._build_handoff_toolset(run_context, tools=None)

    assert toolset is not None
    assert toolset.get_tool("admin_only_mcp") is plugin_tool
    assert toolset.get_tool("transfer_to_child") is None


def test_is_builtin_tool_instance_true_for_real_builtin_tool():
    assert _is_builtin_tool_instance(ExecuteShellTool()) is True


def test_is_builtin_tool_instance_false_for_plain_tool():
    tool = FunctionTool(
        name="my_plugin_tool",
        description="d",
        parameters={"type": "object", "properties": {}},
    )
    assert _is_builtin_tool_instance(tool) is False


def test_is_builtin_tool_instance_false_for_name_collision_with_builtin():
    """Same name as a builtin tool, different class — must not be treated
    as builtin."""
    impostor = FunctionTool(
        name="astrbot_execute_shell",
        description="not actually the builtin shell tool",
        parameters={"type": "object", "properties": {}},
    )
    assert _is_builtin_tool_instance(impostor) is False


def _build_execute_run_context(tool_mgr) -> ContextWrapper:
    event = _DummyEvent()
    context = SimpleNamespace(get_llm_tool_manager=lambda: tool_mgr)
    return ContextWrapper(context=SimpleNamespace(event=event, context=context))


@pytest.mark.asyncio
async def test_execute_denies_tool_when_permission_check_fails():
    async def _denying_check(name, ctx):
        return f"error: Permission denied for {name}"

    tool_mgr = SimpleNamespace(check_tool_permission=_denying_check)
    run_context = _build_execute_run_context(tool_mgr)

    called = False

    async def handler(ctx, **kw):
        nonlocal called
        called = True
        return "should not run"

    tool = FunctionTool(
        name="dangerous_tool",
        description="d",
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )

    results = [r async for r in FunctionToolExecutor.execute(tool, run_context)]

    assert not called
    assert len(results) == 1
    assert isinstance(results[0], mcp.types.CallToolResult)
    assert "Permission denied" in results[0].content[0].text


@pytest.mark.asyncio
async def test_execute_invokes_permission_check_and_runs_tool_when_allowed():
    calls = []

    async def _allowing_check(name, ctx):
        calls.append(name)
        return None

    tool_mgr = SimpleNamespace(check_tool_permission=_allowing_check)
    run_context = _build_execute_run_context(tool_mgr)

    async def handler(ctx, **kw):
        return "ok"

    tool = FunctionTool(
        name="plugin_tool",
        description="d",
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )

    results = [r async for r in FunctionToolExecutor.execute(tool, run_context)]

    assert calls == ["plugin_tool"]
    assert len(results) == 1
    assert results[0].content[0].text == "ok"


@pytest.mark.asyncio
async def test_execute_skips_permission_check_for_real_builtin_tool(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []

    async def _recording_check(name, ctx):
        calls.append(name)
        return None

    tool_mgr = SimpleNamespace(check_tool_permission=_recording_check)
    run_context = _build_execute_run_context(tool_mgr)

    async def _fake_call(self, ctx, **kwargs):
        return "stubbed-output"

    monkeypatch.setattr(ExecuteShellTool, "call", _fake_call)
    tool = ExecuteShellTool()

    results = [
        r
        async for r in FunctionToolExecutor.execute(
            tool, run_context, command="echo hi"
        )
    ]

    assert calls == []
    assert results[0].content[0].text == "stubbed-output"


@pytest.mark.asyncio
async def test_execute_falls_back_to_global_llm_tools_when_ctx_lacks_manager(
    monkeypatch: pytest.MonkeyPatch,
):
    """Covers the llm_tools fallback when ctx has no get_llm_tool_manager."""
    calls = []

    async def _recording_check(name, ctx):
        calls.append(name)
        return f"error: Permission denied for {name}"

    fake_global_manager = SimpleNamespace(check_tool_permission=_recording_check)
    monkeypatch.setattr(astr_agent_tool_exec, "llm_tools", fake_global_manager)

    event = _DummyEvent()
    ctx = SimpleNamespace()  # no get_llm_tool_manager
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=ctx))

    called = False

    async def handler(ctx, **kw):
        nonlocal called
        called = True
        return "should not run"

    tool = FunctionTool(
        name="plugin_tool",
        description="d",
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )

    results = [r async for r in FunctionToolExecutor.execute(tool, run_context)]

    assert calls == ["plugin_tool"]
    assert not called
    assert "Permission denied" in results[0].content[0].text


@pytest.mark.asyncio
async def test_execute_end_to_end_denies_admin_tool_for_member_with_real_manager():
    """Same as above but with a real FunctionToolManager + sp config,
    not a mocked check_tool_permission."""
    from astrbot.core import sp

    mgr = FunctionToolManager()
    called = False

    async def handler(ctx, **kw):
        nonlocal called
        called = True
        return "should not run"

    tool = FunctionTool(
        name="real_admin_tool",
        description="d",
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )
    mgr.func_list = [tool]

    sp.put(
        "tool_permissions",
        {"_default": {"real_admin_tool": "admin"}},
        scope="global",
        scope_id="global",
    )
    try:

        class _FakeMemberEvent:
            def is_admin(self) -> bool:
                return False

            def get_sender_id(self) -> str:
                return "member_1"

        context = SimpleNamespace(get_llm_tool_manager=lambda: mgr)
        run_context = ContextWrapper(
            context=SimpleNamespace(event=_FakeMemberEvent(), context=context)
        )

        results = [r async for r in FunctionToolExecutor.execute(tool, run_context)]

        assert not called
        assert "Permission denied" in results[0].content[0].text
    finally:
        sp.put("tool_permissions", {}, scope="global", scope_id="global")


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
