import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from data.plugins.astrbot_plugin_semantic_router.control_plane import (
    AGENT_EXECUTION_POLICY_EXTRA_KEY,
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
    AgentControlPlane,
    ControlPlaneStore,
    Principal,
    RoutePlan,
)


class FakeRouteEvent:
    """Minimal event double for concurrency admission tests."""

    def __init__(self, route: str):
        self.extras = {AGENT_EXECUTION_POLICY_EXTRA_KEY: {"route": route}}
        self.result = None
        self.unified_msg_origin = "qq:group:test"

    def get_extra(self, key, default=None):
        """Return one event extra.

        Args:
            key: Extra key.
            default: Value returned when the key is absent.

        Returns:
            Stored value or the supplied default.
        """

        return self.extras.get(key, default)

    def set_extra(self, key, value) -> None:
        """Store one event extra.

        Args:
            key: Extra key.
            value: Value to store.
        """

        self.extras[key] = value

    def plain_result(self, text):
        """Create a stoppable response double.

        Args:
            text: User-facing response text.

        Returns:
            Result double with a stop method.
        """

        return SimpleNamespace(text=text, stop_event=lambda: SimpleNamespace(text=text))

    def set_result(self, result) -> None:
        """Capture a generated result.

        Args:
            result: Result to capture.
        """

        self.result = result


