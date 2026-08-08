from types import SimpleNamespace

import pytest

from astrbot.core.message.components import Face, Image, Plain, Reply
from astrbot.core.utils.quoted_message.settings import QuotedMessageParserSettings
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
        self.calls: list[str] = []

    async def call_action(self, action: str, **params):
        self.calls.append(action)
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


class _NapCatClient:
    def __init__(
        self,
        message_payloads: dict[str, object] | None = None,
        forward_payloads: dict[str, dict] | None = None,
        image_payloads: dict[tuple[str, str], dict] | None = None,
    ):
        self._message_payloads = message_payloads or {}
        self._forward_payloads = forward_payloads or {}
        self._image_payloads = image_payloads or {}
        self.forward_requests: list[str] = []

    async def get_message(self, message_id: str | int):
        key = str(message_id)
        if key not in self._message_payloads:
            raise RuntimeError(f"no mock get_message payload for {key}")
        payload = self._message_payloads[key]
        return SimpleNamespace(
            message_id=int(key) if key.isdigit() else 0,
            sender_id=123456,
            sender_nickname="tester",
            time=1720000000,
            message_str="",
            raw_message="",
            message_payload=payload,
            extra={"sender": {"user_id": 123456, "nickname": "tester"}},
        )

    async def get_forward_message(self, forward_id: str | int):
        key = str(forward_id)
        self.forward_requests.append(key)
        if key not in self._forward_payloads:
            raise RuntimeError(f"no mock get_forward_message payload for {key}")
        return self._forward_payloads[key]

    async def get_image(self, *, file: str | None = None, file_id: str | None = None):
        key = ("file_id" if file_id is not None else "file", file_id or file or "")
        if key not in self._image_payloads:
            raise RuntimeError(f"no mock get_image payload for {key}")
        return self._image_payloads[key]

    async def get_file(self, *, file: str | None = None, file_id: str | None = None):
        key = ("file_id" if file_id is not None else "file", file_id or file or "")
        if key not in self._image_payloads:
            raise RuntimeError(f"no mock get_file payload for {key}")
        return self._image_payloads[key]

    async def get_group_file_url(self, *, group_id, file_id: str):
        key = ("group_file_url", f"{group_id}:{file_id}")
        if key not in self._image_payloads:
            raise RuntimeError(f"no mock get_group_file_url payload for {key}")
        return self._image_payloads[key]

    async def get_private_file_url(self, *, file_id: str):
        key = ("private_file_url", file_id)
        if key not in self._image_payloads:
            raise RuntimeError(f"no mock get_private_file_url payload for {key}")
        return self._image_payloads[key]


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


def _make_napcat_event(
    reply: Reply,
    *,
    message_payloads: dict[str, object] | None = None,
    forward_payloads: dict[str, dict] | None = None,
    image_payloads: dict[tuple[str, str], dict] | None = None,
):
    return SimpleNamespace(
        message_obj=SimpleNamespace(message=[reply]),
        adapter=SimpleNamespace(
            client=_NapCatClient(
                message_payloads=message_payloads,
                forward_payloads=forward_payloads,
                image_payloads=image_payloads,
            )
        ),
        get_group_id=lambda: "",
    )


def test_quoted_message_parser_settings_preserve_zero_limit_overrides() -> None:
    defaults = QuotedMessageParserSettings()

    settings = defaults.with_overrides(
        {
            "max_component_chain_depth": 0,
            "max_forward_node_depth": 0,
            "max_forward_fetch": 0,
        }
    )

    assert settings.max_component_chain_depth == 0
    assert settings.max_forward_node_depth == 0
    assert settings.max_forward_fetch == 0
    assert (
        defaults.with_overrides({"max_forward_fetch": -1}).max_forward_fetch
        == defaults.max_forward_fetch
    )


@pytest.mark.asyncio
async def test_extract_quoted_message_text_from_reply_chain():
    reply = Reply(id="1", chain=[Plain(text="quoted content")], message_str="")
    event = _make_event(reply)
    text = await extract_quoted_message_text(event)
    assert text == "quoted content"


@pytest.mark.asyncio
async def test_extract_quoted_message_text_renders_qq_face_semantics():
    reply = Reply(id="1", chain=[Face(id=111)], message_str="")
    event = _make_event(reply)

    text = await extract_quoted_message_text(event)

    assert text == "[QQ Face: 可怜 (id: 111)]"


@pytest.mark.asyncio
async def test_extract_quoted_message_text_renders_raw_onebot_face_semantics():
    reply = Reply(id="face-message", chain=None, message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "face-message"): {
                "data": {"message": [{"type": "face", "data": {"id": "111"}}]}
            }
        },
    )

    text = await extract_quoted_message_text(event)

    assert text == "[QQ Face: 可怜 (id: 111)]"


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
    reply = Reply(
        id="placeholder", chain=[Plain(text="quoted content")], message_str=""
    )
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


