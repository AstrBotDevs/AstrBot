import asyncio
from collections import Counter, deque
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import astrbot.api.message_components as Comp
from data.plugins.astrbot_plugin_semantic_router.main import SemanticRouterPlugin


class FakeMailboxEvent:
    """Minimal group event for adaptive mailbox tests."""

    def __init__(self, user_id: str, text: str, group_id: str = "group-1"):
        self.user_id = user_id
        self.group_id = group_id
        self.message_str = text
        self.unified_msg_origin = f"qq:group:{group_id}"
        self.session_id = self.unified_msg_origin
        self.message_obj = SimpleNamespace(
            message=[], message_str=text, message_id=f"{user_id}:{text}"
        )
        self.is_at_or_wake_command = False
        self.is_wake = False
        self.stopped = False
        self.call_llm = True
        self.extras = {}

    def is_private_chat(self) -> bool:
        """Return false for the group test double."""

        return False

    def get_platform_name(self) -> str:
        """Return the stable platform name."""

        return "qq"

    def get_group_id(self) -> str:
        """Return the test group identifier."""

        return self.group_id

    def get_sender_id(self) -> str:
        """Return the stable sender identifier."""

        return self.user_id

    def get_sender_name(self) -> str:
        """Return a deterministic sender name."""

        return self.user_id

    def set_extra(self, key, value) -> None:
        """Store one event extra.

        Args:
            key: Extra key.
            value: Value to store.
        """

        self.extras[key] = value

    def stop_event(self) -> None:
        """Mark the event as stopped."""

        self.stopped = True

    def is_stopped(self) -> bool:
        """Return whether event propagation has stopped."""

        return self.stopped

    def should_call_llm(self, enabled: bool) -> None:
        """Capture the default LLM decision.

        Args:
            enabled: Whether the default LLM may run.
        """

        self.call_llm = enabled


@pytest.fixture
def mailbox_plugin() -> SemanticRouterPlugin:
    """Build an isolated mailbox without starting AstrBot services."""

    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.mailbox_global_capacity = 32
    plugin.mailbox_session_capacity = 6
    plugin.fragment_quiet_window = 0.03
    plugin.fragment_hard_window = 0.08
    plugin.mailbox_max_merge_count = 5
    plugin._mailbox_lock = asyncio.Lock()
    plugin._mailbox_pending = {}
    plugin._mailbox_counters = Counter()
    plugin._mailbox_wait_ms = deque(maxlen=500)
    plugin._work_slots = {
        "search": asyncio.Semaphore(2),
        "vision": asyncio.Semaphore(2),
        "plugin": asyncio.Semaphore(3),
    }
    plugin._work_session_locks = {}
    plugin._work_waiters = Counter()
    plugin._work_user_waiters = Counter()
    plugin._work_waiter_lock = asyncio.Lock()
    plugin.recent_image_ttl_seconds = 120.0
    plugin._recent_conversation_images = {}
    plugin._audit_mailbox = lambda *args, **kwargs: plugin._mailbox_counters.update(
        [args[3]]
    )
    return plugin


