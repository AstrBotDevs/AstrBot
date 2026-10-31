import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.pipeline.respond.stage import RespondStage


class _PlatformCard(BaseMessageComponent):
    type: str = "platform_card"
    title: str = ""


@pytest.mark.asyncio
async def test_platform_specific_component_is_not_empty():
    stage = RespondStage()

    assert await stage._is_empty_message_chain([_PlatformCard(title="t")]) is False
    assert (
        await stage._is_empty_message_chain([Comp.Plain(text=" "), _PlatformCard()])
        is False
    )


@pytest.mark.asyncio
async def test_builtin_empty_components_are_still_empty():
    stage = RespondStage()

    assert await stage._is_empty_message_chain([]) is True
    assert (
        await stage._is_empty_message_chain(
            [Comp.Plain(text="  "), Comp.Image(file="")]
        )
        is True
    )
