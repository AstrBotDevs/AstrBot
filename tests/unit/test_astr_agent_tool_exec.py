from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import mcp
import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.config.default import DEFAULT_MAX_HANDOFF_CALLS_PER_RUN
from astrbot.core.message.components import Image
from astrbot.core.skills.skill_manager import SkillInfo


class _DummyEvent:
    def __init__(self, message_components: list[object] | None = None) -> None:
        self.unified_msg_origin = "webchat:FriendMessage:webchat!user!session"
        self.message_obj = SimpleNamespace(message=message_components or [])
        self.role = "member"

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value


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
        tool=_DummyTool(),  # type: ignore[arg-type]
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

    _tool_mgr = SimpleNamespace(
        get_builtin_tool=lambda _: SimpleNamespace(
            name="dummy", active=True, parameters={}
        )
    )
    context = SimpleNamespace(
        get_current_chat_provider_id=_fake_get_current_chat_provider_id,
        tool_loop_agent=_fake_tool_loop_agent,
        get_config=lambda **_kwargs: {"provider_settings": {}},
        get_llm_tool_manager=lambda: _tool_mgr,
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

    try:
        toolset = FunctionToolExecutor._build_handoff_toolset(run_context, None)
        assert toolset is not None
        assert "astrbot_list_sandbox_providers" in toolset.names()
        assert "provider_a_screenshot" in toolset.names()
        assert "provider_b_tool" not in toolset.names()
    finally:
        llm_tools.func_list = previous_tools
        FunctionToolExecutor._runtime_computer_tools_cache.clear()


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
async def test_build_handoff_toolset_filters_session_disabled_plugin_tool():
    plugin_tool = FunctionTool(
        name="memorix_tool",
        description="memorix tool",
        parameters={"type": "object", "properties": {}},
        handler_module_path="test_plugin",
        active=True,
    )
    run_context = ContextWrapper(
        context=SimpleNamespace(
            event=_DummyEvent([]),
            context=SimpleNamespace(
                get_config=lambda **_kwargs: {"provider_settings": {"computer_use_runtime": "none"}}
            ),
        )
    )

    with patch(
        "astrbot.core.astr_agent_tool_exec.SessionPluginManager.get_session_plugin_config",
        new=AsyncMock(return_value={"disabled_plugins": ["astrbot_plugin_memorix"]}),
    ) as mock_get_config, patch(
        "astrbot.core.astr_agent_tool_exec.llm_tools"
    ) as mock_llm_tools, patch(
        "astrbot.core.astr_agent_tool_exec.star_map"
    ) as mock_star_map:
        mock_llm_tools.func_list = [plugin_tool]
        mock_plugin = MagicMock()
        mock_plugin.name = "astrbot_plugin_memorix"
        mock_plugin.reserved = False
        mock_star_map.get.return_value = mock_plugin

        toolset = await FunctionToolExecutor._build_handoff_toolset(run_context, None)

    mock_get_config.assert_awaited_once()
    assert toolset is None


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

    _tool_mgr = SimpleNamespace(
        get_builtin_tool=lambda _: SimpleNamespace(
            name="dummy", active=True, parameters={}
        )
    )
    context = SimpleNamespace(
        get_current_chat_provider_id=_fake_get_current_chat_provider_id,
        tool_loop_agent=_fake_tool_loop_agent,
        get_config=lambda **_kwargs: {"provider_settings": {}},
        get_llm_tool_manager=lambda: _tool_mgr,
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


def test_build_handoff_skills_prompt_filters_selected_skills(
    monkeypatch: pytest.MonkeyPatch,
):
    manager = SimpleNamespace(
        list_skills=lambda **_kwargs: [
            SkillInfo(
                name="web-search-skill",
                description="Search the web",
                path="/skills/web-search-skill/SKILL.md",
                active=True,
            ),
            SkillInfo(
                name="other-skill",
                description="Other work",
                path="/skills/other-skill/SKILL.md",
                active=True,
            ),
        ],
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_tool_exec.SkillManager",
        lambda: manager,
    )

    prompt = FunctionToolExecutor._build_handoff_skills_prompt(
        ["web-search-skill"],
        "local",
    )

    assert "web-search-skill" in prompt
    assert "Search the web" in prompt
    assert "other-skill" not in prompt


@pytest.mark.asyncio
async def test_execute_handoff_appends_agent_skills_prompt(
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
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))
    tool = SimpleNamespace(
        name="transfer_to_subagent",
        provider_id=None,
        agent=SimpleNamespace(
            name="subagent",
            tools=[],
            skills=["web-search-skill"],
            instructions="subagent-instructions",
            begin_dialogs=[],
            run_hooks=None,
        ),
    )
    monkeypatch.setattr(
        FunctionToolExecutor,
        "_build_handoff_skills_prompt",
        classmethod(lambda cls, skill_names, runtime: "SKILL PROMPT"),
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
    assert captured["system_prompt"] == "subagent-instructions\n\nSKILL PROMPT"


def test_build_handoff_system_prompt_omits_empty_parts(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        FunctionToolExecutor,
        "_build_handoff_skills_prompt",
        classmethod(lambda cls, skill_names, runtime: "SKILL PROMPT\n"),
    )

    prompt = FunctionToolExecutor._build_handoff_system_prompt(
        "  ",
        ["web-search-skill"],
        "local",
    )

    assert prompt == "SKILL PROMPT"


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
async def test_execute_handoff_rejects_empty_input():
    async def _fake_get_current_chat_provider_id(_umo):
        return "provider-id"

    async def _fake_tool_loop_agent(**_kwargs):
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

    results = []
    async for result in FunctionToolExecutor._execute_handoff(
        tool,
        run_context,
        image_urls_prepared=True,
        input="   ",
        image_urls=[],
    ):
        results.append(result)

    assert len(results) == 1
    assert isinstance(results[0], mcp.types.CallToolResult)
    text_content = results[0].content[0]
    assert isinstance(text_content, mcp.types.TextContent)
    assert "missing_or_empty_input" in text_content.text


@pytest.mark.asyncio
async def test_execute_handoff_falls_back_to_current_provider_when_configured_missing():
    captured: dict = {}

    class _DummyProviderManager:
        async def get_provider_by_id(self, _provider_id: str):
            return None

    async def _fake_get_current_chat_provider_id(_umo):
        return "fallback-provider"

    async def _fake_tool_loop_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(completion_text="ok")

    context = SimpleNamespace(
        provider_manager=_DummyProviderManager(),
        get_current_chat_provider_id=_fake_get_current_chat_provider_id,
        tool_loop_agent=_fake_tool_loop_agent,
        get_config=lambda **_kwargs: {"provider_settings": {}},
    )
    event = _DummyEvent([])
    run_context = ContextWrapper(context=SimpleNamespace(event=event, context=context))
    tool = SimpleNamespace(
        name="transfer_to_subagent",
        provider_id="missing-provider-id",
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
    assert captured["chat_provider_id"] == "fallback-provider"
