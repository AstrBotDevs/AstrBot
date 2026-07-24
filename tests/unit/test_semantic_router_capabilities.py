from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from data.plugins.astrbot_plugin_semantic_router.control_plane import (
    AGENT_EXECUTION_POLICY_EXTRA_KEY,
    ROLE_OWNER,
    ROUTE_STANDARD,
    AgentControlPlane,
)
from data.plugins.astrbot_plugin_semantic_router.main import (
    AgentJobControlTool,
    RouteDecision,
    SemanticRouterPlugin,
)


def test_agent_job_control_tool_retains_owner_after_pydantic_init() -> None:
    owner = object()
    tool = AgentJobControlTool(owner, "agent_job_status")

    assert tool.plugin is owner
    assert tool.operation == "agent_job_status"


def test_invalid_capability_seed_is_quarantined_and_falls_back(tmp_path) -> None:
    runtime_seed = tmp_path / "plugin_capabilities.json"
    bundle_seed = tmp_path / "bundle.json"
    runtime_seed.write_text('{"capabilities": [', encoding="utf-8")
    bundle_seed.write_text(
        '{"capabilities": [{"id": "demo", "plugin": "demo"}]}',
        encoding="utf-8",
    )
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.capability_path = runtime_seed
    plugin.capability_bundle_path = bundle_seed

    loaded = plugin._load_capabilities()

    assert loaded == [{"id": "demo", "plugin": "demo"}]
    assert runtime_seed.exists()
    assert '"demo"' in runtime_seed.read_text(encoding="utf-8")
    assert list(tmp_path.glob("plugin_capabilities.invalid-*.json"))