@pytest.mark.asyncio
async def test_image_is_cached_before_wakepro_and_attached_to_followup(
    mailbox_plugin, tmp_path
) -> None:
    image_event = FakeMailboxEvent("u1", "")
    image_path = tmp_path / "recent-image.png"
    image_path.write_bytes(b"stable-image-test")
    image_event.message_obj.message = [Comp.Image.fromFileSystem(image_path)]

    await mailbox_plugin.capture_recent_images(image_event)

    followup = FakeMailboxEvent("u1", "亚托莉，上面这张图是什么意思")
    image_calls = []

    async def apply_route(event, text):
        return None

    async def build_image_context(event):
        image_calls.append(event.message_str)
        return {"ok": True, "summary": "visual evidence"}

    @asynccontextmanager
    async def work_budget(event, text, kind, timeout):
        yield True

    mailbox_plugin.context_enabled = False
    mailbox_plugin.enabled = True
    mailbox_plugin.image_understanding_enabled = True
    mailbox_plugin.integrated_image_answer_enabled = True
    # Unified Tool Manager mode must still pre-execute required visual evidence;
    # otherwise the model may skip the required tool and fall into legacy captioning.
    mailbox_plugin.unified_tool_execution = True
    mailbox_plugin.capability_routing_enabled = False
    mailbox_plugin.direct_search_enabled = True
    mailbox_plugin.adaptive_mailbox_enabled = False
    mailbox_plugin._looks_like_explicit_command = lambda text: False
    mailbox_plugin._targeting_allowed = lambda event, text: (True, "explicit wake")
    mailbox_plugin._mark_conversation_addressed = lambda event, reason: None
    mailbox_plugin._normalize_text = lambda text: text
    mailbox_plugin._extract_search_query = lambda text: "wrong-search-route"
    mailbox_plugin._looks_like_image_understanding = lambda text: True
    mailbox_plugin._image_wake_text = lambda text: True
    mailbox_plugin._mark_cooldown = lambda event: None
    mailbox_plugin._work_budget = work_budget
    mailbox_plugin._build_image_context = build_image_context
    mailbox_plugin._apply_vision_semantic_policy = lambda event, context: None
    mailbox_plugin.control_plane = SimpleNamespace(apply_route=apply_route)

    results = [result async for result in mailbox_plugin.route_message(followup)]

    assert results == []
    assert image_calls == ["亚托莉，上面这张图是什么意思"]
    assert followup.extras["semantic_router_recent_image_attached"] is True
    assert followup.extras["semantic_router_recent_image_paths"] == [
        str(image_path.resolve())
    ]
    assert followup.extras["semantic_router_image_requested"] is True
    assert any(isinstance(item, Comp.Image) for item in followup.message_obj.message)
    assert "semantic_router_direct_search" not in followup.extras


@pytest.mark.asyncio
async def test_reply_wrapped_image_is_cached_for_name_wake(
    mailbox_plugin, tmp_path
) -> None:
    image_path = tmp_path / "reply-image.png"
    image_path.write_bytes(b"reply-image-test")
    image_event = FakeMailboxEvent("u1", "")
    image = Comp.Image.fromFileSystem(image_path)
    image_event.message_obj.message = [
        Comp.Reply(id="m2", sender_id="u2", chain=[image]),
    ]

    await mailbox_plugin.capture_recent_images(image_event)

    cached = mailbox_plugin._recent_conversation_images["qq:group:group-1"]
    assert len(cached["images"]) == 1


def test_image_only_message_is_kept_in_scoped_context(mailbox_plugin, tmp_path) -> None:
    image_path = tmp_path / "context-image.png"
    image_path.write_bytes(b"context-image-test")
    event = FakeMailboxEvent("u1", "")
    event.message_obj.message = [Comp.Image.fromFileSystem(image_path)]
    mailbox_plugin.context_state = {"scopes": {}, "conversations": {}}
    mailbox_plugin.max_recent_messages = 24
    mailbox_plugin.max_context_text_chars = 900
    mailbox_plugin.context_ttl_days = 30
    mailbox_plugin._schedule_context_save = lambda: None

    mailbox_plugin._record_message(event)

    assert (
        mailbox_plugin.context_state["scopes"]["qq:group:group-1:shared"]["recent"][-1][
            "text"
        ]
        == "[图片]"
    )


def test_mailbox_classification_uses_zero_model_signals(mailbox_plugin) -> None:
    event = FakeMailboxEvent("u1", "是的")

    assert (
        mailbox_plugin._classify_mailbox(
            event,
            "普通群聊",
            scope_allowed=False,
            scope_reason="群聊未唤醒",
            has_image=False,
            work_required=False,
        )[0]
        == "CONTEXT_ONLY"
    )
    assert (
        mailbox_plugin._classify_mailbox(
            event,
            "是的",
            scope_allowed=True,
            scope_reason="续接",
            has_image=False,
            work_required=False,
        )[0]
        == "CONTEXT_ONLY"
    )
    assert (
        mailbox_plugin._classify_mailbox(
            event,
            "帮我查一下金价",
            scope_allowed=True,
            scope_reason="明确唤醒",
            has_image=False,
            work_required=True,
        )[0]
        == "WORK"
    )
    assert (
        mailbox_plugin._classify_mailbox(
            event,
            "今天累死了",
            scope_allowed=True,
            scope_reason="同一用户续接",
            has_image=False,
            work_required=False,
        )[0]
        == "COALESCE"
    )


