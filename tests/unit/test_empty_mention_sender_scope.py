"""Production-wiring tests for empty-mention per-sender isolation (#9377).

Unlike tests/test_session_waiter_cross_user.py, which exercises the session-key
logic in isolation, these tests drive the real `Main.handle_empty_mention` and
`Main.handle_session_control_agent` handlers. They fail if the production
wiring is reverted (waiter registered without SenderSessionFilter, or the
empty-sender guard removed).
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import astrbot.builtin_stars.astrbot.main as main_module
from astrbot.api.message_components import At, Plain
from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.utils.session_waiter import FILTERS, USER_SESSIONS

BOT_ID = "3878611411"
GROUP_UMO = "napcat2:GroupMessage:984306989"
ALICE = "1111"  # the member who sends the empty mention
BOB = "2222"  # an unrelated member of the same group


@pytest.fixture(autouse=True)
def _clean_session_state():
    USER_SESSIONS.clear()
    FILTERS.clear()
    yield
    USER_SESSIONS.clear()
    FILTERS.clear()


class FakeEvent:
    """Minimal real object (not a MagicMock) so copy.copy() behaves natively."""

    def __init__(self, sender_id: str, text: str, components: list) -> None:
        self.unified_msg_origin = GROUP_UMO
        self.message_str = text
        self.message_obj = SimpleNamespace(message=list(components))
        self.stop_event_calls = 0
        self._sender_id = sender_id

    def get_messages(self) -> list:
        return self.message_obj.message

    def get_self_id(self) -> str:
        return BOT_ID

    def get_sender_id(self) -> str:
        return self._sender_id

    def stop_event(self) -> None:
        self.stop_event_calls += 1


def make_main() -> Main:
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = {
        "platform_settings": {
            "empty_mention_waiting": True,
            # Skip the LLM reply so the handler goes straight to waiting.
            "empty_mention_waiting_need_reply": False,
        },
        "wake_prefix": [],
    }
    return main


@pytest.mark.asyncio
async def test_other_members_message_passes_through():
    """BOB's message must not be stopped, modified, or re-enqueued."""
    main = make_main()
    queue = main.context.get_event_queue.return_value
    trigger = FakeEvent(ALICE, "", [At(qq=BOT_ID, name=BOT_ID)])

    async def drain() -> None:
        async for _ in main.handle_empty_mention(trigger):
            pass

    task = asyncio.create_task(drain())
    await asyncio.sleep(0.05)  # let the handler reach (or skip) the waiter
    assert len(USER_SESSIONS) == 1, "waiter should be registered"

    bob_event = FakeEvent(BOB, "just chatting", [Plain("just chatting")])
    await main.handle_session_control_agent(bob_event)

    assert bob_event.stop_event_calls == 0, "BOB's event must not be stopped"
    queue.put_nowait.assert_not_called()
    assert isinstance(bob_event.message_obj.message[0], Plain), (
        "no At component may be injected into BOB's message"
    )
    assert len(USER_SESSIONS) == 1, "the waiter must still be waiting for ALICE"

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_original_senders_followup_is_redispatched():
    """ALICE's follow-up gets the bot At injected, is stopped and re-enqueued."""
    main = make_main()
    queue = main.context.get_event_queue.return_value
    trigger = FakeEvent(ALICE, "", [At(qq=BOT_ID, name=BOT_ID)])

    async def drain() -> None:
        async for _ in main.handle_empty_mention(trigger):
            pass

    task = asyncio.create_task(drain())
    await asyncio.sleep(0.05)  # let the handler reach (or skip) the waiter

    followup = FakeEvent(ALICE, "hello bot", [Plain("hello bot")])
    await main.handle_session_control_agent(followup)

    assert followup.stop_event_calls > 0, "the consumed follow-up must be stopped"
    queue.put_nowait.assert_called_once()
    injected = followup.message_obj.message[0]
    assert isinstance(injected, At) and str(injected.qq) == BOT_ID
    await task  # controller.stop() lets the handler complete
    assert USER_SESSIONS == {}, "the waiter must be cleaned up after consuming"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_sender", [None, 0, False, [], b""])
async def test_unusable_sender_id_skips_waiting(monkeypatch, bad_sender):
    """A sender id that is not a non-empty string must not start a waiter.

    A truthiness check on ``str(sender_id)`` would pass here: ``str(None)`` is
    ``"None"``, which is truthy, so the waiter would register under a key like
    ``...:None``. The guard must therefore check the type as well.
    """
    main = make_main()
    trigger = FakeEvent(bad_sender, "", [At(qq=BOT_ID, name=BOT_ID)])
    monkeypatch.setattr(main_module.logger, "warning", lambda *a, **k: None)

    async def drain() -> None:
        async for _ in main.handle_empty_mention(trigger):
            pass

    task = asyncio.create_task(drain())
    await asyncio.sleep(0.05)  # let the handler reach (or skip) the waiter

    assert task.done(), f"handler must not wait for sender id {bad_sender!r}"
    assert USER_SESSIONS == {}, f"no waiter may register for {bad_sender!r}"
    assert FILTERS == []


@pytest.mark.asyncio
async def test_empty_sender_id_skips_waiting(monkeypatch):
    """Without a reliable sender id no waiter may be registered at all.

    Skipping fails closed: the feature is unavailable for that message rather
    than falling back to a group-wide key that another member could satisfy.
    A warning must be emitted so the situation stays observable.

    The warning is asserted through a patched logger rather than pytest's
    caplog because astrbot's logger sets ``propagate = False`` (records are
    forwarded to loguru), so they never reach the root handler caplog installs.
    """
    main = make_main()
    trigger = FakeEvent("", "", [At(qq=BOT_ID, name=BOT_ID)])

    warnings = []
    monkeypatch.setattr(
        main_module.logger,
        "warning",
        lambda msg, *args, **kwargs: warnings.append(msg % args if args else msg),
    )

    async def drain() -> None:
        async for _ in main.handle_empty_mention(trigger):
            pass

    task = asyncio.create_task(drain())
    await asyncio.sleep(0.05)  # let the handler reach (or skip) the waiter

    assert task.done(), "handler must finish immediately instead of waiting"
    assert USER_SESSIONS == {}, "no waiter may be registered without a sender id"
    assert FILTERS == []
    assert any("no sender id" in w for w in warnings), (
        f"skipping the wait must be logged, not silent; got {warnings}"
    )