def test_live_capability_rescan_separates_contract_failures_and_risk(tmp_path) -> None:
    store = __import__(
        "data.plugins.astrbot_plugin_semantic_router.control_plane",
        fromlist=["ControlPlaneStore"],
    ).ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    tools = [
        SimpleNamespace(
            name="public_lookup",
            description="Read public facts",
            parameters={"type": "object", "properties": {}},
            handler_module_path="plugin.lookup",
        ),
        SimpleNamespace(
            name="write_file",
            description="Write a file",
            parameters={"type": "object", "properties": {}},
            handler_module_path="plugin.files",
        ),
        SimpleNamespace(
            name="broken_tool",
            description="",
            parameters={"type": "not-a-schema"},
            handler_module_path="plugin.broken",
        ),
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.store = store
    plane.context = SimpleNamespace(
        get_llm_tool_manager=lambda: SimpleNamespace(func_list=tools),
        get_all_stars=lambda: [],
    )

    counts = plane.rescan_capabilities()
    records = {item["name"]: item for item in store.capabilities()}

    assert counts["registered_commands"] >= 0
    assert records["public_lookup"]["status"] == "active"
    assert records["public_lookup"]["risk"] == "R0"
    assert records["write_file"]["status"] == "pending"
    assert records["write_file"]["risk"] == "R4"
    assert records["broken_tool"]["status"] == "pending"


def test_control_plane_audits_plan_trace_and_delivery_hash(tmp_path) -> None:
    store = __import__(
        "data.plugins.astrbot_plugin_semantic_router.control_plane",
        fromlist=["ControlPlaneStore"],
    ).ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    principal = SimpleNamespace(principal_id="aiocqhttp:owner")
    plan = SimpleNamespace(
        principal=principal,
        route=ROUTE_STANDARD,
        reason="semantic-planner-tool",
        provider_id="deepseek/deepseek-v4-pro",
        allowed_tools=["weather_lookup", "anysearch_search", "browser_search"],
        knowledge_mode="off",
        selected_tool="weather_lookup",
        tool_required=True,
        semantic_confidence=0.91,
    )
    store.audit_decision("aiocqhttp:private:1", plan, trace_id="trace-1")
    store.audit_tool(
        principal_id=principal.principal_id,
        umo="aiocqhttp:private:1",
        trace_id="trace-1",
        tool_name="weather_lookup",
        risk="R0",
        status="completed",
        detail="ok",
    )
    store.audit_message_delivery(
        principal_id=principal.principal_id,
        umo="aiocqhttp:private:1",
        trace_id="trace-1",
        status="sent",
        content="天气晴朗",
        component_types="Plain",
    )

    with store._connect() as conn:
        decision = conn.execute(
            "SELECT trace_id, candidate_tools, selected_tool, tool_required "
            "FROM decision_audit"
        ).fetchone()
        tool = conn.execute("SELECT trace_id FROM tool_audit").fetchone()
        delivery = conn.execute(
            "SELECT status, content_hash, duplicate FROM message_delivery_audit"
        ).fetchone()
    assert decision["trace_id"] == "trace-1"
    assert "weather_lookup" in decision["candidate_tools"]
    assert decision["selected_tool"] == "weather_lookup"
    assert decision["tool_required"] == 1
    assert tool["trace_id"] == "trace-1"
    assert delivery["status"] == "sent"
    assert delivery["content_hash"]
    assert delivery["duplicate"] == 0


def test_audio_semantic_state_selects_active_audio_provider() -> None:
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.enforce = True
    plane.fast_provider = "deepseek/deepseek-v4-flash"
    plane.standard_provider = "deepseek/deepseek-v4-pro"
    plane.audio_provider = "google_gemini_bot/gemini-3.1-flash-lite"
    plane._provider_breakers = {}
    plane._tool_breakers = {}
    plane.store = SimpleNamespace(
        get_mode=lambda principal_id, umo: "on",
        capability=lambda name: None,
        capabilities=lambda active_only=False: [],
    )
    plane.select_tools = lambda text, route, role: []
    plane.resolve_principal = lambda event: SimpleNamespace(
        principal_id="aiocqhttp:1",
        role="member",
        restricted=False,
    )
    audio_provider = SimpleNamespace(
        provider_config={
            "id": "google_gemini_bot/gemini-3.1-flash-lite",
            "modalities": ["text", "audio"],
        }
    )
    plane.context = SimpleNamespace(get_all_providers=lambda: [audio_provider])
    event = SimpleNamespace(
        unified_msg_origin="aiocqhttp:private:1",
        get_extra=lambda key, default=None: (
            {
                "intent": "audio",
                "should_use_audio": True,
                "confidence": 0.9,
                "required_evidence": ["audio"],
            }
            if key == "semantic_router_semantic_state"
            else default
        ),
        message_obj=SimpleNamespace(message=[]),
    )

    plan = plane.build_route_plan(event, "")

    assert plan is not None
    assert plan.provider_id == "google_gemini_bot/gemini-3.1-flash-lite"
    assert "audio-capable-provider" in plan.reason


def test_high_confidence_music_capability_precedes_semantic_search() -> None:
    """Domain routing must not turn a concrete music request into search."""

    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.enforce = True
    plane.fast_provider = "deepseek/deepseek-v4-flash"
    plane.standard_provider = "deepseek/deepseek-v4-pro"
    plane.audio_provider = ""
    plane._provider_breakers = {}
    plane._tool_breakers = {}
    plane.custom_intent_routes = {}
    plane.store = SimpleNamespace(
        get_mode=lambda principal_id, umo: "on",
        capability=lambda name: None,
        capabilities=lambda active_only=False: [
            {"name": "find_music", "status": "active", "kind": "tool", "risk": "R0"},
            {
                "name": "deliver_music",
                "status": "active",
                "kind": "tool",
                "risk": "R2",
            },
            {
                "name": "anysearch_search",
                "status": "active",
                "kind": "tool",
                "risk": "R0",
            },
        ],
    )
    plane.select_tools = lambda text, route, role: ["find_music", "deliver_music"]
    plane.resolve_principal = lambda event: SimpleNamespace(
        principal_id="aiocqhttp:owner",
        role=ROLE_OWNER,
        restricted=False,
    )
    plane.context = SimpleNamespace()
    event = SimpleNamespace(
        unified_msg_origin="aiocqhttp:group:1",
        message_obj=SimpleNamespace(message=[]),
        get_extra=lambda key, default=None: (
            {
                "intent": "web_search",
                "should_search": True,
                "confidence": 0.9,
            }
            if key == "semantic_router_semantic_state"
            else default
        ),
    )

    plan = plane.build_route_plan(event, "播放平凡之路")

    assert plan is not None
    assert plan.selected_tool == "find_music"
    assert plan.allowed_tools == ["find_music", "deliver_music"]


@pytest.mark.asyncio
async def test_initialize_preserves_existing_browser_search_tool() -> None:
    existing_tool = object()
    manager = SimpleNamespace(get_tool=lambda name: existing_tool)
    context = SimpleNamespace(
        get_llm_tool_manager=lambda: manager,
        add_llm_tools=MagicMock(),
        activate_llm_tool=MagicMock(),
    )
    control_plane = SimpleNamespace(
        register_diagnostic_tools=MagicMock(),
        rescan_capabilities=MagicMock(return_value={"status_active": 1}),
        enforce=True,
    )
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.context = context
    plugin.control_plane = control_plane
    plugin.search_tool_name = "browser_search"
    plugin.debug = False

    await plugin.initialize()

    context.add_llm_tools.assert_called_once()
    registered_job_tools = context.add_llm_tools.call_args.args
    assert {tool.name for tool in registered_job_tools} == {
        "agent_job_start",
        "agent_job_status",
        "agent_job_result",
        "agent_job_cancel",
    }
    context.activate_llm_tool.assert_called_once_with("browser_search")
    control_plane.rescan_capabilities.assert_called_once()


def test_registered_tool_supports_legacy_manager_interface() -> None:
    expected = object()
    manager = SimpleNamespace(
        get_func=lambda name: expected if name == "search" else None
    )
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.context = SimpleNamespace(get_llm_tool_manager=lambda: manager)

    assert plugin._get_registered_tool("search") is expected


def test_gold_capability_matches_natural_language() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.capabilities = [
        {
            "id": "daily.gold",
            "plugin": "astrbot_plugin_dailyhub",
            "method": "cmd_gold",
            "command": "金价",
            "arg_mode": "none",
            "risk": "safe",
            "triggers": ["今日金价", "金价", "黄金价格"],
        }
    ]
    plugin._rule_music_decision = lambda text: None
    plugin._looks_like_search_meta = lambda text: False
    plugin._normalize_text = lambda text: text.strip()

    decision = plugin._capability_decision(SimpleNamespace(), "今日金价")

    assert decision is not None
    assert decision.intent == "plugin.daily.gold"
    assert decision.action == "cmd_gold"
    assert decision.confidence >= 0.86


def test_known_meme_phrase_triggers_evidence_search_without_question_words() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.meme_auto_search_terms = ["哈基米", "南北绿豆"]
    plugin._looks_like_search_meta = lambda text: False
    plugin._rule_music_decision = lambda text: None
    plugin._normalize_text = lambda text: text.strip()

    query = plugin._extract_search_query("亚托莉，哈基米南北绿豆")

    assert "哈基米南北绿豆" in query
    assert "网络梗" in query
    assert "亚托莉" not in query


@pytest.mark.parametrize(
    "text, expected",
    [
        ("亚托莉，查一下今天北京天气", "北京天气"),
        ("亚托莉，今天国际新闻", "新闻"),
        ("亚托莉，DeepSeek 最新版本", "DeepSeek"),
        ("亚托莉，比特币价格", "比特币"),
        ("亚托莉，美元人民币汇率", "汇率"),
        ("亚托莉，英伟达股票", "英伟达"),
        ("亚托莉，哈基米是什么梗", "网络梗"),
        ("亚托莉，最近小黑盒有什么便宜的吗", "小黑盒"),
    ],
)
def test_current_information_categories_create_search_queries(
    text: str, expected: str
) -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.meme_auto_search_terms = ["哈基米", "南北绿豆"]
    plugin._rule_music_decision = lambda normalized: None

    query = plugin._extract_search_query(text)

    assert query
    assert expected in query


def test_search_configuration_question_does_not_trigger_web_search() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.meme_auto_search_terms = []
    plugin._rule_music_decision = lambda normalized: None

    query = plugin._extract_search_query("亚托莉，搜索功能怎么配置才会触发")

    assert query == ""


def test_generic_music_request_is_not_treated_as_a_song_name() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.music_triggers = ["听一下"]
    plugin.negative_patterns = []

    decision = plugin._rule_music_decision("放几个音乐来听一下")

    assert decision is None


@pytest.mark.parametrize(
    "text", ["来个周杰伦的", "给我来一首晴天", "亚托莉，来首七里香"]
)
def test_implicit_music_intent_selects_playback_tools(text: str) -> None:
    """Recognize action-plus-target music requests without exact phrase rules."""

    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._tool_breakers = {}
    plane._capability_metadata = {}
    plane.custom_intent_routes = {}
    plane.store = SimpleNamespace(
        capabilities=lambda active_only=False: [
            {
                "name": "find_music",
                "status": "active",
                "kind": "tool",
                "risk": "R0",
                "description": "Find a playable song candidate.",
            },
            {
                "name": "deliver_music",
                "status": "active",
                "kind": "tool",
                "risk": "R0",
                "description": "Send the selected song to the current chat.",
            },
        ],
    )

    assert plane.select_tools(text, ROUTE_STANDARD, ROLE_OWNER) == [
        "find_music",
        "deliver_music",
    ]


def test_generic_implicit_music_request_does_not_invent_a_song_title() -> None:
    """A request for an unspecified genre should remain a clarification/chat turn."""

    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._tool_breakers = {}
    plane._capability_metadata = {}
    plane.custom_intent_routes = {}
    plane.store = SimpleNamespace(
        capabilities=lambda active_only=False: [
            {"name": "find_music", "status": "active", "kind": "tool", "risk": "R0"},
            {"name": "deliver_music", "status": "active", "kind": "tool", "risk": "R0"},
        ],
    )

    assert plane.select_tools("来点音乐", ROUTE_STANDARD, ROLE_OWNER) == []


def test_short_implicit_music_request_is_not_forced_into_fast_route() -> None:
    """A short action-plus-target message still selects playback tools."""

    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._tool_breakers = {}
    plane._capability_metadata = {}
    plane.custom_intent_routes = {}
    plane.store = SimpleNamespace(
        capabilities=lambda active_only=False: [
            {"name": "find_music", "status": "active", "kind": "tool", "risk": "R0"},
            {
                "name": "deliver_music",
                "status": "active",
                "kind": "tool",
                "risk": "R0",
            },
        ],
    )

    assert plane.select_tools("来个周杰伦的", ROUTE_STANDARD, ROLE_OWNER) == [
        "find_music",
        "deliver_music",
    ]


def test_daily_fortune_request_selects_terminal_local_tool() -> None:
    """A fortune request must not fall through to the generic web search path."""

    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._tool_breakers = {}
    plane._capability_metadata = {}
    plane.custom_intent_routes = {}
    plane.store = SimpleNamespace(
        capabilities=lambda active_only=False: [
            {
                "name": "get_daily_fortune",
                "status": "active",
                "kind": "tool",
                "risk": "R1",
                "description": "Generate and deliver today's fortune poster.",
            },
            {
                "name": "anysearch_search",
                "status": "active",
                "kind": "tool",
                "risk": "R0",
                "description": "Search the public web.",
            },
        ],
    )

    assert plane.select_tools(
        "\u4eca\u65e5\u8fd0\u52bf", ROUTE_STANDARD, ROLE_OWNER
    ) == ["get_daily_fortune"]


def test_provider_failure_from_successful_fallback_opens_circuit() -> None:
    """A hidden primary failure must still be visible to the circuit breaker."""

    provider = "google_gemini_bot/gemini-3.1-flash-lite"
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._provider_breakers = {}
    plane._recent_failures = {}
    plane.store = SimpleNamespace(
        capability=lambda name: None,
        record_health_event=MagicMock(),
    )
    values = {
        AGENT_EXECUTION_POLICY_EXTRA_KEY: {"provider_id": provider},
        "agent_provider_failures": [
            {"provider_id": provider, "detail": "HTTP 429 rate limit"}
        ],
    }
    event = SimpleNamespace(
        get_extra=lambda key, default=None: values.get(key, default)
    )

    plane.record_provider_result(
        event,
        SimpleNamespace(role="assistant", completion_text="fallback response"),
    )

    assert plane._provider_breakers[provider] > 0
    plane.store.record_health_event.assert_called_once()


@pytest.mark.asyncio
async def test_meme_search_executes_registered_browser_tool_first() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.anysearch_enabled = True
    plugin.direct_search_engine = "bing"
    plugin.direct_search_max_chars = 3200
    plugin._get_registered_tool = lambda name: (
        object() if name == "browser_search" else None
    )
    calls = []

    async def execute(event, tool_name, args, timeout):
        calls.append((tool_name, args, timeout))
        return True, "浏览器搜索完成。\n页面摘要：哈基米是网络流行语。"

    plugin._execute_controlled_tool = execute

    result = await plugin._fetch_search_result(
        SimpleNamespace(), "哈基米 网络梗 含义 出处 常见用法 社区语境"
    )

    assert result["ok"] is True
    assert result["engine"] == "browser_search"
    assert calls[0][0] == "browser_search"
    assert calls[0][2] == 10


@pytest.mark.asyncio
async def test_anysearch_failure_falls_back_to_registered_browser_tool() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.anysearch_enabled = True
    plugin.direct_search_engine = "bing"
    plugin.direct_search_max_chars = 3200
    plugin._get_registered_tool = lambda name: (
        object() if name in {"anysearch_search", "browser_search"} else None
    )
    plugin._fetch_anysearch_result = AsyncMock(
        return_value={"ok": False, "error": "rate limited"}
    )
    plugin.control_plane = SimpleNamespace(_redact=lambda text: text)

    async def execute(event, tool_name, args, timeout):
        return True, "实时金价来源已打开"

    plugin._execute_controlled_tool = execute

    result = await plugin._fetch_search_result(SimpleNamespace(), "今日国际金价")

    assert result["ok"] is True
    assert result["engine"] == "browser_search"
    assert result["fallback_from"] == "anysearch"
    assert result["fallback_reason"] == "rate limited"


def test_anysearch_parser_keeps_publication_time() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.search_context_max_items = 8
    content = (
        "## Search Results (1 result)\n\n"
        "### 1. Official release notes\n"
        "- **URL**: https://developer.example.com/releases\n"
        "- **Published Time**: 2026-07-21\n"
        "- Stable release details.\n"
    )

    items = plugin._anysearch_result_items(content)

    assert items == [
        {
            "title": "Official release notes",
            "snippet": "Stable release details.",
            "source": "https://developer.example.com/releases",
            "published": "2026-07-21",
        }
    ]


@pytest.mark.asyncio
async def test_anysearch_uses_prefixed_mcp_only_when_plugin_tool_is_missing() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.search_context_max_items = 5
    plugin.direct_search_max_chars = 3200
    plugin.anysearch_timeout = 12
    plugin._get_registered_tool = lambda name: (
        object() if name == "mcp_anysearch_search" else None
    )
    calls = []

    async def execute(event, tool_name, args, timeout):
        calls.append(tool_name)
        return True, "## Search Results (1 result)\n\n### 1. Result"

    plugin._execute_controlled_tool = execute

    result = await plugin._fetch_anysearch_result(SimpleNamespace(), "latest release")

    assert result["ok"] is True
    assert calls == ["mcp_anysearch_search"]


@pytest.mark.asyncio
async def test_legacy_music_and_image_fallbacks_use_tool_manager_only() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    calls = []

    def get_tool(name):
        return object() if name in {"find_music", "understand_current_images"} else None

    async def execute(event, tool_name, args, timeout):
        calls.append((tool_name, args, timeout))
        return True, f"controlled:{tool_name}"

    plugin._get_registered_tool = get_tool
    plugin._execute_controlled_tool = execute
    event = SimpleNamespace(plain_result=lambda text: text)

    music_results = [
        result async for result in plugin._call_music_plugin(event, "晴天")
    ]
    image_results = [
        result
        async for result in plugin._call_image_understanding_plugin(
            event, "这张图什么意思"
        )
    ]

    assert music_results == ["controlled:find_music"]
    assert image_results == ["controlled:understand_current_images"]
    assert calls == [
        ("find_music", {"title": "晴天"}, 15),
        ("understand_current_images", {"prompt": "这张图什么意思"}, 30),
    ]


def test_common_atri_spelling_variants_are_wake_aliases() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)

    assert plugin._search_wake_text("亚托里，帮我查一下天气")
    assert plugin._search_wake_text("阿托里在吗")
    assert plugin._search_wake_text("亚托，看看这个")
    assert plugin._image_wake_text("萝卜子看看图")


