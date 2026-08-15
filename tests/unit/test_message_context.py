from types import SimpleNamespace

import pytest

from astrbot.core import astr_main_agent as ama
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.message.components import (
    Face,
    File,
    Forward,
    Json,
    Node,
    Plain,
    Record,
    Video,
)
from astrbot.core.utils.message_context import MessageContextRenderer
from astrbot.core.utils.quoted_message.settings import QuotedMessageParserSettings


class _NapCatContextClient:
    def __init__(
        self,
        forward_payloads: dict[str, dict] | None = None,
        message_payloads: dict[str, object] | None = None,
    ) -> None:
        self.forward_payloads = forward_payloads or {}
        self.message_payloads = message_payloads or {}
        self.forward_requests: list[str] = []
        self.message_requests: list[str] = []

    async def get_message(self, message_id):
        key = str(message_id)
        self.message_requests.append(key)
        if key not in self.message_payloads:
            raise RuntimeError(f"no mock message payload for {key}")
        return SimpleNamespace(
            message_id=int(key) if key.isdigit() else 0,
            sender_id=10001,
            sender_nickname="Mock Sender",
            time=1720000000,
            message_str="",
            raw_message="",
            message_payload=self.message_payloads[key],
            extra={"sender": {"user_id": 10001, "nickname": "Mock Sender"}},
        )

    async def get_forward_message(self, forward_id):
        key = str(forward_id)
        self.forward_requests.append(key)
        if key not in self.forward_payloads:
            raise RuntimeError(f"no mock forward payload for {key}")
        return self.forward_payloads[key]

    async def get_image(self, **kwargs):
        raise AssertionError(f"unexpected get_image call: {kwargs}")

    async def get_file(self, **kwargs):
        raise AssertionError(f"unexpected get_file call: {kwargs}")

    async def get_group_file_url(self, **kwargs):
        raise AssertionError(f"unexpected get_group_file_url call: {kwargs}")

    async def get_private_file_url(self, **kwargs):
        raise AssertionError(f"unexpected get_private_file_url call: {kwargs}")


def _make_event(components, client: _NapCatContextClient):
    return SimpleNamespace(
        message_obj=SimpleNamespace(message=components),
        adapter=SimpleNamespace(client=client),
        get_group_id=lambda: "",
    )


