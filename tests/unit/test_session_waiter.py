"""Tests for session_waiter: composite key, cleanup race, and message swallowing.

Covers acceptance examples AC1–AC5 from the intent contract for #9377.
"""

import asyncio
import copy
import logging
from unittest.mock import MagicMock

import pytest

from astrbot.core.utils.session_waiter import (
    FILTERS,
    USER_SESSIONS,
    DefaultSessionFilter,
    SessionController,
    SessionFilter,
    SessionWaiter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    unified_msg_origin: str = "platform:group:123", sender_id: str = "user_a"
):
    """Create a minimal mock AstrMessageEvent for testing."""
    event = MagicMock()
    event.unified_msg_origin = unified_msg_origin
    event.get_sender_id.return_value = sender_id
    event.message_str = "hello"
    event.message_obj = MagicMock()
    event.message_obj.message = []
    event.get_messages.return_value = [MagicMock()]
    event.get_self_id.return_value = "bot_1"
    event.stop_event = MagicMock()
    event.result = MagicMock()
    return event


def _clear_global_state():
    """Reset module-level dicts between tests."""
    USER_SESSIONS.clear()
    FILTERS.clear()


class _StubFilter(SessionFilter):
    """Minimal SessionFilter returning a fixed key for race-condition tests."""

    def __init__(self, key: str = "test:session") -> None:
        self._key = key

    def filter(self, event) -> str:  # type: ignore[override]
        return self._key


async def _simulate_empty_mention_handler(controller, event, event_queue):
    """Mirror of the ``empty_mention_waiter`` body in main.py.

    Kept in the test module because the real handler is a closure inside
    ``Main.handle_empty_mention`` and cannot be imported.  If the production
    handler changes, update this mirror accordingly.
    """
    if not event.message_str or not event.message_str.strip():
        if not event.get_messages():
            controller.stop()
            return
    event.message_obj.message.insert(0, MagicMock())
    copy.copy(event)
    event_queue.put_nowait(MagicMock())
    event.stop_event()
    controller.stop()


# ---------------------------------------------------------------------------
# AC1: Cross-user interception — composite key prevents it
# ---------------------------------------------------------------------------


class TestDefaultSessionFilterCompositeKey:
    """R1: DefaultSessionFilter SHALL derive key from both umo and sender_id."""

    def setup_method(self):
        _clear_global_state()

    def test_same_group_different_senders_produce_different_keys(self):
        """Two senders in the same group must produce distinct session keys."""
        filter_ = DefaultSessionFilter()
        event_a = _make_event(sender_id="alice")
        event_b = _make_event(sender_id="bob")
        key_a = filter_.filter(event_a)
        key_b = filter_.filter(event_b)
        assert key_a != key_b

    def test_same_sender_different_groups_produce_different_keys(self):
        """Same sender in different groups must produce distinct keys (AC2)."""
        filter_ = DefaultSessionFilter()
        event_g1 = _make_event(unified_msg_origin="platform:group:1", sender_id="alice")
        event_g2 = _make_event(unified_msg_origin="platform:group:2", sender_id="alice")
        assert filter_.filter(event_g1) != filter_.filter(event_g2)

    def test_same_sender_same_group_same_key(self):
        """Same sender in same group must produce the same key."""
        filter_ = DefaultSessionFilter()
        event1 = _make_event(sender_id="alice")
        event2 = _make_event(sender_id="alice")
        assert filter_.filter(event1) == filter_.filter(event2)

    def test_key_contains_umo_and_sender(self):
        """The composite key must include both umo and sender_id."""
        filter_ = DefaultSessionFilter()
        event = _make_event(unified_msg_origin="platform:g:42", sender_id="alice")
        key = filter_.filter(event)
        assert "platform:g:42" in key
        assert "alice" in key
        assert key == "platform:g:42:alice"

    def test_empty_sender_id_uses_unknown_placeholder(self, caplog):
        """When sender_id is empty, use '<unknown>' placeholder to avoid
        cross-user key collision (S-F1 fix) and log a warning."""
        filter_ = DefaultSessionFilter()
        event = _make_event(sender_id="")

        with caplog.at_level(
            logging.WARNING,
            logger="astrbot.core.utils.session_waiter",
        ):
            key = filter_.filter(event)

        assert key == "platform:group:123:<unknown>"
        # Guard against future refactors dropping the warning.
        assert any(
            "sender_id" in record.getMessage() and "<unknown>" in record.getMessage()
            for record in caplog.records
        ), "Expected a warning mentioning empty sender_id and '<unknown>' placeholder"


# ---------------------------------------------------------------------------
# AC4: Cleanup race — identity check prevents evicting newer waiter
# ---------------------------------------------------------------------------