def test_image_failure_report_does_not_select_sticker_tools() -> None:
    control_plane = AgentControlPlane.__new__(AgentControlPlane)
    control_plane.store = SimpleNamespace(
        capabilities=lambda active_only=True: [
            {"name": "search_emoji", "risk": "R0", "description": ""},
            {"name": "list_stickers", "risk": "R0", "description": ""},
        ]
    )

    tools = control_plane.select_tools(
        "完蛋咯，有图片表情包这些炸了", ROUTE_STANDARD, ROLE_OWNER
    )

    assert tools == []


@pytest.mark.asyncio
async def test_dailyhub_route_binds_source_from_semantic_request() -> None:
    """A live-source capability receives the required source argument."""

    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    tool = SimpleNamespace(
        name="get_daily_news",
        parameters={
            "type": "object",
            "properties": {"source": {"type": "string"}},
            "required": ["source"],
        },
    )
    plugin._get_registered_tool = lambda name: tool if name == tool.name else None
    captured: list[tuple[str, dict[str, str]]] = []

    async def execute(_event, tool_name, arguments, timeout):
        captured.append((tool_name, arguments))
        assert timeout == 15
        return True, "ok"

    plugin._execute_controlled_tool = execute
    extras: dict[str, object] = {}
    event = SimpleNamespace(
        message_str="亚托莉，查一下今日金价",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
        plain_result=lambda text: text,
    )
    decision = RouteDecision(
        intent="get_daily_news", action="daily_news", argument="", confidence=1.0
    )

    results = [result async for result in plugin._call_capability(event, decision)]

    assert captured == [("get_daily_news", {"source": "金价"})]
    assert results == ["ok"]
