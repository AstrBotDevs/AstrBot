import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
from astrbot.core.platform.button_interaction import (
    decode_button_callback,
    encode_button_callback,
)
from astrbot.core.platform.sources.mattermost.client import MattermostClient
from astrbot.core.platform.sources.mattermost.mattermost_adapter import (
    MattermostPlatformAdapter,
)
from tests.fixtures.helpers import make_platform_config


def _build_adapter() -> MattermostPlatformAdapter:
    adapter = MattermostPlatformAdapter(
        make_platform_config(
            "mattermost",
            id="test_mattermost",
            mattermost_url="https://chat.example.com",
            mattermost_bot_token="test_token",
            mattermost_reconnect_delay=5.0,
        ),
        {},
        asyncio.Queue(),
    )
    adapter.bot_self_id = "bot-id"
    adapter.bot_username = "bot"
    adapter._mention_pattern = adapter._build_mention_pattern(adapter.bot_username)
    return adapter


@pytest.mark.asyncio
async def test_mattermost_convert_message_strips_leading_self_mention():
    adapter = _build_adapter()

    result = await adapter.convert_message(
        post={
            "id": "post-1",
            "channel_id": "channel-1",
            "user_id": "user-1",
            "message": "@bot /help now",
            "create_at": 1_700_000_000_000,
            "file_ids": [],
        },
        data={
            "channel_type": "O",
            "sender_name": "alice",
        },
    )

    assert result is not None
    assert result.message_str == "/help now"
    assert isinstance(result.message[0], Comp.At)
    assert result.message[0].qq == "bot-id"
    assert any(
        isinstance(component, Comp.Plain) and component.text.strip() == "/help now"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_mattermost_parse_post_attachments_maps_media_types(tmp_path):
    client = MattermostClient("https://chat.example.com", "test_token")
    wav_path = str(tmp_path / "mattermost_voice.wav")

    file_infos = {
        "img": {"name": "image.png", "mime_type": "image/png"},
        "audio": {"name": "voice.ogg", "mime_type": "audio/ogg"},
        "video": {"name": "clip.mp4", "mime_type": "video/mp4"},
        "doc": {"name": "report.pdf", "mime_type": "application/pdf"},
    }

    client.get_file_info = AsyncMock(side_effect=lambda file_id: file_infos[file_id])
    client.download_file = AsyncMock(return_value=b"payload")

    class FakeMediaResolver:
        def __init__(self, media_ref: str, **kwargs) -> None:
            assert media_ref.endswith("mattermost_audio.ogg")
            assert kwargs["media_type"] == "audio"

        async def to_path(self, **kwargs) -> str:
            assert kwargs["target_format"] == "wav"
            return wav_path

    with (
        patch(
            "astrbot.core.platform.sources.mattermost.client.get_astrbot_temp_path",
            MagicMock(return_value=str(tmp_path)),
        ),
        patch(
            "astrbot.core.platform.sources.mattermost.client.MediaResolver",
            FakeMediaResolver,
        ),
    ):
        components, temp_paths = await client.parse_post_attachments(
            ["img", "audio", "video", "doc"]
        )

    assert len(components) == 4
    assert isinstance(components[0], Comp.Image)
    assert isinstance(components[1], Comp.Record)
    assert components[1].file == wav_path
    assert components[1].url == wav_path
    assert isinstance(components[2], Comp.Video)
    assert isinstance(components[3], Comp.File)
    assert len(temp_paths) == 4

    expected_names = ["image.png", "voice.ogg", "clip.mp4", "report.pdf"]
    for temp_path, expected_name in zip(temp_paths, expected_names):
        path = Path(temp_path)
        assert path.exists()
        assert path.name.endswith(Path(expected_name).suffix)


@pytest.mark.asyncio
async def test_mattermost_send_message_chain_maps_portable_buttons():
    callback_url = "https://bot.example.com/api/platform/webhook/mattermost-callback"
    client = MattermostClient(
        "https://chat.example.com",
        "test_token",
        action_callback_url=callback_url,
    )
    client.create_post = AsyncMock(return_value={"id": "post-1"})

    await client.send_message_chain(
        "channel-1",
        MessageChain(
            [
                Comp.Plain("Review request"),
                Comp.ActionRow(
                    buttons=[
                        Comp.Button(
                            id="approve",
                            label="Approve",
                            action=Comp.CallbackAction(data={"request_id": 42}),
                            style=Comp.ButtonStyle.SUCCESS,
                        ),
                        Comp.Button(
                            id="details",
                            label="Details",
                            action=Comp.UrlAction(url="https://example.com/42"),
                            style=Comp.ButtonStyle.PRIMARY,
                        ),
                    ],
                    fallback_text="Review actions",
                ),
            ]
        ),
    )

    payload = client.create_post.await_args.kwargs
    callback_token = payload["props"]["attachments"][0]["actions"][0]["integration"][
        "context"
    ]["astrbot_callback"]
    assert payload["props"] == {
        "attachments": [
            {
                "fallback": "Review actions",
                "text": "Review actions\n[Details](https://example.com/42)",
                "actions": [
                    {
                        "id": "astrbot1b0",
                        "type": "button",
                        "name": "Approve",
                        "style": "success",
                        "integration": {
                            "url": callback_url,
                            "context": {
                                "astrbot_callback": callback_token,
                            },
                        },
                    }
                ],
            }
        ]
    }
    assert decode_button_callback(callback_token) == (
        "approve",
        {"request_id": 42},
    )


@pytest.mark.asyncio
async def test_mattermost_callback_button_degrades_without_public_callback():
    client = MattermostClient("https://chat.example.com", "test_token")
    client.create_post = AsyncMock(return_value={"id": "post-1"})

    await client.send_message_chain(
        "channel-1",
        MessageChain(
            [
                Comp.ActionRow(
                    buttons=[
                        Comp.Button(
                            id="approve",
                            label="Approve",
                            action=Comp.CallbackAction(),
                        )
                    ],
                    fallback_text="Choose an action",
                )
            ]
        ),
    )

    attachment = client.create_post.await_args.kwargs["props"]["attachments"][0]
    assert attachment == {
        "fallback": "Choose an action",
        "text": "Choose an action\nApprove",
    }


@pytest.mark.asyncio
async def test_mattermost_webhook_acknowledges_then_dispatches_button():
    adapter = _build_adapter()
    adapter.client.get_channel = AsyncMock(return_value={"type": "O"})
    callback_token = encode_button_callback(
        "approve",
        {"request_id": 42},
    )

    class FakeRequest:
        async def get_json(self, *, silent: bool = False):
            assert silent is False
            return {
                "trigger_id": "trigger-1",
                "user_id": "user-1",
                "user_name": "alice",
                "channel_id": "channel-1",
                "post_id": "post-1",
                "context": {"astrbot_callback": callback_token},
            }

    response = await adapter.webhook_callback(FakeRequest())

    assert response == {}
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    event = adapter._event_queue.get_nowait()
    assert event.get_sender_id() == "user-1"
    assert event.get_session_id() == "channel-1"
    interaction = event.get_button_interaction()
    assert interaction is not None
    assert interaction.action_id == "approve"
    assert interaction.data == {"request_id": 42}
    assert interaction.interaction_id == "trigger-1"
    assert interaction.source_message_id == "post-1"
