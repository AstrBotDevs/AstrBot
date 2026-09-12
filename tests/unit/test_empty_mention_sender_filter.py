"""Tests for `_SenderSessionFilter` and the empty-mention waiter sender binding.

Covers PR #9422 / issue #9377: the empty-mention waiter must be scoped to the
(session, sender) pair that initiated it, so that in a group chat only the
initiating member can satisfy the waiter -- not every member of the group.

Two layers are exercised:

A. `_SenderSessionFilter.filter()` in isolation (pure key computation).
B. Integration through the `session_waiter` decorator + `SessionWaiter.trigger`,
   mirroring how `Main.handle_session_control_agent` dispatches follow-ups.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from astrbot.builtin_stars.astrbot.main import _SenderSessionFilter
from astrbot.core.utils.session_waiter import (
    FILTERS,
    USER_SESSIONS,
    SessionWaiter,
    session_waiter,
)

# Target sentinel for unresolvable sender ids (locked by review). Uses angle
# brackets because no platform produces a real sender id containing them.
UNKNOWN_SENDER_SENTINEL = "<unknown>"

UMO_GROUP_A = "test_platform:group:111"
UMO_GROUP_B = "test_platform:group:222"

DEFAULT_MESSAGE = "hello"


def make_event(umo: str, sender_id) -> MagicMock:
    """Build a minimal mock AstrMessageEvent.

    Only the surface used by the filter and the waiter machinery is populated:
    `unified_msg_origin`, `get_sender_id()` and `message_str`.
    """
    ev = MagicMock()
    ev.unified_msg_origin = umo
    ev.get_sender_id.return_value = sender_id
    ev.message_str = ""
    return ev


@pytest.fixture(autouse=True)
def _clean_global_session_state():
    """Never leak USER_SESSIONS / FILTERS across tests."""
    USER_SESSIONS.clear()
    FILTERS.clear()
    yield
    USER_SESSIONS.clear()
    FILTERS.clear()


async def _wait_for_registration(session_id: str, timeout: float = 1.0):
    """Poll until a waiter with `session_id` is registered; return its controller."""
    async def _poll():
        while session_id not in USER_SESSIONS:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout=timeout)
    return USER_SESSIONS[session_id].session_controller


def _release_keep_watcher(session_controller) -> None:
    """Unblock the `SessionController.keep()` background watcher task so the
    test event loop has no dangling tasks after an early completion."""
    if session_controller.current_event is not None:
        session_controller.current_event.set()


async def _dispatch_like_control_agent(event) -> None:
    """Mirror `Main.handle_session_control_agent`: for every registered filter,
    compute the session key and trigger any matching waiter."""
    for session_filter in list(FILTERS):
        session_id = session_filter.filter(event)
        if session_id in USER_SESSIONS:
            await SessionWaiter.trigger(session_id, event)


# =====================================================================
# A. _SenderSessionFilter.filter() -- pure unit tests
# =====================================================================


def test_different_senders_in_same_group_produce_different_keys():
    """A follow-up from another member of the same group must map to a
    different session key than the initiator's."""
    f = _SenderSessionFilter()
    ev_a = make_event(UMO_GROUP_A, "10001")
    ev_b = make_event(UMO_GROUP_A, "10002")
    assert f.filter(ev_a) != f.filter(ev_b)


def test_same_sender_in_different_groups_produce_different_keys():
    """Cross-session isolation: the same sender in another conversation must
    not share a session key."""
    f = _SenderSessionFilter()
    ev_g1 = make_event(UMO_GROUP_A, "10001")
    ev_g2 = make_event(UMO_GROUP_B, "10001")
    assert f.filter(ev_g1) != f.filter(ev_g2)


def test_same_sender_same_group_produces_same_key():
    """Repeatability: the initiator's follow-ups keep mapping to the same key."""
    f = _SenderSessionFilter()
    ev_1 = make_event(UMO_GROUP_A, "10001")
    ev_2 = make_event(UMO_GROUP_A, "10001")
    assert f.filter(ev_1) == f.filter(ev_2) == f"{UMO_GROUP_A}:10001"


@pytest.mark.parametrize("falsy_sender_id", ["", None, 0])
def test_falsy_sender_id_maps_to_unknown_sender_sentinel(falsy_sender_id):
    """An empty/falsy sender id falls back to a sentinel so the waiter never
    binds to the raw conversation alone."""
    f = _SenderSessionFilter()
    ev = make_event(UMO_GROUP_A, falsy_sender_id)
    assert f.filter(ev) == f"{UMO_GROUP_A}:{UNKNOWN_SENDER_SENTINEL}"
    # The sentinel key must not collide with a legitimate member's key.
    ev_real = make_event(UMO_GROUP_A, "10001")
    assert f.filter(ev) != f.filter(ev_real)


def test_two_unknown_senders_in_same_group_share_key():
    """Documented limitation of the current fallback: all members without a
    resolvable sender id collapse onto the same key in a group (they can still
    hijack each other's waiter). Kept as a documentation test, not as the
    desired behavior."""
    f = _SenderSessionFilter()
    ev_u1 = make_event(UMO_GROUP_A, "")
    ev_u2 = make_event(UMO_GROUP_A, None)
    assert f.filter(ev_u1) == f.filter(ev_u2)


def test_real_sender_id_equal_to_sentinel_does_not_collide():
    """A genuine sender id must never collide with the unknown-sender fallback
    key.

    Target behavior (locked by review): the sentinel is '<unknown>', which no
    real sender id contains, so even a real id that exactly equals the legacy
    sentinel string '__unknown_sender__' maps to its own distinct key.
    """
    f = _SenderSessionFilter()
    ev_unknown = make_event(UMO_GROUP_A, "")
    ev_legacy_sentinel_id = make_event(UMO_GROUP_A, "__unknown_sender__")
    assert f.filter(ev_unknown) != f.filter(ev_legacy_sentinel_id)