@pytest.mark.parametrize(
    "text",
    [
        "亚托莉，我上面发图片是什么意思",
        "我刚发的那张图是什么梗",
        "前面发了个表情包表达什么",
        "我发的上一张图片写了什么",
    ],
)
def test_natural_recent_image_references_are_recognized(mailbox_plugin, text) -> None:
    assert mailbox_plugin._references_recent_image(text) is True


@pytest.mark.parametrize(
    "text", ["亚托莉，看看上面的内容", "亚 托 莉 你在吗", "萝卜子，接着说"]
)
def test_name_wake_aliases_are_normalized(mailbox_plugin, text) -> None:
    assert mailbox_plugin._search_wake_text(text) is True


def test_recent_same_user_image_is_a_contextual_followup(mailbox_plugin) -> None:
    event = FakeMailboxEvent("u1", "")
    mailbox_plugin.route_group_only_when_wake_or_at = True
    mailbox_plugin.conversation_followup_seconds = 60
    mailbox_plugin._scope_info = lambda event: {
        "conversation_key": "qq:group:group-1",
        "user_id": "u1",
    }
    mailbox_plugin._get_conversation_state = lambda key, create=False: {
        "last_bot_addressed_user_id": "u1",
        "last_bot_addressed_at": __import__("time").time(),
        "last_other_user_after_address_at": 0,
    }
    mailbox_plugin._contains_image = lambda event: True
    mailbox_plugin._search_wake_text = lambda text: False
    mailbox_plugin._image_wake_text = lambda text: False

    allowed, reason = mailbox_plugin._targeting_allowed(event, "")

    assert allowed is True
    assert "续接" in reason


def test_owner_bare_image_is_admitted_without_wake(mailbox_plugin) -> None:
    event = FakeMailboxEvent("owner", "")
    mailbox_plugin.route_group_only_when_wake_or_at = True
    mailbox_plugin._contains_image = lambda event: True
    mailbox_plugin._search_wake_text = lambda text: False
    mailbox_plugin._image_wake_text = lambda text: False
    mailbox_plugin.context_state = {}
    mailbox_plugin.control_plane = SimpleNamespace(
        resolve_principal=lambda event: SimpleNamespace(role="owner")
    )

    allowed, reason = mailbox_plugin._targeting_allowed(event, "")

    assert allowed is True
    assert reason == "所有者图片"


@pytest.mark.asyncio
async def test_same_sender_fragments_merge_into_newest_event(mailbox_plugin) -> None:
    first = FakeMailboxEvent("u1", "我刚刚看到一个")
    second = FakeMailboxEvent("u1", "很奇怪的东西")

    first_task = asyncio.create_task(
        mailbox_plugin._coalesce_mailbox(first, first.message_str)
    )
    await asyncio.sleep(0.01)
    second_task = asyncio.create_task(
        mailbox_plugin._coalesce_mailbox(second, second.message_str)
    )
    first_result, second_result = await asyncio.gather(first_task, second_task)

    assert first_result is False
    assert second_result is True
    assert first.stopped is True
    assert second.message_str == "我刚刚看到一个\n很奇怪的东西"
    assert not mailbox_plugin._mailbox_pending


@pytest.mark.asyncio
async def test_fifty_message_burst_stays_within_mailbox_bounds(mailbox_plugin) -> None:
    events = [FakeMailboxEvent(f"u{index}", f"fragment-{index}") for index in range(50)]
    tasks = [
        asyncio.create_task(mailbox_plugin._coalesce_mailbox(event, event.message_str))
        for event in events
    ]
    await asyncio.sleep(0.01)

    assert len(mailbox_plugin._mailbox_pending) <= 6

    await asyncio.gather(*tasks)
    assert not mailbox_plugin._mailbox_pending
    assert sum(event.stopped for event in events) >= 44


