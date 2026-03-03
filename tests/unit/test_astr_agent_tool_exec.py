from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import mcp
import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.message.components import Image


class _DummyEvent:
    def __init__(self, message_components: list[object] | None = None) -> None:
        self.unified_msg_origin = "webchat:FriendMessage:webchat!user!session"
        self.message_obj = SimpleNamespace(message=message_components or [])
        self.role = "assistant"

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
    async for result in FunctionToolExecutor._execute_handoff(
        tool,
        run_context,
        input="hello",
        image_urls=[],
    ):
        results.append(result)

    assert len(results) == 1
    assert captured["max_steps"] == 5


@pytest.mark.asyncio
async def test_build_handoff_toolset_defaults_runtime_to_none():
    event = _DummyEvent([])
    context = SimpleNamespace(
        get_config=lambda **_kwargs: {"provider_settings": {}},
    )
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))
    toolset = FunctionToolExecutor._build_handoff_toolset(run_context, [])
    assert toolset is None


@pytest.mark.asyncio
async def test_wake_main_agent_for_background_result_uses_provider_settings(
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
        return SimpleNamespace(history="[]")

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
        "astrbot.core.astr_agent_tool_exec.persist_agent_history",
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

    await FunctionToolExecutor._wake_main_agent_for_background_result(
        run_context=run_context,
        task_id="task_1",
        tool_name="transfer_to_subagent",
        result_text="ok",
        tool_args={"input": "hello"},
        note="background finished",
        summary_name="subagent-summary",
    )

    cfg = captured["config"]
    assert cfg.tool_call_timeout == 123
    assert cfg.computer_use_runtime == "none"
    assert cfg.add_cron_tools is False
    assert cfg.provider_settings["computer_use_runtime"] == "none"


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
async def test_execute_handoff_background_strict_failover_without_orchestrator():
    run_context = _build_run_context()
    tool = _DummyTool()

    with patch("astrbot.core.astr_agent_tool_exec.asyncio.create_task") as create_task_mock:
        results = []
        async for result in FunctionToolExecutor._execute_handoff_background(
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
    orchestrator = SimpleNamespace(submit_handoff=AsyncMock(side_effect=RuntimeError("boom")))
    event = _DummyEvent([])
    context = SimpleNamespace(subagent_orchestrator=orchestrator)
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))

    with patch("astrbot.core.astr_agent_tool_exec.asyncio.create_task") as create_task_mock:
        results = []
        async for result in FunctionToolExecutor._execute_handoff_background(
            _DummyTool(),
            run_context,
            tool_call_id="call_1",
            input="hello",
        ):
            results.append(result)

    assert len(results) == 1
    assert "error:" in results[0].content[0].text
    create_task_mock.assert_not_called()