@pytest.mark.asyncio
async def test_zero_forward_fetch_skips_forward_requests_without_a_limit_warning(
    caplog,
):
    reply = Reply(id="zero-fetch", chain=None, message_str="")
    event = _make_event(
        reply,
        responses={
            ("get_msg", "zero-fetch"): {
                "data": {
                    "message": [
                        {"type": "text", "data": {"text": "parent"}},
                        {"type": "forward", "data": {"id": "forward-1"}},
                    ]
                }
            }
        },
    )

    text = await extract_quoted_message_text(
        event,
        settings=QuotedMessageParserSettings(max_forward_fetch=0),
    )

    assert text == "parent"
    assert event.bot.api.calls == ["get_msg"]
    assert "stop fetching nested forward messages after 0 hops" not in caplog.text


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
async def test_extract_quoted_message_text_mixed_placeholder_does_not_trigger_fallback():
    reply = Reply(
        id="402",
        chain=[Plain(text="Alice: [Forward Message]\nreal text")],
        message_str="",
    )
    event = SimpleNamespace(
        message_obj=SimpleNamespace(message=[reply]),
        bot=SimpleNamespace(api=_FailIfCalledAPI()),
        get_group_id=lambda: "",
    )

    text = await extract_quoted_message_text(event)
    assert text is not None
    assert "[Forward Message]" in text
    assert "real text" in text


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
    assert text == "[JSON]still works"


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
async def test_extract_quoted_message_images_accepts_legacy_file_uri(tmp_path):
    image_file = tmp_path / "quoted.png"
    image_file.write_bytes(b"image")
    file_uri = (
        f"file:///{image_file.as_posix()}"
        if image_file.as_posix().startswith("/")
        else image_file.as_uri()
    )
    reply = Reply(id="placeholder", chain=[Image(file=file_uri)], message_str="")
    object.__setattr__(reply, "id", None)
    event = SimpleNamespace(
        message_obj=SimpleNamespace(message=[reply]),
        bot=SimpleNamespace(api=_FailIfCalledAPI()),
        get_group_id=lambda: "",
    )

    images = await extract_quoted_message_images(event)

    assert images == [str(image_file)]


@pytest.mark.asyncio
async def test_extract_quoted_message_images_non_image_local_path_is_ignored(tmp_path):
    non_image_file = tmp_path / "secret.txt"
    non_image_file.write_text("not an image", encoding="utf-8")

    reply = Reply(
        id="placeholder", chain=[Image(file=str(non_image_file))], message_str=""
    )
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


@pytest.mark.asyncio
async def test_extract_quoted_message_prefers_embedded_napcat_nested_forward_content():
    nested_image = "https://img.example.com/mock-nested-forward.jpg"
    reply = Reply(id="700", chain=[Plain(text="[Forward Message]")], message_str="")
    event = _make_napcat_event(
        reply,
        message_payloads={
            "700": [{"type": "forward", "data": {"id": "mock-outer-forward"}}]
        },
        forward_payloads={
            "mock-outer-forward": {
                "status": "ok",
                "retcode": 0,
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Mock Outer Sender"},
                            "message": [
                                {
                                    "type": "forward",
                                    "data": {
                                        "id": "mock-inner-unfetchable",
                                        "content": [
                                            {
                                                "sender": {
                                                    "nickname": "Mock Inner Sender"
                                                },
                                                "message": [
                                                    {
                                                        "type": "text",
                                                        "data": {
                                                            "text": "mock nested text"
                                                        },
                                                    },
                                                    {
                                                        "type": "image",
                                                        "data": {"url": nested_image},
                                                    },
                                                ],
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ]
                },
            }
        },
    )

    text = await extract_quoted_message_text(event)
    images = await extract_quoted_message_images(event)

    assert text is not None
    assert "Mock Inner Sender: mock nested text[Image]" in text
    assert images == [nested_image]
    assert event.adapter.client.forward_requests == [
        "mock-outer-forward",
    ]


@pytest.mark.asyncio
async def test_extract_quoted_message_text_supports_napcat_client_fallback():
    reply = Reply(id="500", chain=[Plain(text="[Forward Message]")], message_str="")
    event = _make_napcat_event(
        reply,
        message_payloads={
            "500": [
                {"type": "text", "data": {"text": "parent"}},
                {"type": "forward", "data": {"id": "fwd_napcat"}},
            ]
        },
        forward_payloads={
            "fwd_napcat": {
                "status": "ok",
                "retcode": 0,
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [{"type": "text", "data": {"text": "hello"}}],
                        },
                        {
                            "sender": {"nickname": "Bob"},
                            "message": [
                                {"type": "image", "data": {"url": "https://img/x.jpg"}},
                                {"type": "text", "data": {"text": "world"}},
                            ],
                        },
                    ]
                },
            }
        },
    )

    text = await extract_quoted_message_text(event)
    assert text is not None
    assert "parent" in text
    assert "Alice: hello" in text
    assert "Bob: [Image]world" in text


@pytest.mark.asyncio
async def test_extract_quoted_message_images_supports_napcat_client_fallback():
    reply = Reply(id="600", chain=None, message_str="")
    event = _make_napcat_event(
        reply,
        message_payloads={
            "600": [
                {"type": "image", "data": {"file": "abc123.jpg"}},
            ]
        },
        image_payloads={
            ("file", "abc123.jpg"): {
                "status": "ok",
                "retcode": 0,
                "data": {"url": "https://img.example.com/napcat-resolved.jpg"},
            }
        },
    )

    images = await extract_quoted_message_images(event)
    assert images == ["https://img.example.com/napcat-resolved.jpg"]
