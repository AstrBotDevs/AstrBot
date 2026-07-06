from types import SimpleNamespace
from unittest.mock import AsyncMock

import mcp
import pytest

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.message.components import Image
from astrbot.core.provider.func_tool_manager import (
    FunctionToolManager,
    _PermissionGuardedTool,
)
from astrbot.core.provider.register import llm_tools


class _DummyEvent:
    def __init__(self, message_components: list[object] | None = None) -> None:
        self.unified_msg_origin = "webchat:FriendMessage:webchat!user!session"
        self.message_obj = SimpleNamespace(message=message_components or [])
        self.role = "member"

    def get_extra(self, _key: str):
        return None


class _NoopRunner:
    async def step_until_done(self, _limit: int):
        if False:
            yield None

    def get_final_llm_resp(self):
        return None


class _DummyTool:
    def __init__(self) -> None:
        self.name = "transfer_to_subagent"
        self.agent = SimpleNamespace(name="subagent")


def _build_run_context(message_components: list[object] | None = None):
    event = _DummyEvent(message_components=message_components)
    ctx = SimpleNamespace(event=event, context=SimpleNamespace())
    return ContextWrapper(context=ctx)


class _DoneRunner:
    async def step_until_done(self, _max_step):
        for item in ():
            yield item

    def get_final_llm_resp(self):
        return SimpleNamespace(role="assistant", completion_text="done")


def test_build_handoff_toolset_keeps_permission_guards_for_default_tools():
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
    assert isinstance(toolset.get_tool("admin_only_mcp"), _PermissionGuardedTool)
    assert toolset.get_tool("transfer_to_child") is None


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
async def test_build_handoff_toolset_uses_registered_provider_tools_only(
    monkeypatch: pytest.MonkeyPatch,
):
    from astrbot.core.agent.tool import FunctionTool
    from astrbot.core.computer import computer_client

    registered_provider_tool = FunctionTool(
        name="provider_a_screenshot",
        parameters={"type": "object", "properties": {}},
        description="Provider A screenshot",
    )
    registered_provider_tool.sandbox_provider_id = "provider_a"
    unregistered_provider_tool = FunctionTool(
        name="provider_b_tool",
        parameters={"type": "object", "properties": {}},
        description="Provider B tool",
    )
    unregistered_provider_tool.sandbox_provider_id = "provider_b"

    previous_tools = list(llm_tools.func_list)
    FunctionToolExecutor._runtime_computer_tools_cache.clear()
    llm_tools.func_list = [registered_provider_tool]

    tool_mgr = SimpleNamespace(
        get_builtin_tool=lambda cls, **kwargs: cls(**kwargs),
        get_func=lambda name: {
            "provider_a_screenshot": registered_provider_tool,
            "provider_b_tool": unregistered_provider_tool,
        }.get(name),
    )
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {"booter": "provider_a"},
            }
        },
        get_llm_tool_manager=lambda: tool_mgr,
    )
    event = _DummyEvent([])
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))
    monkeypatch.setattr(
        computer_client,
        "list_sandbox_providers",
        lambda: [
            {"provider_id": "provider_b", "tool_names": ["provider_b_tool"]},
        ],
    )
    monkeypatch.setattr(
        computer_client,
        "get_current_sandbox_provider_id",
        lambda _session_id: "provider_a",
    )

    try:
        toolset = FunctionToolExecutor._build_handoff_toolset(run_context, None)
        assert toolset is not None
        assert "astrbot_sandbox_query" in toolset.names()
        assert "provider_a_screenshot" in toolset.names()
        assert "provider_b_tool" not in toolset.names()
    finally:
        llm_tools.func_list = previous_tools
        FunctionToolExecutor._runtime_computer_tools_cache.clear()


@pytest.mark.asyncio
async def test_build_handoff_toolset_filters_registered_provider_tools_each_build(
    monkeypatch: pytest.MonkeyPatch,
):
    from astrbot.core.computer import computer_client

    provider_tool = FunctionTool(
        name="provider_a_screenshot",
        parameters={"type": "object", "properties": {}},
        description="Provider A screenshot",
    )
    provider_tool.sandbox_provider_id = "provider_a"

    previous_tools = list(llm_tools.func_list)
    FunctionToolExecutor._runtime_computer_tools_cache.clear()
    llm_tools.func_list = [provider_tool]

    tool_mgr = SimpleNamespace(
        func_list=[provider_tool],
        get_builtin_tool=lambda cls, **kwargs: cls(**kwargs),
        get_func=lambda name: provider_tool if name == provider_tool.name else None,
    )
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {"computer_use_runtime": "sandbox"}
        },
        get_llm_tool_manager=lambda: tool_mgr,
    )
    event = _DummyEvent([])
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))

    current_provider = "provider_a"

    def get_current_provider(_session_id):
        return current_provider

    monkeypatch.setattr(
        computer_client,
        "get_current_sandbox_provider_id",
        get_current_provider,
    )

    try:
        matching = FunctionToolExecutor._build_handoff_toolset(run_context, None)
        current_provider = "provider_b"
        non_matching = FunctionToolExecutor._build_handoff_toolset(run_context, None)
        current_provider = "provider_a"
        matching_again = FunctionToolExecutor._build_handoff_toolset(run_context, None)

        assert matching is not None
        assert non_matching is not None
        assert matching_again is not None
        assert "provider_a_screenshot" in matching.names()
        assert "provider_a_screenshot" not in non_matching.names()
        assert "provider_a_screenshot" in matching_again.names()
    finally:
        llm_tools.func_list = previous_tools
        FunctionToolExecutor._runtime_computer_tools_cache.clear()


