"""Session-key isolation tests for the empty-mention waiter (issue #9377).

The fix is scoped: DefaultSessionFilter keeps its group-level
unified_msg_origin semantics (third-party plugins rely on it), and only the
built-in empty-mention waiter opts into the new SenderSessionFilter.

This file therefore locks down two things:
1. The default behavior is unchanged — DefaultSessionFilter still returns
   unified_msg_origin (including a regression guard that mirrors a real
   plugin's manual-registration pattern);
2. The new behavior is correct — SenderSessionFilter only responds to the
   original sender, without leaking across conversations and without
   constructible key collisions.

The module under test is loaded from its file path with its two imports
stubbed, so validating pure key logic does not require the full astrbot
dependency tree. Production wiring of Main.handle_empty_mention is covered
separately in tests/unit/test_empty_mention_sender_scope.py.
"""

import asyncio
import importlib.util
import pathlib
import sys
import types

import pytest

_SRC = (
    pathlib.Path(__file__).resolve().parents[1]
    / "astrbot"
    / "core"
    / "utils"
    / "session_waiter.py"
)


def _load_session_waiter():
    """Load session_waiter from its file path with stubbed imports.

    Returns:
        The loaded session_waiter module object (cached in sys.modules).
    """
    if "_sw_under_test" in sys.modules:
        return sys.modules["_sw_under_test"]

    class BaseMessageComponent: ...

    class AstrMessageEvent: ...

    names = (
        "astrbot",
        "astrbot.core",
        "astrbot.core.message",
        "astrbot.core.message.components",
        "astrbot.core.platform",
    )
    saved = {k: sys.modules.get(k) for k in names}
    stubs = {k: types.ModuleType(k) for k in names}
    stubs["astrbot.core.message.components"].BaseMessageComponent = BaseMessageComponent
    stubs["astrbot.core.platform"].AstrMessageEvent = AstrMessageEvent
    # `import a.b.c as x` requires child modules as parent attributes.
    stubs["astrbot"].core = stubs["astrbot.core"]
    stubs["astrbot.core"].message = stubs["astrbot.core.message"]
    stubs["astrbot.core"].platform = stubs["astrbot.core.platform"]
    stubs["astrbot.core.message"].components = stubs["astrbot.core.message.components"]
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("_sw_under_test", _SRC)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_sw_under_test"] = mod
        spec.loader.exec_module(mod)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return mod


class FakeEvent:
    """Implements only the interface used by SessionFilter / handlers."""

    def __init__(self, umo: str, sender_id: str, text: str) -> None:
        self.unified_msg_origin = umo
        self._sender_id = sender_id
        self.message_str = text

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_messages(self) -> list:
        return []


@pytest.fixture
def waiter_mod():
    mod = _load_session_waiter()
    mod.USER_SESSIONS.clear()
    mod.FILTERS.clear()
    yield mod
    mod.USER_SESSIONS.clear()
    mod.FILTERS.clear()


GROUP = "napcat2:GroupMessage:984306989"
GROUP2 = "napcat2:GroupMessage:111222333"
ALICE = "3878611411"  # the member who sent the empty mention
BOB = "3781884259"  # an unrelated member of the same group


async def _run_with_sender_filter(mod, incoming):
    """Start ALICE's waiter with SenderSessionFilter and feed it events.

    Mirrors the empty-mention call site: ALICE sends an empty mention to start
    the waiter, then each event in `incoming` goes through the dispatch loop.

    Args:
        mod: The loaded session_waiter module.
        incoming: FakeEvent instances fed to the dispatch loop in order.

    Returns:
        List of (sender_id, unified_msg_origin) tuples the waiter captured.
    """
    captured = []

    @mod.session_waiter(5)
    async def waiter(controller, event):
        if not event.message_str.strip():
            return
        captured.append((event.get_sender_id(), event.unified_msg_origin))
        controller.stop()

    trigger = FakeEvent(GROUP, ALICE, "")
    task = asyncio.create_task(
        waiter(trigger, session_filter=mod.SenderSessionFilter())
    )
    await asyncio.sleep(0)  # let the waiter finish registration

    for ev in incoming:
        for f in list(mod.FILTERS):
            sid = f.filter(ev)
            if sid in mod.USER_SESSIONS:
                await mod.SessionWaiter.trigger(sid, ev)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass  # only swallow the cancellation itself; unexpected errors must fail
    return captured


# --- Default semantics unchanged (third-party plugin compatibility) ---


def test_default_filter_returns_umo_unchanged():
    """DefaultSessionFilter must keep returning unified_msg_origin."""
    f = _load_session_waiter().DefaultSessionFilter()
    assert f.filter(FakeEvent(GROUP, ALICE, "")) == GROUP
    # Same group, same key, regardless of sender.
    assert f.filter(FakeEvent(GROUP, BOB, "")) == GROUP