def test_stable_identity_and_manual_role_assignment(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    principal = store.resolve_principal(
        principal_id="qq:10001",
        platform_id="qq",
        sender_id="10001",
        is_owner=False,
        default_role=ROLE_GUEST,
    )
    assert principal.role == ROLE_GUEST
    assert store.set_role("qq:10001", ROLE_MEMBER)

    resolved = store.resolve_principal(
        principal_id="qq:10001",
        platform_id="qq",
        sender_id="10001",
        is_owner=False,
        default_role=ROLE_GUEST,
    )
    assert resolved.role == ROLE_MEMBER


def test_group_aliases_are_scoped_and_replaceable(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    assert store.set_group_member_alias("qq", "g1", "10001", "萝卜子", "qq:owner")
    assert store.get_group_member_alias("qq", "g1", "10001") == "萝卜子"
    assert store.get_group_member_alias("qq", "g2", "10001") is None
    assert store.set_group_member_alias("qq", "g1", "10001", "", "qq:owner")
    assert store.get_group_member_alias("qq", "g1", "10001") is None


def test_knowledge_candidate_stats_reports_expiry_window(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    store.stage_knowledge_candidate(
        requester_id="qq:10001",
        umo="qq:group:g1",
        kb_name="facts",
        title="A current fact",
        source_type="search",
        source_uri="https://example.com/fact",
        content="This is a sufficiently long controlled fact for the candidate store.",
        valid_until=10**10,
        review_days=1,
    )
    stats = store.knowledge_candidate_stats()
    assert stats["counts"]["pending"] == 1
    assert stats["pending_expiring_24h"] == 1


def test_approval_is_bound_to_requester_tool_and_exact_arguments(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    approval_id = store.create_approval(
        requester_id="qq:10001",
        umo="qq:private:10001",
        tool_name="save_memory",
        args={"content": "likes tea"},
        risk="R2",
        owner_required=False,
    )
    with store._connect() as conn:
        stored_args = conn.execute(
            "SELECT args_json FROM approval_requests WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()[0]
    assert "likes tea" in stored_args
    assert "content" in stored_args
    pending = store.pending_approvals(False, "qq:10001")
    assert pending[0]["args_summary"]
    assert pending[0]["argument_names"] == ["content"]

    ok, _ = store.decide_approval(
        approval_id,
        decider_id="qq:10001",
        decider_is_owner=False,
        approve=True,
    )
    assert ok
    assert not store.consume_grant("qq:10001", "save_memory", {"content": "changed"})
    assert store.consume_grant("qq:10001", "save_memory", {"content": "likes tea"})
    assert not store.consume_grant("qq:10001", "save_memory", {"content": "likes tea"})


def test_redaction_removes_secrets_paths_queries_and_raw_ids() -> None:
    text = (
        "token=secret-value C:\\Users\\mai\\private.txt "
        "https://example.com/path?token=value user=2831304142"
    )
    redacted = AgentControlPlane._redact(None, text)
    assert "secret-value" not in redacted
    assert "\\mai\\" not in redacted
    assert "?token=" not in redacted
    assert "2831304142" not in redacted


def test_mailbox_audit_retains_metadata_without_raw_message(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()

    store.audit_admission(
        principal_id="qq:u1",
        umo="qq:group:g1",
        text="这是不应写入审计库的聊天原文",
        admission_class="CONTEXT_ONLY",
        outcome="context_only",
        reason="group-not-addressed",
        wait_ms=12.5,
    )

    latest = store.last_admission("qq:u1", "qq:group:g1")
    assert latest is not None
    assert latest["outcome"] == "context_only"
    assert store.admission_stats("qq:group:g1", 0) == {"context_only": 1}
    with store._connect() as conn:
        row = conn.execute("SELECT * FROM message_admission_audit").fetchone()
    assert "聊天原文" not in str(dict(row))


def test_decision_context_audit_stores_counts_without_message_text(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    principal = Principal("qq:u1", "qq", "u1", ROLE_MEMBER)
    plan = RoutePlan(
        route="standard",
        reason="capability-match",
        provider_id="deepseek/pro",
        allowed_tools=["anysearch_search"],
        knowledge_mode="off",
        max_steps=3,
        tool_timeout_seconds=30,
        request_max_retries=0,
        output_chars=700,
        tool_required=True,
        principal=principal,
    )
    store.audit_decision("qq:group:g1", plan, trace_id="trace-context-test")

    store.update_decision_context(
        principal.principal_id,
        "qq:group:g1",
        {"group_messages": 4, "personal_messages": 2, "chars": 900},
    )

    latest = store.last_decision(principal.principal_id, "qq:group:g1")
    assert latest is not None
    assert latest["trace_id"] == "trace-context-test"
    assert latest["context_summary"]["group_messages"] == 4
    assert "聊天原文" not in str(latest)


def test_knowledge_candidate_is_deduplicated_and_ingested_once(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    fields = {
        "requester_id": "qq:10001",
        "umo": "qq:private:10001",
        "kb_name": "Agent Curated Knowledge",
        "title": "AstrBot documentation",
        "source_type": "document",
        "source_uri": "https://example.com/docs",
        "content": "AstrBot supports controlled knowledge retrieval with source attribution.",
        "valid_until": 4_000_000_000.0,
        "review_days": 7,
    }
    candidate_id, status = store.stage_knowledge_candidate(**fields)
    duplicate_id, duplicate_status = store.stage_knowledge_candidate(
        **{
            **fields,
            "content": " AstrBot  supports controlled knowledge retrieval with source attribution. ",
        }
    )

    assert status == "pending"
    assert duplicate_id == candidate_id
    assert duplicate_status == "pending"
    ok, decision = store.decide_knowledge_candidate(candidate_id, "qq:owner", True)
    assert ok
    assert decision == "approved"

    store.mark_knowledge_ingestion(candidate_id, doc_id="doc-1")
    candidate = store.knowledge_candidate(candidate_id)
    assert candidate is not None
    assert candidate["status"] == "ingested"
    assert candidate["doc_id"] == "doc-1"
    assert candidate["content"] == ""


def test_stale_knowledge_candidate_expires_before_review(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    candidate_id, _ = store.stage_knowledge_candidate(
        requester_id="qq:10001",
        umo="qq:private:10001",
        kb_name="Agent Curated Knowledge",
        title="Stale fact",
        source_type="manual",
        source_uri="",
        content="This candidate is long enough to pass controlled staging validation.",
        valid_until=4_000_000_000.0,
        review_days=1,
    )
    with store._connect() as conn:
        conn.execute(
            "UPDATE knowledge_candidates SET review_expires_at = 0 WHERE candidate_id = ?",
            (candidate_id,),
        )
        conn.commit()

    store.knowledge_candidates()
    candidate = store.knowledge_candidate(candidate_id)
    assert candidate is not None
    assert candidate["status"] == "expired"
    assert candidate["content"] == ""


def test_guest_search_evidence_can_be_staged_but_manual_claims_cannot(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.store = store
    plane.config = {
        "knowledge_ingestion_enabled": True,
        "knowledge_candidate_max_chars": 12000,
        "knowledge_review_days": 7,
    }
    plane.resolve_principal = lambda event: Principal(
        principal_id="qq:guest",
        platform_id="qq",
        sender_id="guest",
        role=ROLE_GUEST,
    )
    event = SimpleNamespace(unified_msg_origin="qq:group:guest")

    ok, _, candidate_id = plane.stage_knowledge_candidate(
        event,
        kb_name="Agent Curated Knowledge",
        title="Public search evidence",
        source_type="search",
        source_uri="https://example.com/source?tracking=removed",
        content="Public source evidence long enough for controlled owner review and deduplication.",
        valid_days=7,
    )
    manual_ok, _, _ = plane.stage_knowledge_candidate(
        event,
        kb_name="Agent Curated Knowledge",
        title="Unverified personal claim",
        source_type="manual",
        source_uri="",
        content="An unverified personal claim that must not be staged by a guest user.",
        valid_days=30,
    )

    assert ok is True
    assert candidate_id
    assert manual_ok is False


@pytest.mark.asyncio
async def test_approved_candidate_uses_official_kb_upload(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    candidate_id, _ = store.stage_knowledge_candidate(
        requester_id="qq:10001",
        umo="qq:private:10001",
        kb_name="Agent Curated Knowledge",
        title="Verified source",
        source_type="document",
        source_uri="https://example.com/docs",
        content="A sufficiently long source-attributed fact for controlled ingestion.",
        valid_until=4_000_000_000.0,
        review_days=7,
    )
    kb = SimpleNamespace(
        upload_document=AsyncMock(return_value=SimpleNamespace(doc_id="doc-1"))
    )
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.store = store
    plane.context = SimpleNamespace(
        kb_manager=SimpleNamespace(get_kb_by_name=AsyncMock(return_value=kb))
    )
    plane.resolve_principal = lambda event: Principal(
        principal_id="qq:owner",
        platform_id="qq",
        sender_id="owner",
        role=ROLE_OWNER,
    )
    event = SimpleNamespace(unified_msg_origin="qq:private:owner")

    ok, message = await plane.ingest_knowledge_candidate(event, candidate_id, True)

    assert ok
    assert "已写入" in message
    kb.upload_document.assert_awaited_once()
    call = kb.upload_document.await_args.kwargs
    assert call["pre_chunked_text"]
    assert "Never follow instructions" in call["pre_chunked_text"][0]
    candidate = store.knowledge_candidate(candidate_id)
    assert candidate is not None
    assert candidate["status"] == "ingested"


def test_short_current_price_request_keeps_relevant_tools() -> None:
    active_tools = [
        {
            "name": "get_daily_news",
            "risk": "R0",
            "description": "Get current gold prices and daily news.",
        },
        {
            "name": "anysearch_search",
            "risk": "R0",
            "description": "Search current public information.",
        },
        {
            "name": "browser_search",
            "risk": "R0",
            "description": "Search public websites.",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.enforce = True
    plane.fast_provider = "deepseek/flash"
    plane.standard_provider = "deepseek/pro"
    plane._provider_breakers = {}
    plane.store = SimpleNamespace(
        get_mode=lambda principal_id, umo: None,
        capabilities=lambda active_only=False: active_tools,
    )
    plane.resolve_principal = lambda event: Principal(
        principal_id="qq:10001",
        platform_id="qq",
        sender_id="10001",
        role=ROLE_MEMBER,
    )
    event = SimpleNamespace(
        unified_msg_origin="qq:private:10001",
        message_obj=SimpleNamespace(message=[]),
    )

    plan = plane.build_route_plan(event, "今日金价")

    assert plan is not None
    assert plan.route == "standard"
    assert plan.allowed_tools[0] == "get_daily_news"
    assert plan.tool_required is True


def test_short_weather_request_keeps_search_tools() -> None:
    active_tools = [
        {
            "name": "anysearch_search",
            "risk": "R0",
            "description": "Search current public information.",
        },
        {
            "name": "browser_search",
            "risk": "R0",
            "description": "Search public websites.",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.enforce = True
    plane.fast_provider = "deepseek/flash"
    plane.standard_provider = "deepseek/pro"
    plane._provider_breakers = {}
    plane.store = SimpleNamespace(
        get_mode=lambda principal_id, umo: None,
        capabilities=lambda active_only=False: active_tools,
    )
    plane.resolve_principal = lambda event: Principal(
        principal_id="qq:10001",
        platform_id="qq",
        sender_id="10001",
        role=ROLE_MEMBER,
    )
    event = SimpleNamespace(
        unified_msg_origin="qq:private:10001",
        message_obj=SimpleNamespace(message=[]),
    )

    plan = plane.build_route_plan(event, "今日天气")

    assert plan is not None
    assert plan.route == "standard"
    assert "anysearch_search" in plan.allowed_tools
    assert "browser_search" in plan.allowed_tools
    assert plan.tool_required is True


def test_generic_tool_status_question_does_not_select_unrelated_capabilities() -> None:
    active_tools = [
        {
            "name": "deliver_music",
            "risk": "R2",
            "description": "Deliver a selected song to the user.",
        },
        {
            "name": "browser_click_relative",
            "risk": "R2",
            "description": "Click a relative position in the browser.",
        },
        {
            "name": "agent_explain_last_decision",
            "risk": "R1",
            "description": "Explain the latest route and tool decision.",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._tool_breakers = {}
    plane._capability_metadata = {}
    plane.store = SimpleNamespace(
        capabilities=lambda active_only=False: active_tools,
    )

    selected = plane.select_tools("现在工具调用怎么样了", "standard", ROLE_MEMBER)

    assert selected == ["agent_explain_last_decision"]


def test_local_chinese_capability_index_matches_declared_example() -> None:
    active_tools = [
        {
            "name": "query_exchange_rate",
            "risk": "R0",
            "description": "查询公开货币兑换汇率。",
        },
        {
            "name": "browser_search",
            "risk": "R0",
            "description": "搜索公开网页。",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._tool_breakers = {}
    plane._capability_metadata = {
        "query_exchange_rate": {
            "intents": ["currency_exchange"],
            "examples": ["美元兑人民币"],
        }
    }
    plane.store = SimpleNamespace(
        capabilities=lambda active_only=False: active_tools,
    )

    tools = plane.select_tools("美元兑人民币现在是多少", "standard", ROLE_MEMBER)

    assert tools[0] == "query_exchange_rate"


def test_local_capability_index_ignores_generic_short_chat() -> None:
    active_tools = [
        {
            "name": "browser_open",
            "risk": "R0",
            "description": "Open a public webpage in the browser.",
        },
        {
            "name": "deliver_music",
            "risk": "R0",
            "description": "Play a selected song for the current user.",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._tool_breakers = {}
    plane._capability_metadata = {}
    plane.store = SimpleNamespace(
        capabilities=lambda active_only=False: active_tools,
    )

    assert plane.select_tools("上下文理解可以吗", "standard", ROLE_MEMBER) == []


def test_history_request_is_not_misrouted_to_live_search() -> None:
    active_tools = [
        {
            "name": "get_recent_messages",
            "risk": "R1",
            "description": "搜索当前会话的历史消息记录。",
        },
        {
            "name": "anysearch_search",
            "risk": "R0",
            "description": "搜索当前公开信息。",
        },
        {
            "name": "browser_search",
            "risk": "R0",
            "description": "搜索公开网页。",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._tool_breakers = {}
    plane._capability_metadata = {}
    plane.store = SimpleNamespace(
        capabilities=lambda active_only=False: active_tools,
    )

    selected = plane.select_tools(
        "我今天4点的时候说了什么还记得吗", "standard", ROLE_MEMBER
    )

    assert selected == ["get_recent_messages"]


def test_gold_price_request_uses_search_without_unrelated_news_tool() -> None:
    active_tools = [
        {
            "name": "anysearch_search",
            "risk": "R0",
            "description": "搜索当前公开信息。",
        },
        {
            "name": "browser_search",
            "risk": "R0",
            "description": "搜索公开网页。",
        },
        {
            "name": "get_daily_news",
            "risk": "R0",
            "description": "获取每日新闻摘要。",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane._tool_breakers = {}
    plane._capability_metadata = {}
    plane.store = SimpleNamespace(
        capabilities=lambda active_only=False: active_tools,
    )

    selected = plane.select_tools("今日金价", "standard", ROLE_MEMBER)

    assert selected == ["anysearch_search", "browser_search"]


def test_visual_evidence_request_does_not_require_search_tools() -> None:
    active_tools = [
        {
            "name": "anysearch_search",
            "risk": "R0",
            "description": "Search current public information.",
        },
        {
            "name": "browser_search",
            "risk": "R0",
            "description": "Search public websites.",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.enforce = True
    plane.fast_provider = "deepseek/flash"
    plane.standard_provider = "deepseek/pro"
    plane._provider_breakers = {}
    plane.store = SimpleNamespace(
        get_mode=lambda principal_id, umo: None,
        capabilities=lambda active_only=False: active_tools,
    )
    plane.resolve_principal = lambda event: Principal(
        principal_id="qq:10001",
        platform_id="qq",
        sender_id="10001",
        role=ROLE_MEMBER,
    )
    image = type("Image", (), {})()
    event = SimpleNamespace(
        unified_msg_origin="qq:group:10001",
        message_obj=SimpleNamespace(message=[image]),
        get_extra=lambda key, default=None: (
            True if key == "semantic_router_image_requested" else default
        ),
    )

    plan = plane.build_route_plan(event, "亚托莉，我上面发图片是什么意思")

    assert plan is not None
    assert plan.allowed_tools == []
    assert plan.tool_required is False


def test_short_bilibili_request_selects_registered_plugin_tools() -> None:
    active_tools = [
        {
            "name": "bili_search_hot_videos",
            "risk": "R0",
            "description": "搜索哔哩哔哩热门视频。",
        },
        {
            "name": "bili_get_user_dynamics",
            "risk": "R0",
            "description": "查询并总结 Bilibili UP 主动态。",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.enforce = True
    plane.fast_provider = "deepseek/flash"
    plane.standard_provider = "deepseek/pro"
    plane._provider_breakers = {}
    plane.store = SimpleNamespace(
        get_mode=lambda principal_id, umo: None,
        capabilities=lambda active_only=False: active_tools,
    )
    plane.resolve_principal = lambda event: Principal(
        principal_id="qq:10001",
        platform_id="qq",
        sender_id="10001",
        role=ROLE_MEMBER,
    )
    event = SimpleNamespace(
        unified_msg_origin="qq:private:10001",
        message_obj=SimpleNamespace(message=[]),
    )

    plan = plane.build_route_plan(event, "帮我找B站热门视频")

    assert plan is not None
    assert plan.route == "standard"
    assert plan.allowed_tools[0] == "bili_search_hot_videos"
    assert "bili_get_user_dynamics" in plan.allowed_tools
    assert plan.tool_required is True


def test_bilibili_video_reference_selects_video_info_tool() -> None:
    active_tools = [
        {
            "name": "bili_search_hot_videos",
            "risk": "R0",
            "description": "搜索哔哩哔哩热门视频。",
        },
        {
            "name": "bili_get_user_dynamics",
            "risk": "R0",
            "description": "查询并总结 Bilibili UP 主动态。",
        },
        {
            "name": "bili_get_video_info",
            "risk": "R0",
            "description": "读取一个 BV 视频的标题、作者、时长和公开元数据。",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.enforce = True
    plane.fast_provider = "deepseek/flash"
    plane.standard_provider = "deepseek/pro"
    plane._provider_breakers = {}
    plane.store = SimpleNamespace(
        get_mode=lambda principal_id, umo: None,
        capabilities=lambda active_only=False: active_tools,
    )
    plane.resolve_principal = lambda event: Principal(
        principal_id="qq:10001",
        platform_id="qq",
        sender_id="10001",
        role=ROLE_MEMBER,
    )
    event = SimpleNamespace(
        unified_msg_origin="qq:private:10001",
        message_obj=SimpleNamespace(message=[]),
    )

    plan = plane.build_route_plan(event, "总结这个 BV1DbKN6JExh 视频")

    assert plan is not None
    assert plan.allowed_tools == ["bili_get_video_info"]
    assert plan.tool_required is True


def test_bilibili_video_summary_selects_official_summary_tool() -> None:
    active_tools = [
        {
            "name": "bili_get_video_info",
            "risk": "R0",
            "description": "读取一个 BV 视频的公开元数据。",
        },
        {
            "name": "bili_get_video_summary",
            "risk": "R0",
            "description": "读取 Bilibili 官方 AI 视频总结。",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.enforce = True
    plane.fast_provider = "deepseek/flash"
    plane.standard_provider = "deepseek/pro"
    plane._provider_breakers = {}
    plane.store = SimpleNamespace(
        get_mode=lambda principal_id, umo: None,
        capabilities=lambda active_only=False: active_tools,
    )
    plane.resolve_principal = lambda event: Principal(
        principal_id="qq:10001",
        platform_id="qq",
        sender_id="10001",
        role=ROLE_MEMBER,
    )
    event = SimpleNamespace(
        unified_msg_origin="qq:private:10001",
        message_obj=SimpleNamespace(message=[]),
    )

    plan = plane.build_route_plan(event, "这个 BV1DbKN6JExh 视频讲了什么")

    assert plan is not None
    assert plan.allowed_tools == ["bili_get_video_summary"]
    assert plan.tool_required is True


def test_group_history_intent_selects_exact_registered_tool() -> None:
    active_tools = [
        {
            "name": "get_group_memory_summary",
            "risk": "R0",
            "description": "获取指定日期的群聊总结。",
        },
        {
            "name": "anysearch_search",
            "risk": "R0",
            "description": "Search current public information.",
        },
    ]
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.enforce = True
    plane.fast_provider = "deepseek/flash"
    plane.standard_provider = "deepseek/pro"
    plane._provider_breakers = {}
    plane.store = SimpleNamespace(
        get_mode=lambda principal_id, umo: None,
        capabilities=lambda active_only=False: active_tools,
    )
    plane.resolve_principal = lambda event: Principal(
        principal_id="qq:10001",
        platform_id="qq",
        sender_id="10001",
        role=ROLE_MEMBER,
    )
    event = SimpleNamespace(
        unified_msg_origin="qq:group:10001",
        message_obj=SimpleNamespace(message=[]),
    )

    plan = plane.build_route_plan(event, "亚托里，昨天群里聊了什么")

    assert plan is not None
    assert plan.route == "standard"
    assert plan.allowed_tools == ["get_group_memory_summary"]
    assert plan.tool_required is True


def test_developer_and_external_send_tools_are_not_public() -> None:
    plane = AgentControlPlane.__new__(AgentControlPlane)

    assert plane._classify_risk("dev_write_file", "Write a project file") == "R4"
    assert plane._classify_risk("dev_read_file", "Read a project file") == "R4"
    assert plane._classify_risk("send_emoji_by_id", "Send an emoji") == "R3"
    assert plane._classify_risk("anysearch_search", "Search public facts") == "R0"


def test_risk_escalation_resets_previously_active_capability(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    store.upsert_capability(
        name="dev_write_file",
        source="plugin:test",
        description="Write a project file",
        risk="R0",
        signature="same-signature",
    )

    status = store.upsert_capability(
        name="dev_write_file",
        source="plugin:test",
        description="Write a project file",
        risk="R4",
        signature="same-signature",
    )

    assert status == "pending"
    capability = store.capability("dev_write_file")
    assert capability is not None
    assert capability["risk"] == "R4"
    assert capability["status"] == "pending"


def test_capability_catalog_keeps_command_and_tool_kinds_separate(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    store.upsert_capability(
        name="weather_tool",
        kind="tool",
        source="plugin:test",
        description="Read public weather",
        risk="R0",
        signature="tool-signature",
    )
    store.upsert_capability(
        name="command:weather",
        kind="command",
        source="command:test",
        description="Weather command",
        risk="R3",
        signature="command-signature",
    )

    records = {item["name"]: item for item in store.capabilities()}
    assert records["weather_tool"]["kind"] == "tool"
    assert records["command:weather"]["kind"] == "command"


def test_group_guest_keeps_guest_identity_but_can_read_scoped_r1(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    principal = store.resolve_principal(
        principal_id="qq:guest",
        platform_id="qq",
        sender_id="guest",
        is_owner=False,
        default_role=ROLE_GUEST,
    )
    assert principal.role == ROLE_GUEST

    store.upsert_capability(
        name="group_stats",
        source="plugin:test",
        description="Read current group aggregate statistics",
        risk="R1",
        signature="group-stats",
    )
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.store = store
    plane.resolve_principal = lambda event: principal
    plane._redact = lambda text: text
    group_event = SimpleNamespace(
        unified_msg_origin="qq:group:g1",
        get_group_id=lambda: "g1",
    )
    private_event = SimpleNamespace(
        unified_msg_origin="qq:private:guest",
        get_group_id=lambda: "",
    )

    allowed, _, _ = plane.authorize_tool(group_event, "group_stats", {})
    denied, _, _ = plane.authorize_tool(private_event, "group_stats", {})
    assert allowed is True
    assert denied is False


def test_user_info_cross_user_lookup_requires_owner_approval(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    store.upsert_capability(
        name="get_user_info",
        source="plugin:qq_tools",
        description="Read QQ profile information",
        risk="R1",
        signature="user-info",
    )
    principal = Principal("qq:10001", "qq", "10001", ROLE_MEMBER)
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.store = store
    plane.resolve_principal = lambda event: principal
    plane._redact = lambda text: text
    event = SimpleNamespace(
        unified_msg_origin="qq:group:g1",
        get_group_id=lambda: "g1",
        get_sender_id=lambda: "10001",
    )

    allowed, _, _ = plane.authorize_tool(event, "get_user_info", {"qq_id": "20002"})
    assert allowed is False
    pending = store.pending_approvals(False, principal.principal_id)
    assert pending[0]["risk"] == "R3"

    own_allowed, _, _ = plane.authorize_tool(
        event, "get_user_info", {"qq_id": "10001"}
    )
    assert own_allowed is True


def test_request_policy_denies_tool_outside_allowlist(tmp_path) -> None:
    store = ControlPlaneStore(tmp_path / "control.db")
    store.initialize()
    store.upsert_capability(
        name="browser_open",
        source="plugin:qq_tools",
        description="Open a public webpage",
        risk="R0",
        signature="browser-open",
    )
    principal = Principal("qq:10001", "qq", "10001", ROLE_MEMBER)
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.store = store
    plane.resolve_principal = lambda event: principal
    event = SimpleNamespace(
        unified_msg_origin="qq:private:10001",
        get_extra=lambda key, default=None: {
            AGENT_EXECUTION_POLICY_EXTRA_KEY: {
                "allowed_tools": ["browser_search"]
            }
        }.get(key, default),
        set_extra=lambda key, value: None,
    )

    allowed, message, approval_id = plane.authorize_tool(event, "browser_open", {})

    assert allowed is False
    assert "not allowed" in message
    assert approval_id is None


@pytest.mark.asyncio
async def test_fast_request_uses_reserved_lane_when_shared_lane_is_full() -> None:
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.shadow_mode = False
    plane._shared_slots = asyncio.Semaphore(0)
    plane._fast_slots = asyncio.Semaphore(1)
    plane._deep_slots = asyncio.Semaphore(1)
    plane._fast_queue_timeout = 0.01
    plane._standard_queue_timeout = 0.01
    plane._lease_timeout = 60.0
    plane._leases = {}
    plane.store = SimpleNamespace(record_health_event=lambda *args: None)
    event = FakeRouteEvent("fast")

    assert await plane.acquire_route(event) is True
    assert plane._fast_slots._value == 0
    assert plane._shared_slots._value == 0

    plane.release_route(event)
    assert plane._fast_slots._value == 1


@pytest.mark.asyncio
async def test_route_planning_does_not_acquire_execution_capacity() -> None:
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.shadow_mode = False
    plane._shared_slots = asyncio.Semaphore(3)
    plane._fast_slots = asyncio.Semaphore(1)
    plane._deep_slots = asyncio.Semaphore(1)
    plane._leases = {}
    principal = Principal("qq:owner", "qq", "owner", ROLE_OWNER)
    plan = RoutePlan(
        route="fast",
        reason="short",
        provider_id="deepseek/flash",
        allowed_tools=[],
        knowledge_mode="off",
        max_steps=1,
        tool_timeout_seconds=15,
        request_max_retries=0,
        output_chars=180,
        tool_required=False,
        principal=principal,
    )
    plane.build_route_plan = lambda event, text: plan
    plane.store = SimpleNamespace(audit_decision=lambda *args: None)
    event = FakeRouteEvent("fast")

    assert await plane.apply_route(event, "hello") is plan
    assert event.get_extra("agent_trace_id").startswith("trace-")
    assert plane._shared_slots._value == 3
    assert plane._fast_slots._value == 1
    assert not plane._leases


@pytest.mark.asyncio
async def test_standard_overload_cannot_consume_reserved_fast_lane() -> None:
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.shadow_mode = False
    plane._shared_slots = asyncio.Semaphore(0)
    plane._fast_slots = asyncio.Semaphore(1)
    plane._deep_slots = asyncio.Semaphore(1)
    plane._fast_queue_timeout = 0.01
    plane._standard_queue_timeout = 0.01
    plane._lease_timeout = 60.0
    plane._leases = {}
    health_events = []
    plane.store = SimpleNamespace(
        record_health_event=lambda *args: health_events.append(args)
    )
    event = FakeRouteEvent("standard")

    assert await plane.acquire_route(event) is False
    assert plane._fast_slots._value == 1
    assert plane._shared_slots._value == 0
    assert event.result is not None
    assert health_events[-1][2] == "llm_queue_saturated"


@pytest.mark.asyncio
async def test_abandoned_fast_lease_is_reclaimed_by_watchdog() -> None:
    plane = AgentControlPlane.__new__(AgentControlPlane)
    plane.shadow_mode = False
    plane._shared_slots = asyncio.Semaphore(1)
    plane._fast_slots = asyncio.Semaphore(1)
    plane._deep_slots = asyncio.Semaphore(1)
    plane._fast_queue_timeout = 0.01
    plane._standard_queue_timeout = 0.01
    plane._lease_timeout = 0.01
    plane._leases = {}
    health_events = []
    plane.store = SimpleNamespace(
        record_health_event=lambda *args: health_events.append(args)
    )
    event = FakeRouteEvent("fast")

    assert await plane.acquire_route(event) is True
    await asyncio.sleep(0.03)

    assert plane._fast_slots._value == 1
    assert not plane._leases
    assert health_events[-1][2] == "llm_lease_expired"