# =====================================================================
# B. Integration: the waiter is bound to the initiating sender
# =====================================================================


@pytest.mark.asyncio
async def test_original_sender_followup_is_captured():
    """The initiator's follow-up in the same group satisfies the waiter."""
    handler_called = asyncio.Event()
    handled = []

    @session_waiter(timeout=1.0)
    async def waiter(controller, event):
        if not event.message_str or not event.message_str.strip():
            return
        handled.append(event)
        handler_called.set()
        controller.stop()

    init_event = make_event(UMO_GROUP_A, "sender_a")
    followup_event = make_event(UMO_GROUP_A, "sender_a")
    followup_event.message_str = DEFAULT_MESSAGE

    session_id = _SenderSessionFilter().filter(init_event)
    waiter_task = asyncio.create_task(
        waiter(init_event, session_filter=_SenderSessionFilter())
    )
    controller = await _wait_for_registration(session_id)

    await _dispatch_like_control_agent(followup_event)
    await asyncio.wait_for(waiter_task, timeout=1.0)

    assert handler_called.is_set()
    assert len(handled) == 1
    assert session_id not in USER_SESSIONS  # cleaned up after completion
    _release_keep_watcher(controller)


@pytest.mark.asyncio
async def test_other_member_followup_is_not_captured():
    """A different member of the same group must NOT satisfy the waiter (the
    regression this PR fixes)."""
    handler_called = asyncio.Event()
    handled = []

    @session_waiter(timeout=0.3)
    async def waiter(controller, event):
        handled.append(event)
        handler_called.set()
        controller.stop()

    init_event = make_event(UMO_GROUP_A, "sender_a")
    other_event = make_event(UMO_GROUP_A, "sender_b")
    other_event.message_str = DEFAULT_MESSAGE

    session_id_a = _SenderSessionFilter().filter(init_event)
    session_id_b = _SenderSessionFilter().filter(other_event)
    assert session_id_a != session_id_b

    waiter_task = asyncio.create_task(
        waiter(init_event, session_filter=_SenderSessionFilter())
    )
    await _wait_for_registration(session_id_a)

    await _dispatch_like_control_agent(other_event)
    await asyncio.sleep(0.05)

    assert not handler_called.is_set()
    assert len(handled) == 0
    # The waiter is still bound to sender_a and still waiting.
    assert session_id_a in USER_SESSIONS
    assert session_id_b not in USER_SESSIONS

    # Nobody hijacked it; it eventually times out on its own.
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(waiter_task, timeout=1.0)


@pytest.mark.asyncio
async def test_cross_session_other_group_followup_is_not_captured():
    """The same sender in a different conversation must NOT satisfy the waiter."""
    handler_called = asyncio.Event()

    @session_waiter(timeout=0.3)
    async def waiter(controller, event):
        handler_called.set()
        controller.stop()

    init_event = make_event(UMO_GROUP_A, "sender_a")
    cross_event = make_event(UMO_GROUP_B, "sender_a")
    cross_event.message_str = DEFAULT_MESSAGE

    session_id_a = _SenderSessionFilter().filter(init_event)

    waiter_task = asyncio.create_task(
        waiter(init_event, session_filter=_SenderSessionFilter())
    )
    await _wait_for_registration(session_id_a)

    await _dispatch_like_control_agent(cross_event)
    await asyncio.sleep(0.05)

    assert not handler_called.is_set()
    assert session_id_a in USER_SESSIONS

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(waiter_task, timeout=1.0)


@pytest.mark.asyncio
async def test_blank_followup_does_not_satisfy_waiter():
    """A blank follow-up from the initiator returns early without stopping the
    controller, matching `empty_mention_waiter`'s blank-message guard."""
    handler_called = asyncio.Event()

    @session_waiter(timeout=0.3)
    async def waiter(controller, event):
        if not event.message_str or not event.message_str.strip():
            return
        handler_called.set()
        controller.stop()

    init_event = make_event(UMO_GROUP_A, "sender_a")
    blank_event = make_event(UMO_GROUP_A, "sender_a")
    blank_event.message_str = "   "

    session_id = _SenderSessionFilter().filter(init_event)

    waiter_task = asyncio.create_task(
        waiter(init_event, session_filter=_SenderSessionFilter())
    )
    await _wait_for_registration(session_id)

    await _dispatch_like_control_agent(blank_event)
    await asyncio.sleep(0.05)

    assert not handler_called.is_set()
    assert session_id in USER_SESSIONS

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(waiter_task, timeout=1.0)


@pytest.mark.asyncio
async def test_unknown_sender_registration_and_trigger_use_same_key():
    """The unknown-sender fallback still pairs registration and follow-up via
    the sentinel key within the same group."""
    handler_called = asyncio.Event()

    @session_waiter(timeout=1.0)
    async def waiter(controller, event):
        handler_called.set()
        controller.stop()

    unknown_init = make_event(UMO_GROUP_A, "")
    unknown_followup = make_event(UMO_GROUP_A, "")
    unknown_followup.message_str = DEFAULT_MESSAGE

    session_id = _SenderSessionFilter().filter(unknown_init)
    assert session_id == f"{UMO_GROUP_A}:{UNKNOWN_SENDER_SENTINEL}"

    waiter_task = asyncio.create_task(
        waiter(unknown_init, session_filter=_SenderSessionFilter())
    )
    controller = await _wait_for_registration(session_id)

    await _dispatch_like_control_agent(unknown_followup)
    await asyncio.wait_for(waiter_task, timeout=1.0)

    assert handler_called.is_set()
    _release_keep_watcher(controller)
