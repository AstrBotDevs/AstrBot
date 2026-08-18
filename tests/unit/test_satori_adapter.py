from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.api.message_components import Plain
from astrbot.core.platform.sources.satori.satori_adapter import SatoriPlatformAdapter

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_satori_handle_message_background_dispatches_event_handlers():
    adapter = SatoriPlatformAdapter(
        {
            "id": "satori-test",
            "satori_endpoint": "ws://localhost:5140/satori/v1/events",
        },
        {},
        asyncio.Queue(),
    )

    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()

    async def _handle_event(event_data: dict) -> None:
        if event_data["message"]["id"] == "first":
            first_started.set()
            await release_first.wait()
            return
        if event_data["message"]["id"] == "second":
            second_started.set()

    adapter.handle_event = _handle_event  # type: ignore[method-assign]

    await adapter.handle_message(
        json.dumps(
            {
                "op": 0,
                "body": {
                    "sn": 10,
                    "type": "message-created",
                    "message": {"id": "first"},
                },
            }
        )
    )
    await asyncio.wait_for(first_started.wait(), timeout=1.0)

    await adapter.handle_message(
        json.dumps(
            {
                "op": 0,
                "body": {
                    "sn": 11,
                    "type": "message-created",
                    "message": {"id": "second"},
                },
            }
        )
    )
    await asyncio.wait_for(second_started.wait(), timeout=1.0)
    assert adapter.sequence == 11

    release_first.set()
    if adapter._event_tasks:
        await asyncio.gather(*list(adapter._event_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_satori_parse_elements_keeps_audio_lazy():
    adapter = SatoriPlatformAdapter(
        {
            "id": "satori-test",
            "satori_endpoint": "ws://localhost:5140/satori/v1/events",
        },
        {},
        asyncio.Queue(),
    )

    elements = await adapter.parse_satori_elements(
        '<audio src="https://example.test/voice.ogg" />'
    )

    assert len(elements) == 1
    record = elements[0]
    assert record.file == ""

    media_resolver = SimpleNamespace(to_path=AsyncMock(return_value="/tmp/satori.wav"))
    with patch(
        "astrbot.core.platform.sources.satori.satori_adapter.MediaResolver",
        return_value=media_resolver,
    ):
        await record._resolve_deferred_source()

    assert record.file == "/tmp/satori.wav"
    assert record.path == "/tmp/satori.wav"
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")


@pytest.mark.asyncio
async def test_satori_parse_elements_rejects_xml_entities():
    adapter = SatoriPlatformAdapter(
        {
            "id": "satori-test",
            "satori_endpoint": "ws://localhost:5140/satori/v1/events",
        },
        {},
        asyncio.Queue(),
    )
    payload = '<!DOCTYPE root [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><p>&xxe;</p>'

    elements = await adapter.parse_satori_elements(payload)

    assert elements == [Plain(text=payload)]


def test_satori_create_event_does_not_promote_member_roles():
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.message_type import MessageType

    adapter = SatoriPlatformAdapter(
        {
            "id": "satori-test",
            "satori_endpoint": "ws://localhost:5140/satori/v1/events",
        },
        {},
        asyncio.Queue(),
    )
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = "guild-1"
    message.session_id = "channel-1"
    message.sender = MessageMember("user-1", "tester")
    message.raw_message = {
        "guild": {"id": "guild-1"},
        "user": {"id": "user-1", "roles": ["admin"]},
        "member": {"roles": ["owner"]},
    }
    message.message_str = "hello"
    message.message = []
    event = adapter.create_event(message)
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"
