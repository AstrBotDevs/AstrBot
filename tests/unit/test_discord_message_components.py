from types import SimpleNamespace

import pytest

from astrbot.api.message_components import BaseMessageComponent, File, Image, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.platform.sources.discord.components import (
    DiscordButton,
    DiscordEmbed,
    DiscordReference,
    DiscordView,
)
from astrbot.core.platform.sources.discord.discord_platform_event import (
    DiscordPlatformEvent,
    DiscordViewComponent,
)


def test_discord_components_construct() -> None:
    embed = DiscordEmbed(title="test")
    button = DiscordButton(label="Click")
    view = DiscordView(components=[button])
    reference = DiscordReference(message_id="1", channel_id="2")
    view_component = DiscordViewComponent(object())

    assert embed.title == "test"
    assert button.label == "Click"
    assert view.components == [button]
    assert reference.message_id == "1"
    assert view_component.view is not None


@pytest.mark.asyncio
async def test_parse_to_discord_handles_discord_embed() -> None:
    chain = MessageChain(chain=[DiscordEmbed(title="test")])

    (
        content,
        files,
        view,
        embeds,
        reference,
    ) = await DiscordPlatformEvent._parse_to_discord(
        object(),
        chain,
    )

    assert content == ""
    assert files == []
    assert view is None
    assert reference is None
    assert len(embeds) == 1
    assert embeds[0].title == "test"


@pytest.mark.asyncio
async def test_parse_to_discord_handles_duck_typed_discord_embed() -> None:
    class CompatibleDiscordEmbed(BaseMessageComponent):
        type: str = "discord_embed"
        title: str | None = None

        def __init__(self, title: str) -> None:
            super().__init__(title=title)

    chain = SimpleNamespace(chain=[CompatibleDiscordEmbed("duck")])

    _, _, _, embeds, _ = await DiscordPlatformEvent._parse_to_discord(object(), chain)

    assert len(embeds) == 1
    assert embeds[0].title == "duck"


@pytest.mark.asyncio
async def test_respond_stage_keeps_non_empty_discord_components() -> None:
    stage = RespondStage()

    assert DiscordEmbed().empty() is True
    assert DiscordView().empty() is True
    assert await stage._is_empty_message_chain([DiscordEmbed(title="test")]) is False
    assert (
        await stage._is_empty_message_chain(
            [DiscordView(components=[DiscordButton(label="Click")])],
        )
        is False
    )


@pytest.mark.asyncio
async def test_plain_image_file_regression(tmp_path) -> None:
    stage = RespondStage()
    file_path = tmp_path / "example.txt"
    file_path.write_text("hello")

    assert await stage._is_empty_message_chain([Plain("hello")]) is False
    assert await stage._is_empty_message_chain([Image.fromBase64("aGVsbG8=")]) is False
    assert (
        await stage._is_empty_message_chain(
            [File(name="example.txt", file=str(file_path))],
        )
        is False
    )

    (
        content,
        files,
        view,
        embeds,
        reference,
    ) = await DiscordPlatformEvent._parse_to_discord(
        object(),
        MessageChain(
            chain=[
                Plain("hello"),
                Image.fromBase64("aGVsbG8="),
            ],
        ),
    )

    assert content == "hello"
    assert len(files) == 1
    assert view is None
    assert embeds == []
    assert reference is None