@pytest.mark.asyncio
async def test_build_handoff_toolset_uses_scoped_tool_manager_for_all_tools():
    from astrbot.core.agent.tool import FunctionTool

    allowed_tool = FunctionTool(
        name="allowed_tool",
        parameters={"type": "object", "properties": {}},
        description="allowed",
    )
    disallowed_tool = FunctionTool(
        name="disallowed_tool",
        parameters={"type": "object", "properties": {}},
        description="disallowed",
    )
    previous_tools = list(llm_tools.func_list)
    FunctionToolExecutor._runtime_computer_tools_cache.clear()
    llm_tools.func_list = [allowed_tool, disallowed_tool]
    tool_mgr = SimpleNamespace(func_list=[allowed_tool], get_func=lambda name: None)
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {"computer_use_runtime": "none"}
        },
        get_llm_tool_manager=lambda: tool_mgr,
    )
    run_context = ContextWrapper(
        context=SimpleNamespace(event=_DummyEvent([]), context=context)
    )

    try:
        toolset = FunctionToolExecutor._build_handoff_toolset(run_context, None)
        assert toolset is not None
        assert "allowed_tool" in toolset.names()
        assert "disallowed_tool" not in toolset.names()
    finally:
        llm_tools.func_list = previous_tools
        FunctionToolExecutor._runtime_computer_tools_cache.clear()


def test_clear_runtime_computer_tools_cache_provider_id_clears_all_entries():
    FunctionToolExecutor._runtime_computer_tools_cache = {
        (1, "sandbox", ""): {},
        (2, "local", "other"): {},
    }

    FunctionToolExecutor.clear_runtime_computer_tools_cache("generic")

    assert FunctionToolExecutor._runtime_computer_tools_cache == {}


@pytest.mark.asyncio
async def test_background_wake_preserves_computer_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    async def _fake_get_session_conv(**_kwargs):
        return SimpleNamespace(history="[]")

    async def _fake_build_main_agent(**kwargs):
        captured["config"] = kwargs["config"]
        return SimpleNamespace(agent_runner=_NoopRunner())

    async def _fake_persist_agent_history(*_args, **_kwargs):
        return None

    provider_settings = {
        "computer_use_runtime": "sandbox",
        "sandbox": {"booter": "generic", "max_sandboxes": 2},
        "stream": True,
    }
    context = SimpleNamespace(
        conversation_manager=SimpleNamespace(),
        get_config=lambda **_kwargs: {"provider_settings": provider_settings},
        get_llm_tool_manager=lambda: SimpleNamespace(
            get_builtin_tool=lambda _cls: SimpleNamespace(
                name="send_message_to_user", active=True
            )
        ),
    )
    run_context = ContextWrapper(
        context=SimpleNamespace(event=_DummyEvent([]), context=context),
        tool_call_timeout=17,
    )

    monkeypatch.setattr(
        "astrbot.core.astr_main_agent._get_session_conv", _fake_get_session_conv
    )
    monkeypatch.setattr(
        "astrbot.core.astr_main_agent.build_main_agent", _fake_build_main_agent
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_tool_exec.persist_agent_history",
        _fake_persist_agent_history,
    )

    await FunctionToolExecutor._wake_main_agent_for_background_result(
        run_context,
        task_id="task-id",
        tool_name="tool",
        result_text="result",
        tool_args={},
        note="note",
        summary_name="tool",
    )

    config = captured["config"]
    assert config.computer_use_runtime == "sandbox"
    assert config.sandbox_cfg == {"booter": "generic", "max_sandboxes": 2}
    assert config.provider_settings == provider_settings


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
async def test_background_wakeup_passes_provider_settings_to_main_agent(
    monkeypatch: pytest.MonkeyPatch,
):
    provider_settings = {
        "fallback_chat_models": ["fallback-provider"],
        "request_max_retries": 3,
        "stream": True,
    }
    captured: dict = {}

    async def _fake_get_session_conv(**_kwargs):
        return SimpleNamespace(history="[]")

    async def _fake_build_main_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(agent_runner=_DoneRunner())

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

    await FunctionToolExecutor._wake_main_agent_for_background_result(
        run_context,
        task_id="task-id",
        tool_name="long_tool",
        result_text="ok",
        tool_args={},
        note="task finished",
        summary_name="BackgroundTask",
    )

    config = captured["config"]
    assert config.tool_call_timeout == 456
    assert config.streaming_response == provider_settings["stream"]
    assert config.provider_settings == provider_settings
    assert config.provider_settings["fallback_chat_models"] == ["fallback-provider"]


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
