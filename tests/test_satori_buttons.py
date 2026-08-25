import asyncio

import pytest

from astrbot.api.message_components import (
    ActionRow,
    Button,
    ButtonInteraction,
    ButtonStyle,
    CallbackAction,
    UrlAction,
)
from astrbot.core.platform.button_interaction import decode_button_callback
from astrbot.core.platform.sources.satori.satori_adapter import (
    SatoriPlatformAdapter,
)
from astrbot.core.platform.sources.satori.satori_event import SatoriPlatformEvent
from tests.fixtures.helpers import make_platform_config


def _build_adapter() -> SatoriPlatformAdapter:
    return SatoriPlatformAdapter(
        make_platform_config("satori", id="test_satori"),
        {},
        asyncio.Queue(),
    )


@pytest.mark.asyncio
async def test_satori_renders_portable_callback_and_link_buttons():
    rendered = await SatoriPlatformEvent._convert_component_to_satori_static(
        ActionRow(
            buttons=[
                Button(
                    id="approve",
                    label="Approve & continue",
                    action=CallbackAction(data={"request_id": 42}),
                    style=ButtonStyle.SUCCESS,
                ),
                Button(
                    id="docs",
                    label="Docs",
                    action=UrlAction(url="https://example.com/?a=1&b=2"),
                    style=ButtonStyle.PRIMARY,
                ),
            ]
        )
    )

    assert rendered.count("<button") == 2
    assert 'type="action"' in rendered
    assert 'theme="success"' in rendered
    assert "Approve &amp; continue" in rendered
    assert 'type="link"' in rendered
    assert 'href="https://example.com/?a=1&amp;b=2"' in rendered

    callback_id = rendered.split('id="', 1)[1].split('"', 1)[0]
    assert decode_button_callback(callback_id) == (
        "approve",
        {"request_id": 42},
    )


def test_satori_button_interaction_enters_portable_pipeline():
    adapter = _build_adapter()
    callback_markup = asyncio.run(
        SatoriPlatformEvent._convert_component_to_satori_static(
            Button(
                id="approve",
                label="Approve",
                action=CallbackAction(data={"request_id": 42}),
            )
        )
    )
    callback_id = callback_markup.split('id="', 1)[1].split('"', 1)[0]

    message = adapter.convert_satori_button_interaction(
        {
            "sn": 17,
            "type": "interaction/button",
            "timestamp": 1_700_000_000,
            "button": {"id": callback_id},
            "channel": {"id": "channel-1"},
            "guild": {"id": "guild-1"},
            "operator": {"id": "user-1", "name": "Alice"},
            "login": {"platform": "test", "user": {"id": "bot-1"}},
            "message": {"id": "source-message-1"},
        }
    )

    assert message is not None
    assert message.session_id == "channel-1"
    assert message.group_id == "guild-1"
    assert message.sender.user_id == "user-1"
    assert message.message_str == "approve"
    interaction = message.message[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "approve"
    assert interaction.data == {"request_id": 42}
    assert interaction.interaction_id == "17"
    assert interaction.source_message_id == "source-message-1"


@pytest.mark.asyncio
async def test_satori_dispatches_button_interaction(monkeypatch):
    adapter = _build_adapter()
    rendered = await SatoriPlatformEvent._convert_component_to_satori_static(
        Button(
            id="approve",
            label="Approve",
            action=CallbackAction(),
        )
    )
    callback_id = rendered.split('id="', 1)[1].split('"', 1)[0]
    dispatched = []
    monkeypatch.setattr(adapter, "commit_event", dispatched.append)

    await adapter.handle_event(
        {
            "sn": 18,
            "type": "interaction/button",
            "button": {"id": callback_id},
            "channel": {"id": "channel-1"},
            "operator": {"id": "user-1"},
            "login": {"platform": "test", "user": {"id": "bot-1"}},
        }
    )

    assert len(dispatched) == 1
    assert dispatched[0].is_button_interaction()