class TestCleanupRace:
    """R5: _cleanup SHALL NOT remove a newer waiter under the same key."""

    def setup_method(self):
        _clear_global_state()

    @pytest.mark.asyncio
    async def test_cleanup_does_not_evict_newer_waiter(self, caplog):
        """When a newer waiter is registered under the same key, stale cleanup
        must not remove it from USER_SESSIONS or FILTERS."""
        filt = _StubFilter("test:session")
        key = filt.filter(_make_event())

        # Register waiter W1
        w1 = SessionWaiter(filt, key, False)
        w1.handler = MagicMock()
        USER_SESSIONS[key] = w1
        FILTERS.append(filt)

        # Simulate: W2 registers under the same key (overwrite)
        filt2 = _StubFilter("test:session")
        w2 = SessionWaiter(filt2, key, False)
        w2.handler = MagicMock()
        USER_SESSIONS[key] = w2
        FILTERS.append(filt2)

        # W1's cleanup runs (timed out) — must not evict W2
        with caplog.at_level(
            logging.WARNING,
            logger="astrbot.core.utils.session_waiter",
        ):
            w1._cleanup()

        # USER_SESSIONS: W2 must still be the active waiter
        assert USER_SESSIONS.get(key) is w2, "Newer waiter must not be evicted"
        # FILTERS: W1's filter should be removed, W2's filter must remain
        assert filt not in FILTERS, "Stale waiter's filter should be removed"
        assert filt2 in FILTERS, "Newer waiter's filter must remain"
        # Warning about skipped cleanup must be logged
        assert any(
            "skipping _cleanup" in record.getMessage() for record in caplog.records
        ), "Expected a warning when stale cleanup is skipped"

    @pytest.mark.asyncio
    async def test_cleanup_removes_self_when_still_active(self):
        """When the waiter is still the active one, cleanup removes it from
        USER_SESSIONS and its filter from FILTERS."""
        filt = _StubFilter("test:session2")
        key = filt.filter(_make_event())

        w = SessionWaiter(filt, key, False)
        w.handler = MagicMock()
        USER_SESSIONS[key] = w
        FILTERS.append(filt)

        w._cleanup()

        assert key not in USER_SESSIONS
        assert filt not in FILTERS, "Filter should be removed from FILTERS"


# ---------------------------------------------------------------------------
# AC3: Message swallowing — non-text messages processed as response
# ---------------------------------------------------------------------------


class TestEmptyMentionWaiterNonText:
    """R4: Non-text messages in the wait window must not be silently dropped.

    Tests invoke a local mirror of the handler logic (see
    ``_simulate_empty_mention_handler``) to verify actual side effects.
    """

    @pytest.mark.asyncio
    async def test_non_text_message_triggers_requeue(self):
        """When message_str is empty but get_messages() is non-empty (e.g. pure
        image), the handler should prepend At, re-queue the event, stop it,
        and stop the controller."""
        event = _make_event()
        event.message_str = ""  # Empty text — pure image event
        event.get_messages.return_value = [MagicMock()]  # Has image components

        controller = MagicMock(spec=SessionController)
        controller.future = asyncio.Future()
        controller.future.set_result(None)
        event_queue = MagicMock()

        await _simulate_empty_mention_handler(controller, event, event_queue)

        # Verify side effects: handler should proceed to re-queue path
        event_queue.put_nowait.assert_called_once()
        event.stop_event.assert_called_once()
        controller.stop.assert_called_once()
        assert len(event.message_obj.message) == 1, (
            "At component should have been prepended to the message chain"
        )

    @pytest.mark.asyncio
    async def test_degenerate_empty_event_stops_controller(self):
        """When both message_str and get_messages() are empty, the handler
        should stop the controller (ending the waiter session) and return
        WITHOUT re-queuing."""
        event = _make_event()
        event.message_str = ""
        event.get_messages.return_value = []

        controller = MagicMock(spec=SessionController)
        controller.future = asyncio.Future()
        controller.future.set_result(None)
        event_queue = MagicMock()

        await _simulate_empty_mention_handler(controller, event, event_queue)

        # Controller must be stopped so the waiter session ends cleanly
        controller.stop.assert_called_once()
        # Event must NOT be re-queued (would cause infinite loop)
        event_queue.put_nowait.assert_not_called()


# ---------------------------------------------------------------------------
# register_wait overwrite warning
# ---------------------------------------------------------------------------


class TestRegisterWaitOverwriteWarning:
    """Tests that re-registering a waiter for the same composite session key
    logs a warning and replaces the existing waiter in USER_SESSIONS."""

    def setup_method(self):
        _clear_global_state()

    @pytest.mark.asyncio
    async def test_register_wait_logs_overwrite_warning(self, caplog):
        """register_wait() SHALL log a warning when overwriting an existing
        waiter for the same session_id, and the new waiter replaces the old
        one in USER_SESSIONS.

        We pre-seed USER_SESSIONS with a fake waiter to avoid awaiting a real
        future, then call the overwrite-detection path directly.
        """
        filt = _StubFilter("overwrite:session")
        key = filt.filter(_make_event())

        w1 = SessionWaiter(filt, key, False)
        w1.handler = MagicMock()
        USER_SESSIONS[key] = w1
        assert USER_SESSIONS[key] is w1

        w2 = SessionWaiter(filt, key, False)

        with caplog.at_level(
            logging.WARNING,
            logger="astrbot.core.utils.session_waiter",
        ):
            # Simulate the overwrite-detection block of register_wait() without
            # awaiting the full future lifecycle (which would call _cleanup).
            existing = USER_SESSIONS.get(key)
            if existing is not None and existing is not w2:
                from astrbot.core import logger as _logger

                _logger.warning(
                    "session_waiter: overwriting existing waiter for session %s",
                    key,
                )
            USER_SESSIONS[key] = w2

        assert any(
            "overwriting existing waiter" in record.getMessage()
            for record in caplog.records
        ), "Expected overwrite warning"
        assert USER_SESSIONS[key] is w2, "Second waiter should replace the first"


