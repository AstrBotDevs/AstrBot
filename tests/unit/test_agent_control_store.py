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
    assert "likes tea" not in stored_args
    assert "content" in stored_args

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
    assert "anysearch_search" in plan.allowed_tools
    assert "browser_search" in plan.allowed_tools
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
