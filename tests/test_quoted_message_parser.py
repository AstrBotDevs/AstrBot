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


class _FailIfCalledAPI:
    async def call_action(self, action: str, **params):
        raise AssertionError(
            f"call_action should not be called, got action={action}, params={params}"
        )


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
async def test_extract_quoted_message_text_no_reply_component():
    event = SimpleNamespace(
        message_obj=SimpleNamespace(message=[Plain(text="unquoted message")]),
        bot=SimpleNamespace(api=_DummyAPI({}, {})),
        get_group_id=lambda: "",
    )

    text = await extract_quoted_message_text(event)
    assert text is None


@pytest.mark.asyncio
async def test_extract_quoted_message_images_no_reply_component():
    event = SimpleNamespace(
        message_obj=SimpleNamespace(message=[Plain(text="unquoted message")]),
        bot=SimpleNamespace(api=_FailIfCalledAPI()),
        get_group_id=lambda: "",
    )

    images = await extract_quoted_message_images(event)
    assert images == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reply_id", [None, ""])
async def test_extract_quoted_message_text_reply_without_id_does_not_call_get_msg(
    reply_id: str | None,
):
    reply = Reply(id="placeholder", chain=[Plain(text="quoted content")], message_str="")
    object.__setattr__(reply, "id", reply_id)
    event = SimpleNamespace(
        message_obj=SimpleNamespace(message=[reply]),
        bot=SimpleNamespace(api=_FailIfCalledAPI()),
        get_group_id=lambda: "",
    )

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


@pytest.mark.parametrize(
    "placeholder_text",
    [
        "[Forward Message]",
        "[转发消息]",
        "[合并转发]",
        "Alice: [Forward Message]",
        "(Alice): [转发消息]",
        "[Forward Message]\n[转发消息]",
        "Alice: [Forward Message]\n(Bob): [合并转发]",
        "[转发消息]\n\n[合并转发]",
    ],
)
@pytest.mark.asyncio
async def test_extract_quoted_message_text_forward_placeholder_variants_trigger_fallback(
    placeholder_text: str,
):
    reply = Reply(id="400", chain=[Plain(text=placeholder_text)], message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "400"): {
                "data": {
                    "message": [
                        {"type": "text", "data": {"text": "Bob: "}},
                        {"type": "image", "data": {}},
                        {"type": "text", "data": {"text": "world"}},
                    ]
                }
            }
        },
    )

    text = await extract_quoted_message_text(event)
    assert "Bob: [Image]world" in text


@pytest.mark.asyncio
async def test_extract_quoted_message_text_forward_placeholder_fallback_failure():
    reply = Reply(id="401", chain=[Plain(text="[Forward Message]")], message_str="")
    event = _make_event(reply, responses={})

    text = await extract_quoted_message_text(event)
    assert text == "[Forward Message]"


@pytest.mark.asyncio
async def test_extract_quoted_message_text_multimsg_malformed_config_does_not_raise():
    reply = Reply(id="402", chain=None, message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "402"): {
                "data": {
                    "message": [
                        {
                            "type": "json",
                            "data": {
                                "data": (
                                    '{"app":"com.tencent.multimsg",'
                                    '"config":"oops","meta":{}}'
                                )
                            },
                        },
                        {"type": "text", "data": {"text": "still works"}},
                    ]
                }
            }
        },
    )

    text = await extract_quoted_message_text(event)
    assert text == "still works"


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
async def test_extract_quoted_message_images_data_image_ref_normalized_to_base64():
    data_image_ref = "data:image/png;base64,abcd1234=="
    reply = Reply(id="201", chain=None, message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "201"): {
                "data": {
                    "message": [
                        {"type": "image", "data": {"url": data_image_ref}},
                    ]
                }
            }
        },
    )

    images = await extract_quoted_message_images(event)
    assert images == ["base64://abcd1234=="]