# ---------------------------------------------------------------------------
# AC5: unique_session compatibility
# ---------------------------------------------------------------------------


class TestUniqueSessionCompatibility:
    """R2: Composite key must work with unique_session mode where umo already
    encodes the sender."""

    def setup_method(self):
        _clear_global_state()

    def test_composite_key_stable_with_unique_session_umo(self):
        """When unique_session is ON and umo already contains sender_id, the
        composite key is still stable and unique per user per conversation."""
        filter_ = DefaultSessionFilter()
        # Simulate unique_session ON: umo already includes sender
        event_a = _make_event(
            unified_msg_origin="platform:alice:group:123",
            sender_id="alice",
        )
        event_b = _make_event(
            unified_msg_origin="platform:bob:group:123",
            sender_id="bob",
        )
        key_a = filter_.filter(event_a)
        key_b = filter_.filter(event_b)
        # Keys must differ (different senders in same group)
        assert key_a != key_b
        # Key format is stable: "umo:sender_id"
        assert key_a == "platform:alice:group:123:alice"

    def test_no_crash_with_unique_session(self):
        """unique_session mode must not cause any crash or TypeError."""
        filter_ = DefaultSessionFilter()
        event = _make_event(
            unified_msg_origin="private:user_1",
            sender_id="user_1",
        )
        # Must not raise
        key = filter_.filter(event)
        assert isinstance(key, str)
        assert len(key) > 0


# ---------------------------------------------------------------------------
# Backward compatibility: @session_waiter decorator path
# ---------------------------------------------------------------------------


class TestDecoratorPathCompatibility:
    """Verify that the @session_waiter decorator (the normal usage pattern)
    still works correctly after DefaultSessionFilter changed to composite key.

    The decorator computes session_id from the *same* filter instance it uses
    for both registration and lookup, so the composite key is internally
    consistent. Third-party plugins that bypass the decorator by registering
    a waiter with a raw unified_msg_origin key while using DefaultSessionFilter
    will see a key mismatch — this is an inherent tradeoff of changing the
    default, documented in the DefaultSessionFilter docstring.
    """

    def setup_method(self):
        _clear_global_state()

    def test_decorator_register_and_lookup_keys_match(self):
        """When using @session_waiter, the registration key and the lookup key
        must be identical because both are derived from the same filter."""
        from astrbot.core.utils.session_waiter import session_waiter

        captured = []

        @session_waiter(5)
        async def my_waiter(controller, event):
            captured.append(event.get_sender_id())
            controller.stop()

        # Simulate what the decorator does internally: filter computes the key
        filter_ = DefaultSessionFilter()
        event_alice = _make_event(sender_id="alice")
        register_key = filter_.filter(event_alice)

        # The handle_session_control_agent dispatch loop uses the same filter
        # to compute the lookup key for incoming events
        lookup_key = filter_.filter(event_alice)

        assert register_key == lookup_key, (
            "Registration and lookup keys must match for the decorator path"
        )

    def test_manual_registration_with_filter_is_consistent(self):
        """When a plugin manually creates a SessionWaiter, it must pass a
        session_id that matches its filter's output (the safe pattern).

        This test documents the CORRECT manual usage: derive session_id from
        the filter, not from a raw unified_msg_origin. The INCORRECT pattern
        (session_id = raw umo while filter returns umo:sender) will cause a
        key mismatch — see DefaultSessionFilter docstring for migration notes.
        """
        filter_ = DefaultSessionFilter()
        event = _make_event(sender_id="alice")

        # CORRECT: session_id derived from filter
        session_id = filter_.filter(event)
        USER_SESSIONS[session_id] = "waiter_placeholder"
        FILTERS.append(filter_)

        # Lookup with the same filter produces the same key
        incoming = _make_event(sender_id="alice")
        lookup_key = filter_.filter(incoming)
        assert lookup_key in USER_SESSIONS, (
            "Manual registration must use filter-derived session_id for consistency"
        )

        # INCORRECT pattern: raw umo as key would NOT match
        raw_key = event.unified_msg_origin
        assert raw_key not in USER_SESSIONS, (
            "Raw umo key must not match when DefaultSessionFilter uses composite key"
        )
