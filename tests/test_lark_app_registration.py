import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Json, Plain
from astrbot.core.agent.stop_policy import AgentOutputStopped
from astrbot.core.platform.sources.lark.app_registration import (
    DEFAULT_FEISHU_OPEN_DOMAIN,
    DEFAULT_LARK_OPEN_DOMAIN,
    _registration_data,
    resolve_app_registration_endpoints,
)
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent


def test_resolve_app_registration_endpoints_uses_feishu_accounts_domain():
    endpoints = resolve_app_registration_endpoints(DEFAULT_FEISHU_OPEN_DOMAIN)

    assert endpoints.open_base == DEFAULT_FEISHU_OPEN_DOMAIN
    assert endpoints.registration == (
        "https://accounts.feishu.cn/oauth/v1/app/registration"
    )


def test_resolve_app_registration_endpoints_uses_lark_accounts_domain():
    endpoints = resolve_app_registration_endpoints(DEFAULT_LARK_OPEN_DOMAIN)

    assert endpoints.open_base == DEFAULT_LARK_OPEN_DOMAIN
    assert endpoints.registration == (
        "https://accounts.larksuite.com/oauth/v1/app/registration"
    )


def test_registration_data_accepts_wrapped_and_plain_payloads():
    wrapped = {"data": {"device_code": "device"}}
    plain = {"device_code": "device"}

    assert _registration_data(wrapped) == {"device_code": "device"}
    assert _registration_data(plain) == {"device_code": "device"}


@pytest.mark.asyncio
async def test_lark_file_upload_stop_blocks_message_send(monkeypatch):
    extras = {}
    event = SimpleNamespace(
        is_stopped=lambda: False,
        get_extra=lambda key, default=None: extras.get(key, default),
    )

    async def upload_then_stop(*_args, **_kwargs):
        extras["agent_stop_requested"] = True
        return "uploaded-file-key"

    send_message = AsyncMock()
    monkeypatch.setattr(LarkMessageEvent, "_upload_lark_file", upload_then_stop)
    monkeypatch.setattr(LarkMessageEvent, "_send_im_message", send_message)

    with pytest.raises(AgentOutputStopped):
        await LarkMessageEvent._send_file_message(
            SimpleNamespace(file="file.txt"),
            SimpleNamespace(),
            stop_event=event,
        )

    send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_lark_card_creation_stop_blocks_message_send(monkeypatch):
    extras = {}
    card_started = asyncio.Event()
    release_card = asyncio.Event()
    event = SimpleNamespace(
        is_stopped=lambda: False,
        get_extra=lambda key, default=None: extras.get(key, default),
    )

    class CardResult:
        data = SimpleNamespace(card_id="card-id")

        @staticmethod
        def success():
            return True

    async def create_card(_request):
        card_started.set()
        await release_card.wait()
        return CardResult()

    send_message = AsyncMock(return_value=True)
    monkeypatch.setattr(LarkMessageEvent, "_send_im_message", send_message)
    client = SimpleNamespace(
        im=object(),
        cardkit=SimpleNamespace(
            v1=SimpleNamespace(card=SimpleNamespace(acreate=create_card))
        ),
    )
    task = asyncio.create_task(
        LarkMessageEvent.send_message_chain(
            MessageChain(
                [
                    Json(
                        data={
                            "type": "lark_collapsible_panel_reasoning",
                            "content": "secret",
                        }
                    )
                ]
            ),
            client,
            stop_event=event,
        )
    )
    await asyncio.wait_for(card_started.wait(), timeout=1)
    extras["agent_stop_requested"] = True
    release_card.set()

    with pytest.raises(AgentOutputStopped):
        await task
    send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_lark_audio_path_stop_blocks_conversion(monkeypatch, tmp_path):
    extras = {}
    event = SimpleNamespace(
        is_stopped=lambda: False,
        get_extra=lambda key, default=None: extras.get(key, default),
    )
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")

    async def resolve_then_stop():
        extras["agent_stop_requested"] = True
        return str(audio_path)

    convert_audio = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.platform.sources.lark.lark_event.convert_audio_to_opus",
        convert_audio,
    )

    with pytest.raises(AgentOutputStopped):
        await LarkMessageEvent._send_audio_message(
            SimpleNamespace(convert_to_file_path=resolve_then_stop),
            SimpleNamespace(),
            stop_event=event,
        )
    convert_audio.assert_not_awaited()


@pytest.mark.asyncio
async def test_lark_rejected_post_is_reported_as_delivery_failure(monkeypatch):
    monkeypatch.setattr(
        LarkMessageEvent,
        "_convert_to_lark",
        AsyncMock(return_value=[[{"tag": "md", "text": "answer"}]]),
    )
    monkeypatch.setattr(
        LarkMessageEvent,
        "_send_im_message",
        AsyncMock(return_value=False),
    )

    with pytest.raises(RuntimeError, match="delivery failed"):
        await LarkMessageEvent.send_message_chain(
            MessageChain([Plain("answer")]),
            SimpleNamespace(im=object()),
        )
