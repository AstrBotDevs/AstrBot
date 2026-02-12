from types import SimpleNamespace

import pytest

from astrbot.core.message.components import Image, Plain, Reply
from astrbot.core.utils.quoted_message_parser import (
    extract_quoted_message_images,
    extract_quoted_message_text,
)


class _DummyAPI:
    def __init__(
        self,
        responses: dict[tuple[str, str], dict],
        param_responses: dict[tuple[str, tuple[tuple[str, str], ...]], dict]
        | None = None,
    ):
        self._responses = responses
        self._param_responses = param_responses or {}

    async def call_action(self, action: str, **params):
        param_key = (action, tuple(sorted((k, str(v)) for k, v in params.items())))
        if param_key in self._param_responses:
            return self._param_responses[param_key]

        msg_id = params.get("message_id")
        if msg_id is None:
            msg_id = params.get("id")
        key = (action, str(msg_id))
        if key not in self._responses:
            raise RuntimeError(f"no mock response for {key}")
        return self._responses[key]


def _make_event(
    reply: Reply,
    responses: dict[tuple[str, str], dict] | None = None,
    param_responses: dict[tuple[str, tuple[tuple[str, str], ...]], dict] | None = None,
):
    if responses is None:
        responses = {}
    if param_responses is None:
        param_responses = {}
    return SimpleNamespace(
        message_obj=SimpleNamespace(message=[reply]),
        bot=SimpleNamespace(api=_DummyAPI(responses, param_responses)),
        get_group_id=lambda: "",
    )


@pytest.mark.asyncio
async def test_extract_quoted_message_text_from_reply_chain():
    reply = Reply(id="1", chain=[Plain(text="quoted content")], message_str="")
    event = _make_event(reply)
    text = await extract_quoted_message_text(event)
    assert text == "quoted content"


@pytest.mark.asyncio
async def test_extract_quoted_message_text_fallback_get_msg_and_forward():
    reply = Reply(id="100", chain=None, message_str="")
    event = _make_event(
        reply,
        responses={
            (
                "get_msg",
                "100",
            ): {
                "data": {
                    "message": [
                        {"type": "text", "data": {"text": "parent"}},
                        {"type": "forward", "data": {"id": "fwd_1"}},
                    ]
                }
            },
            (
                "get_forward_msg",
                "fwd_1",
            ): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [{"type": "text", "data": {"text": "hello"}}],
                        },
                        {
                            "sender": {"nickname": "Bob"},
                            "message": [
                                {"type": "image", "data": {"url": "http://img"}},
                                {"type": "text", "data": {"text": "world"}},
                            ],
                        },
                    ]
                }
            },
        },
    )

    text = await extract_quoted_message_text(event)
    assert text is not None
    assert "parent" in text
    assert "Alice: hello" in text
    assert "Bob: [Image]world" in text


@pytest.mark.asyncio
async def test_extract_quoted_message_images_from_reply_chain():
    reply = Reply(
        id="1",
        chain=[
            Plain(text="quoted"),
            Image(file="https://img.example.com/a.jpg"),
        ],
        message_str="",
    )
    event = _make_event(reply)

    images = await extract_quoted_message_images(event)
    assert images == ["https://img.example.com/a.jpg"]


@pytest.mark.asyncio
async def test_extract_quoted_message_images_fallback_get_msg_direct_url():
    reply = Reply(id="200", chain=None, message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "200"): {
                "data": {
                    "message": [
                        {
                            "type": "image",
                            "data": {"url": "https://img.example.com/direct.jpg"},
                        }
                    ]
                }
            }
        },
    )

    images = await extract_quoted_message_images(event)
    assert images == ["https://img.example.com/direct.jpg"]


@pytest.mark.asyncio
async def test_extract_quoted_message_images_fallback_resolve_file_id_with_get_image():
    reply = Reply(id="300", chain=None, message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "300"): {
                "data": {"message": [{"type": "image", "data": {"file": "abc123.jpg"}}]}
            }
        },
        param_responses={
            ("get_image", (("file", "abc123.jpg"),)): {
                "data": {"url": "https://img.example.com/resolved.jpg"}
            }
        },
    )

    images = await extract_quoted_message_images(event)
    assert images == ["https://img.example.com/resolved.jpg"]