@pytest.mark.asyncio
async def test_default_manual_umo_registration_still_triggers(waiter_mod):
    """Regression guard mirroring astrbot_plugin_kimi_datasource_api usage.

    That plugin registers a waiter manually with the raw unified_msg_origin as
    the key while adding a DefaultSessionFilter to FILTERS. Because this fix
    leaves the default filter untouched, the lookup key still equals the
    registration key and the waiter must keep triggering. (If the default were
    changed to include the sender, registration key UMO would never match
    lookup key UMO+sender and the waiter could never trigger — this test exists
    to catch exactly that breakage.)
    """
    mod = waiter_mod
    triggered = []

    waiter = mod.SessionWaiter(mod.DefaultSessionFilter(), GROUP, False)

    async def handler(controller, event):
        triggered.append(event.get_sender_id())
        controller.stop()

    waiter.handler = handler
    mod.FILTERS.append(waiter.session_filter)
    mod.USER_SESSIONS[GROUP] = waiter  # registration key = raw UMO

    incoming = FakeEvent(GROUP, BOB, "login code")
    for f in list(mod.FILTERS):
        sid = f.filter(incoming)
        if sid in mod.USER_SESSIONS:
            await mod.SessionWaiter.trigger(sid, incoming)

    assert triggered == [BOB], "manually UMO-registered waiter must still trigger"


# --- New behavior correct (per-sender isolation) ---


@pytest.mark.asyncio
async def test_sender_filter_isolates_users_in_group(waiter_mod):
    """Primary goal: another member's message is not intercepted."""
    captured = await _run_with_sender_filter(
        waiter_mod, [FakeEvent(GROUP, BOB, "just chatting")]
    )
    assert captured == [], f"BOB's message must not be captured, got {captured}"


@pytest.mark.asyncio
async def test_sender_filter_accepts_original_sender(waiter_mod):
    """Happy path: the original sender's follow-up is still captured."""
    captured = await _run_with_sender_filter(
        waiter_mod, [FakeEvent(GROUP, ALICE, "write me a script")]
    )
    assert captured == [(ALICE, GROUP)]


def test_sender_filter_key_is_collision_free():
    """Keys must be unambiguous when UMO / sender contain separator chars.

    With plain concatenation ("umo#sender"), ("p:GroupMessage:g#x", "y") and
    ("p:GroupMessage:g", "x#y") produce the same key, defeating the isolation.
    The length-prefixed encoding must keep them distinct. Telegram topic-group
    origins genuinely contain "#", so this is not hypothetical.
    """
    f = _load_session_waiter().SenderSessionFilter()
    key_a = f.filter(FakeEvent("p:GroupMessage:g#x", "y", ""))
    key_b = f.filter(FakeEvent("p:GroupMessage:g", "x#y", ""))
    assert key_a != key_b, "distinct (conversation, sender) pairs collided"

    # Pairs constructed with ":" must not collide either.
    key_c = f.filter(FakeEvent("p:GroupMessage:g:x", "y", ""))
    key_d = f.filter(FakeEvent("p:GroupMessage:g", "x:y", ""))
    assert key_c != key_d


@pytest.mark.asyncio
async def test_sender_filter_isolates_users_with_hash_in_umo(waiter_mod):
    """Isolation holds for Telegram topic-group style origins containing "#"."""
    mod = waiter_mod
    topic_umo = "telegram:GroupMessage:-100123#42"
    captured = []

    @mod.session_waiter(5)
    async def waiter(controller, event):
        captured.append(event.get_sender_id())
        controller.stop()

    task = asyncio.create_task(
        waiter(
            FakeEvent(topic_umo, ALICE, ""),
            session_filter=mod.SenderSessionFilter(),
        )
    )
    await asyncio.sleep(0)

    intruder = FakeEvent(topic_umo, BOB, "butting in")
    for f in list(mod.FILTERS):
        sid = f.filter(intruder)
        if sid in mod.USER_SESSIONS:
            await mod.SessionWaiter.trigger(sid, intruder)
    assert captured == [], "another member must not be captured in a topic group"

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_sender_filter_does_not_leak_across_conversations(waiter_mod):
    """SenderSessionFilter keeps the conversation part of the key.

    ALICE's messages in another group or in DMs must not be captured by the
    waiter she started in GROUP.
    """
    captured = await _run_with_sender_filter(
        waiter_mod,
        [
            FakeEvent(GROUP2, ALICE, "talking in another group"),
            FakeEvent(f"napcat2:FriendMessage:{ALICE}", ALICE, "talking in DM"),
        ],
    )
    assert captured == [], f"cross-conversation messages captured: {captured}"