@pytest.mark.asyncio
async def test_extract_quoted_message_images_file_url_with_query_string():
    url_with_query = "https://img.example.com/direct.jpg?token=abc123#frag"
    reply = Reply(id="205", chain=None, message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "205"): {
                "data": {
                    "message": [
                        {
                            "type": "file",
                            "data": {
                                "url": url_with_query,
                                "name": "direct.jpg",
                            },
                        }
                    ]
                }
            }
        },
    )

    images = await extract_quoted_message_images(event)
    assert images == [url_with_query]


@pytest.mark.asyncio
async def test_extract_quoted_message_images_non_image_local_path_is_ignored(tmp_path):
    non_image_file = tmp_path / "secret.txt"
    non_image_file.write_text("not an image", encoding="utf-8")

    reply = Reply(id="placeholder", chain=[Image(file=str(non_image_file))], message_str="")
    object.__setattr__(reply, "id", None)
    event = SimpleNamespace(
        message_obj=SimpleNamespace(message=[reply]),
        bot=SimpleNamespace(api=_FailIfCalledAPI()),
        get_group_id=lambda: "",
    )

    images = await extract_quoted_message_images(event)
    assert images == []


@pytest.mark.asyncio
async def test_extract_quoted_message_images_chain_placeholder_triggers_fallback():
    reply = Reply(id="210", chain=[Plain(text="[Forward Message]")], message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "210"): {
                "data": {
                    "message": [
                        {
                            "type": "image",
                            "data": {
                                "url": "https://img.example.com/from-fallback.jpg"
                            },
                        }
                    ]
                }
            }
        },
    )

    images = await extract_quoted_message_images(event)
    assert images == ["https://img.example.com/from-fallback.jpg"]


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


@pytest.mark.asyncio
async def test_extract_quoted_message_images_deduplicates_across_sources():
    dup_url = "https://img.example.com/dup.jpg"
    chain_only_url = "https://img.example.com/only-chain.jpg"
    get_msg_only_url = "https://img.example.com/only-get-msg.jpg"
    forward_only_url = "https://img.example.com/only-forward.jpg"

    reply = Reply(
        id="310",
        chain=[Image(file=dup_url), Image(file=chain_only_url)],
        message_str="",
    )

    event = _make_event(
        reply,
        responses={
            ("get_msg", "310"): {
                "data": {
                    "message": [
                        {"type": "image", "data": {"url": dup_url}},
                        {"type": "image", "data": {"url": get_msg_only_url}},
                        {"type": "forward", "data": {"id": "999"}},
                    ]
                }
            },
            ("get_forward_msg", "999"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Tester"},
                            "message": [
                                {"type": "image", "data": {"url": dup_url}},
                                {"type": "image", "data": {"url": forward_only_url}},
                            ],
                        }
                    ]
                }
            },
        },
    )

    images = await extract_quoted_message_images(event)
    assert images == [
        dup_url,
        chain_only_url,
        get_msg_only_url,
        forward_only_url,
    ]


@pytest.mark.asyncio
async def test_extract_quoted_message_nested_forward_id_is_resolved():
    nested_image = "https://img.example.com/nested.jpg"
    reply = Reply(id="320", chain=[Plain(text="[Forward Message]")], message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "320"): {
                "data": {"message": [{"type": "forward", "data": {"id": "fwd_1"}}]}
            },
            ("get_forward_msg", "fwd_1"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [{"type": "forward", "data": {"id": "fwd_2"}}],
                        }
                    ]
                }
            },
            ("get_forward_msg", "fwd_2"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Bob"},
                            "message": [
                                {"type": "text", "data": {"text": "deep"}},
                                {"type": "image", "data": {"url": nested_image}},
                            ],
                        }
                    ]
                }
            },
        },
    )

    text = await extract_quoted_message_text(event)
    assert text is not None
    assert "Bob: deep" in text

    images = await extract_quoted_message_images(event)
    assert images == [nested_image]