@pytest.mark.asyncio
async def test_message_context_uses_embedded_nested_forward_content_without_refetch():
    image_url = "https://img.example.com/mock-forward.jpg"
    client = _NapCatContextClient(
        {
            "9000000000000000001": {
                "status": "ok",
                "retcode": 0,
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Mock Outer"},
                            "message": [
                                {
                                    "type": "forward",
                                    "data": {
                                        "id": "9000000000000000002",
                                        "content": [
                                            {
                                                "sender": {"nickname": "Mock Inner"},
                                                "message": [
                                                    {
                                                        "type": "text",
                                                        "data": {"text": "nested text"},
                                                    },
                                                    {
                                                        "type": "image",
                                                        "data": {"url": image_url},
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
        }
    )
    event = _make_event([Forward(id="9000000000000000001")], client)

    rendered = await MessageContextRenderer(event).render_event_components()

    assert "Mock Inner: nested text[Image]" in (rendered.text or "")
    assert rendered.image_refs == [image_url]
    assert client.forward_requests == ["9000000000000000001"]

    rendered_again = await MessageContextRenderer(event).render_event_components()

    assert "Mock Inner: nested text[Image]" in (rendered_again.text or "")
    assert client.forward_requests == ["9000000000000000001"]


@pytest.mark.asyncio
async def test_message_context_renders_embedded_components_and_rich_messages():
    client = _NapCatContextClient()
    event = _make_event(
        [
            Forward(
                id="mock-embedded",
                content=[
                    Node(
                        name="Mock Sender",
                        uin="10001",
                        content=[Plain(text="embedded text")],
                    )
                ],
            ),
            Json(data={"mock": True}),
        ],
        client,
    )

    rendered = await MessageContextRenderer(event).render_event_components()

    assert "Mock Sender: embedded text" in (rendered.text or "")
    assert '[JSON]\n{"mock": true}' in (rendered.text or "")
    assert client.forward_requests == []


@pytest.mark.asyncio
async def test_message_context_renders_qq_face_semantics_for_direct_and_forwarded_faces():
    client = _NapCatContextClient(
        {
            "forward-face": {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Mock Sender"},
                            "message": [{"type": "face", "data": {"id": "111"}}],
                        }
                    ]
                }
            }
        }
    )
    event = _make_event([Face(id=111), Forward(id="forward-face")], client)

    rendered = await MessageContextRenderer(event).render_event_components()

    assert (rendered.text or "").count("[QQ Face: 可怜 (id: 111)]") == 2


@pytest.mark.asyncio
async def test_message_context_fetches_existing_node_content_on_demand():
    client = _NapCatContextClient(
        message_payloads={
            "9001": [
                {"type": "text", "data": {"text": "existing node text"}},
                {
                    "type": "record",
                    "data": {"url": "https://media.example.com/node-audio.amr"},
                },
                {
                    "type": "video",
                    "data": {"url": "https://media.example.com/node-video.mp4"},
                },
                {
                    "type": "file",
                    "data": {"url": "https://files.example.com/node-file.txt"},
                },
            ]
        }
    )
    event = _make_event(
        [Node(id="9001", name="Mock Existing Sender", content=[])],
        client,
    )

    rendered = await MessageContextRenderer(event).render_event_components()

    assert "Mock Existing Sender: existing node text" in (rendered.text or "")
    assert [type(component) for component in rendered.nested_media] == [
        Record,
        Video,
        File,
    ]
    assert client.message_requests == ["9001"]


@pytest.mark.asyncio
async def test_message_context_renders_rich_segments_from_fetched_forward():
    client = _NapCatContextClient(
        {
            "mock-rich-forward": {
                "data": {
                    "messages": [
                        {
                            "type": "node",
                            "data": {
                                "user_id": "10001",
                                "nickname": "Mock Rich Sender",
                                "message": [
                                    {
                                        "type": "image",
                                        "data": {
                                            "file": "mock-image.jpg",
                                            "url": "https://img.example.com/mock.jpg",
                                        },
                                    },
                                    {
                                        "type": "record",
                                        "data": {
                                            "file": "voice.amr",
                                            "url": "https://media.example.com/mock.amr",
                                        },
                                    },
                                    {
                                        "type": "video",
                                        "data": {
                                            "file": "mock-video-token",
                                            "url": "https://media.example.com/mock.mp4",
                                        },
                                    },
                                    {
                                        "type": "file",
                                        "data": {
                                            "file": "mock.txt",
                                            "url": "https://files.example.com/mock.txt",
                                        },
                                    },
                                    {
                                        "type": "music",
                                        "data": {"type": "qq", "id": "123"},
                                    },
                                    {
                                        "type": "location",
                                        "data": {
                                            "lat": "30.0",
                                            "lon": "120.0",
                                            "title": "Mock Place",
                                        },
                                    },
                                    {
                                        "type": "markdown",
                                        "data": {"content": "# Mock Markdown"},
                                    },
                                    {
                                        "type": "onlinefile",
                                        "data": {"fileName": "mock.zip"},
                                    },
                                ],
                            },
                        }
                    ]
                }
            }
        }
    )
    event = _make_event([Forward(id="mock-rich-forward")], client)

    rendered = await MessageContextRenderer(event).render_event_components()

    assert "[Audio]" in (rendered.text or "")
    assert "[Music:qq]" in (rendered.text or "")
    assert "[Location:Mock Place (30.0, 120.0)]" in (rendered.text or "")
    assert "[Markdown]# Mock Markdown" in (rendered.text or "")
    assert "[Online File:mock.zip]" in (rendered.text or "")
    assert rendered.image_refs == ["https://img.example.com/mock.jpg"]
    assert [type(component) for component in rendered.nested_media] == [
        Record,
        Video,
        File,
    ]


@pytest.mark.asyncio
async def test_message_context_stops_cyclic_forward_ids():
    client = _NapCatContextClient(
        {
            "mock-cycle": {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Mock Cycle Sender"},
                            "message": [
                                {"type": "forward", "data": {"id": "mock-cycle"}}
                            ],
                        }
                    ]
                }
            }
        }
    )
    event = _make_event([Forward(id="mock-cycle")], client)

    rendered = await MessageContextRenderer(event).render_event_components()

    assert "[Cyclic Forward Message]" in (rendered.text or "")
    assert client.forward_requests == ["mock-cycle"]


@pytest.mark.asyncio
async def test_message_context_honors_forward_fetch_limit():
    client = _NapCatContextClient(
        {
            "mock-outer": {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Mock Outer"},
                            "message": [
                                {"type": "forward", "data": {"id": "mock-inner"}}
                            ],
                        }
                    ]
                }
            }
        }
    )
    event = _make_event([Forward(id="mock-outer")], client)
    settings = QuotedMessageParserSettings(max_forward_fetch=1)

    rendered = await MessageContextRenderer(
        event,
        settings=settings,
    ).render_event_components()

    assert "[Forward fetch limit reached]" in (rendered.text or "")
    assert client.forward_requests == ["mock-outer"]


@pytest.mark.asyncio
async def test_message_context_zero_forward_fetch_skips_remote_requests():
    client = _NapCatContextClient()
    event = _make_event([Forward(id="mock-forward")], client)

    rendered = await MessageContextRenderer(
        event,
        settings=QuotedMessageParserSettings(max_forward_fetch=0),
    ).render_event_components()

    assert "[Forward fetch limit reached]" in (rendered.text or "")
    assert client.forward_requests == []


@pytest.mark.asyncio
async def test_append_message_component_context_makes_forward_only_request_valid():
    image_url = "https://img.example.com/mock-agent-forward.jpg"
    client = _NapCatContextClient(
        {
            "mock-forward": {
                "data": {
                    "messages": [
                        {
                            "type": "node",
                            "data": {
                                "nickname": "Mock Sender",
                                "message": [
                                    {"type": "text", "data": {"text": "hello"}},
                                    {"type": "image", "data": {"url": image_url}},
                                ],
                            },
                        }
                    ]
                }
            }
        }
    )
    event = _make_event([Forward(id="mock-forward")], client)
    req = ProviderRequest(prompt="")
    config = ama.MainAgentBuildConfig(tool_call_timeout=60)

    await ama._append_message_component_context(event, req, config)

    assert any(
        "Mock Sender: hello" in part.text for part in req.extra_user_content_parts
    )
    assert req.image_urls == [image_url]