@pytest.mark.asyncio
async def test_work_budget_is_global_and_per_conversation(mailbox_plugin) -> None:
    first = FakeMailboxEvent("u1", "search one", "g1")
    same_session = FakeMailboxEvent("u2", "search two", "g1")
    other_session = FakeMailboxEvent("u3", "search three", "g2")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold_first() -> bool:
        async with mailbox_plugin._work_budget(
            first, first.message_str, "search", 0.2
        ) as admitted:
            entered.set()
            await release.wait()
            return admitted

    first_task = asyncio.create_task(hold_first())
    await entered.wait()
    async with mailbox_plugin._work_budget(
        other_session, other_session.message_str, "search", 0.05
    ) as other_admitted:
        assert other_admitted is True
    async with mailbox_plugin._work_budget(
        same_session, same_session.message_str, "search", 0.01
    ) as same_admitted:
        assert same_admitted is False
    release.set()
    assert await first_task is True
    assert not mailbox_plugin._work_waiters
    assert not mailbox_plugin._work_user_waiters


@pytest.mark.asyncio
async def test_quoted_image_meaning_uses_vision_before_search(mailbox_plugin) -> None:
    event = FakeMailboxEvent("u1", "我这张图是什么意思")
    image_calls = []

    async def apply_route(event, text):
        return None

    async def build_image_context(event):
        image_calls.append(event.message_str)
        return {"ok": True, "summary": "visual evidence"}

    @asynccontextmanager
    async def work_budget(event, text, kind, timeout):
        yield True

    mailbox_plugin.context_enabled = False
    mailbox_plugin.enabled = True
    mailbox_plugin.image_understanding_enabled = True
    mailbox_plugin.integrated_image_answer_enabled = True
    mailbox_plugin.capability_routing_enabled = False
    mailbox_plugin.direct_search_enabled = True
    mailbox_plugin.adaptive_mailbox_enabled = False
    mailbox_plugin._contains_image = lambda event: True
    mailbox_plugin._looks_like_explicit_command = lambda text: False
    mailbox_plugin._targeting_allowed = lambda event, text: (True, "明确唤醒")
    mailbox_plugin._mark_conversation_addressed = lambda event, reason: None
    mailbox_plugin._normalize_text = lambda text: text
    mailbox_plugin._extract_search_query = lambda text: "wrong-search-route"
    mailbox_plugin._looks_like_image_understanding = lambda text: True
    mailbox_plugin._image_wake_text = lambda text: False
    mailbox_plugin._mark_cooldown = lambda event: None
    mailbox_plugin._work_budget = work_budget
    mailbox_plugin._build_image_context = build_image_context
    mailbox_plugin._apply_vision_semantic_policy = lambda event, context: None
    mailbox_plugin.control_plane = SimpleNamespace(apply_route=apply_route)

    results = [result async for result in mailbox_plugin.route_message(event)]

    assert results == []
    assert image_calls == ["我这张图是什么意思"]
    assert event.extras["semantic_router_image_understanding"] is True
    assert "semantic_router_direct_search" not in event.extras


@pytest.mark.asyncio
async def test_same_user_cannot_queue_more_than_two_work_items(mailbox_plugin) -> None:
    first = FakeMailboxEvent("u1", "search one", "g1")
    second = FakeMailboxEvent("u1", "search two", "g1")
    third = FakeMailboxEvent("u1", "search three", "g1")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold(event) -> bool:
        async with mailbox_plugin._work_budget(
            event, event.message_str, "search", 0.2
        ) as admitted:
            if event is first:
                entered.set()
            if admitted:
                await release.wait()
            return admitted

    first_task = asyncio.create_task(hold(first))
    await entered.wait()
    second_task = asyncio.create_task(hold(second))
    await asyncio.sleep(0.01)
    async with mailbox_plugin._work_budget(
        third, third.message_str, "search", 0.05
    ) as third_admitted:
        assert third_admitted is False
    release.set()
    assert await first_task is True
    assert await second_task is True
    assert not mailbox_plugin._work_user_waiters
