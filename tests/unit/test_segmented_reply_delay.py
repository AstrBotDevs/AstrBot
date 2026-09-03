"""Tests for segmented reply delay scheduling."""

from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.respond.stage import RespondStage


class DummyRespondEvent:
    """Provide the event interface required by RespondStage tests."""

    def __init__(self, texts: list[str]) -> None:
        """Initialize an event containing the provided text segments.

        Args:
            texts: Text segments to include in the event result.
        """
        self._result = MessageEventResult()
        for text in texts:
            self._result.message(text)
        self._extras = {}
        self.send = AsyncMock()
        self.plugins_name = []

    def get_result(self) -> MessageEventResult | None:
        """Return the current event result."""
        return self._result

    def get_extra(self, key: str, default=None):
        """Return an event extra value.

        Args:
            key: Extra value key.
            default: Value returned when the key is missing.

        Returns:
            The stored value or the provided default.
        """
        return self._extras.get(key, default)

    def get_sender_name(self) -> str:
        """Return a sender name for logging."""
        return "tester"

    def get_sender_id(self) -> str:
        """Return a sender ID for logging."""
        return "user-1"

    def get_platform_id(self) -> str:
        """Return a platform ID for logging."""
        return "test"

    def get_platform_name(self) -> str:
        """Return a platform name eligible for segmented replies."""
        return "test"

    def _outline_chain(self, chain) -> str:
        """Return a readable message-chain outline.

        Args:
            chain: Message components to describe.

        Returns:
            Plain text contained in the message chain.
        """
        return " ".join(comp.text for comp in chain if hasattr(comp, "text"))

    def is_stopped(self) -> bool:
        """Return whether event propagation has stopped."""
        return False

    def clear_result(self) -> None:
        """Clear the current event result."""
        self._result = None


@pytest.mark.asyncio
async def test_segmented_reply_delays_only_after_first_segment() -> None:
    """Send the first segment immediately and delay the next segment."""
    stage = RespondStage()
    stage.config = {"provider_settings": {}}
    stage.platform_settings = {"path_mapping": []}
    stage.enable_seg = True
    stage.only_llm_result = False
    stage._calc_comp_interval = AsyncMock(return_value=2.0)
    event = DummyRespondEvent(["first", "second"])
    timeline = []
    event.send.side_effect = lambda chain: timeline.append(
        ("send", chain.get_plain_text()),
    )
    sleep = AsyncMock(side_effect=lambda delay: timeline.append(("sleep", delay)))

    with patch("astrbot.core.pipeline.respond.stage.asyncio.sleep", new=sleep):
        await stage.process(event)

    assert timeline == [
        ("send", "first"),
        ("sleep", 2.0),
        ("send", "second"),
    ]
    sleep.assert_awaited_once_with(2.0)
    stage._calc_comp_interval.assert_awaited_once()
    assert stage._calc_comp_interval.await_args.args[0].text == "second"


@pytest.mark.asyncio
async def test_single_segmented_reply_has_no_delay() -> None:
    """Send a single segmented reply without applying a delay."""
    stage = RespondStage()
    stage.config = {"provider_settings": {}}
    stage.platform_settings = {"path_mapping": []}
    stage.enable_seg = True
    stage.only_llm_result = False
    stage._calc_comp_interval = AsyncMock(return_value=2.0)
    event = DummyRespondEvent(["only"])
    sleep = AsyncMock()

    with patch("astrbot.core.pipeline.respond.stage.asyncio.sleep", new=sleep):
        await stage.process(event)

    event.send.assert_awaited_once()
    sleep.assert_not_awaited()
    stage._calc_comp_interval.assert_not_awaited()
