import discord
import pytest
from pydantic.v1 import ValidationError

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.discord.components import (
    DiscordButton,
    DiscordEmbed,
    DiscordReference,
    DiscordView,
)
from astrbot.core.platform.sources.discord.discord_platform_event import (
    DiscordViewComponent,
)


def test_discord_embed_can_be_constructed_and_converted():
    embed = DiscordEmbed(
        title="title",
        description="desc",
        fields=[{"name": "a", "value": "b", "inline": True}],
    )
    chain = MessageChain([embed])

    result = chain.chain[0].to_discord_embed()

    assert result.title == "title"
    assert result.description == "desc"
    assert result.fields[0].name == "a"
    assert result.fields[0].inline is True


def test_discord_reference_keeps_ids():
    ref = DiscordReference(message_id="1", channel_id="2")
    assert (ref.message_id, ref.channel_id) == ("1", "2")


@pytest.mark.asyncio
async def test_discord_view_builds_buttons():
    view = DiscordView(
        components=[
            DiscordButton(label="ok", custom_id="ok-id"),
            DiscordButton(label="docs", url="https://example.com"),
        ],
        timeout=30,
    ).to_discord_view()

    assert view.timeout == 30
    assert [item.label for item in view.children] == ["ok", "docs"]
    assert view.children[1].style == discord.ButtonStyle.link

    raw_view = discord.ui.View()
    assert DiscordViewComponent(raw_view).view is raw_view


@pytest.mark.parametrize("item", [1, "not-a-component", None])
def test_discord_view_rejects_non_component_items(item):
    """Validate each view item before constructing a Discord view.

    Args:
        item: A value outside the message-component contract.
    """
    with pytest.raises(ValidationError):
        DiscordView(components=[item])


def test_discord_view_serialization_preserves_button_fields():
    """Typed view items must retain their concrete component fields."""
    view = DiscordView(components=[DiscordButton(label="ok", custom_id="ok-id")])
    assert view.dict()["components"][0]["label"] == "ok"
