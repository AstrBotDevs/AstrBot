"""Response filtering uses the actual message component payloads."""

import pytest

from astrbot.core.message.components import (
    At,
    ComponentType,
    Image,
    Plain,
    Record,
    Video,
)
from astrbot.core.pipeline.respond.stage import RespondStage


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        (Plain(""), False),
        (Plain("  "), False),
        (Plain("hello"), True),
        (Image(file="/tmp/image.png"), True),
        (Image(file=""), False),
        (Image(file="", url="https://example.invalid/image.png"), True),
        (Record(file="/tmp/audio.wav"), True),
        (Video(file="/tmp/video.mp4"), True),
        (At(qq="42"), True),
    ],
)
def test_meaningful_content_uses_component_fields(component, expected: bool) -> None:
    assert RespondStage()._has_meaningful_content(component) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chain", "empty"),
    [([], True), ([Plain(" ")], True), ([Plain(""), Plain("hello")], False)],
)
async def test_empty_chain_filter_checks_all_components(chain, empty: bool) -> None:
    assert await RespondStage()._is_empty_message_chain(chain) is empty


@pytest.mark.parametrize("mutate", [True, False])
def test_component_extraction_preserves_order_and_requested_ownership(
    mutate: bool,
) -> None:
    first, second, third = Plain("one"), At(qq="42"), Plain("two")
    chain = [first, second, third]
    extracted = RespondStage()._extract_comp(
        chain, {ComponentType.Plain}, modify_raw_chain=mutate
    )
    assert extracted == [first, third]
    assert chain == ([second] if mutate else [first, second, third])
