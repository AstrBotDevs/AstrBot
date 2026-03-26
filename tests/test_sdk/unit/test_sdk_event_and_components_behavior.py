from __future__ import annotations

import base64
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from astrbot_sdk import (
    At,
    AtAll,
    Context,
    File,
    Forward,
    Image,
    MediaHelper,
    MessageBuilder,
    MessageChain,
    MessageEvent,
    Plain,
    Poke,
    Record,
    Reply,
    UnknownComponent,
    Video,
)
from astrbot_sdk.message_components import (
    component_to_payload_sync,
    payloads_to_components,
)
from astrbot_sdk.protocol.descriptors import SessionRef


class _BehaviorPeer:
    def __init__(self) -> None:
        self.remote_peer = {"name": "behavior-core"}
        self.remote_capability_map = {
            "platform.send": SimpleNamespace(supports_stream=False),
            "platform.send_image": SimpleNamespace(supports_stream=False),
            "platform.send_chain": SimpleNamespace(supports_stream=False),
        }
        self.sent_messages: list[dict[str, object]] = []

    async def invoke(
        self,
        capability: str,
        payload: dict[str, object],
        *,
        stream: bool = False,
    ) -> dict[str, object]:
        if stream:
            raise AssertionError("unexpected stream invocation")
        if capability not in self.remote_capability_map:
            raise AssertionError(f"unexpected capability: {capability}")

        normalized: dict[str, object] = {
            "capability": capability,
            "session": payload.get("session"),
            "target": payload.get("target"),
        }
        if capability == "platform.send":
            normalized["text"] = payload.get("text")
        elif capability == "platform.send_image":
            normalized["image_url"] = payload.get("image_url")
        else:
            normalized["chain"] = payload.get("chain")
        self.sent_messages.append(normalized)
        return {"message_id": f"message-{len(self.sent_messages)}"}

    async def invoke_stream(self, capability: str, payload: dict[str, object]):
        raise AssertionError(f"unexpected stream capability: {capability} {payload}")


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        del format, args


@pytest.fixture
def media_server(tmp_path: Path):
    assets = {
        "image.jpg": b"fake-image-bytes",
        "audio.mp3": b"fake-audio-bytes",
        "video.mp4": b"fake-video-bytes",
        "doc.bin": b"fake-doc-bytes",
    }
    for name, content in assets.items():
        (tmp_path / name).write_bytes(content)

    handler = functools.partial(_QuietStaticHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", assets
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.unit
def test_message_event_component_access_and_result_behaviors() -> None:
    payload = {
        "text": "hello world",
        "user_id": "user-1",
        "group_id": "room-7",
        "session_id": "demo:group:room-7",
        "platform": "demo",
        "platform_id": "demo-main",
        "message_type": "group",
        "is_admin": True,
        "messages": [
            {"type": "text", "data": {"text": "hello"}},
            {"type": "at", "data": {"qq": "user-2"}},
            {"type": "at", "data": {"qq": "all"}},
            {"type": "image", "data": {"file": "https://example.com/demo.jpg"}},
            {
                "type": "file",
                "data": {
                    "name": "report.pdf",
                    "file": "https://example.com/report.pdf",
                },
            },
            {
                "type": "reply",
                "data": {
                    "id": "reply-1",
                    "sender_id": "user-9",
                    "sender_nickname": "Tester",
                    "message_str": "quoted text",
                    "chain": [{"type": "text", "data": {"text": "quoted text"}}],
                },
            },
            {"type": "text", "data": {"text": "world"}},
            {"type": "mystery", "data": {"foo": "bar"}},
        ],
    }

    event = MessageEvent.from_payload(payload)

    assert event.get_platform_id() == "demo-main"
    assert event.get_session_id() == "demo:group:room-7"
    assert event.unified_msg_origin == "demo:group:room-7"
    assert event.target is not None
    assert event.target.to_payload() == {
        "conversation_id": "demo:group:room-7",
        "platform": "demo",
        "raw": payload,
    }
    assert event.is_group_chat() is True
    assert event.is_private_chat() is False
    assert event.is_admin() is True
    assert event.has_component(Image) is True
    assert event.has_component(Record) is False
    assert [component.text for component in event.get_components(Plain)] == [
        "hello",
        "world",
    ]
    assert len(event.get_images()) == 1
    assert event.get_images()[0].file == "https://example.com/demo.jpg"
    assert len(event.get_files()) == 1
    assert event.get_files()[0].name == "report.pdf"
    replies = event.get_components(Reply)
    assert len(replies) == 1
    assert replies[0].id == "reply-1"
    assert replies[0].sender_id == "user-9"
    assert replies[0].message_str == "quoted text"
    assert len(replies[0].chain) == 1
    assert isinstance(replies[0].chain[0], Plain)
    assert event.extract_plain_text() == "hello world"
    assert event.get_at_users() == ["user-2"]
    assert isinstance(event.get_messages()[-1], UnknownComponent)
    assert event.plain_result("ready").text == "ready"
    assert (
        event.image_result("https://example.com/demo.jpg").chain.components[0].type
        == "image"
    )
    assert (
        event.chain_result([Plain("sdk", convert=False)]).chain.get_plain_text()
        == "sdk"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_event_reply_methods_and_stop_flags() -> None:
    peer = _BehaviorPeer()
    ctx = Context(peer=peer, plugin_id="sdk-docs")
    session_ref = SessionRef(conversation_id="demo:private:user-1", platform="demo")
    event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": session_ref.session,
            "platform": "demo",
            "platform_id": "demo-main",
            "message_type": "private",
            "target": session_ref.to_payload(),
        },
        context=ctx,
    )

    assert event.is_stopped() is False
    event.stop_event()
    assert event.is_stopped() is True
    event.continue_event()
    assert event.is_stopped() is False

    await event.reply("pong")
    await event.reply_image("https://example.com/demo.jpg")
    await event.reply_chain(MessageChain([Plain("hello", convert=False), At("user-2")]))

    assert [item["capability"] for item in peer.sent_messages] == [
        "platform.send",
        "platform.send_image",
        "platform.send_chain",
    ]
    assert [item["session"] for item in peer.sent_messages] == [
        "demo:private:user-1",
        "demo:private:user-1",
        "demo:private:user-1",
    ]
    assert [item["target"]["conversation_id"] for item in peer.sent_messages] == [  # type: ignore[index]
        "demo:private:user-1",
        "demo:private:user-1",
        "demo:private:user-1",
    ]
    assert [item["target"]["platform"] for item in peer.sent_messages] == [  # type: ignore[index]
        "demo",
        "demo",
        "demo",
    ]
    assert peer.sent_messages[0]["text"] == "pong"
    assert peer.sent_messages[1]["image_url"] == "https://example.com/demo.jpg"
    assert peer.sent_messages[2]["chain"] == [
        {"type": "text", "data": {"text": "hello"}},
        {"type": "at", "data": {"qq": "user-2"}},
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_chain_and_builder_preserve_component_order() -> None:
    chain = MessageChain()
    returned = chain.append(Plain("Hello", convert=False)).append(At("user-2"))
    assert returned is chain
    assert chain.extend([Plain("World", convert=False)]) is chain
    assert len(chain) == 3
    assert chain.to_payload() == [
        {"type": "text", "data": {"text": "Hello"}},
        {"type": "at", "data": {"qq": "user-2"}},
        {"type": "text", "data": {"text": "World"}},
    ]
    assert await chain.to_payload_async() == chain.to_payload()
    assert chain.get_plain_text() == "Hello World"
    assert chain.plain_text(with_other_comps_mark=True) == "Hello [At] World"

    built = (
        MessageBuilder()
        .text("hello")
        .at("user-2")
        .at_all()
        .image("https://example.com/image.jpg")
        .record("https://example.com/audio.mp3")
        .video("https://example.com/video.mp4")
        .file("doc.bin", url="https://example.com/doc.bin")
        .reply(id="reply-1", chain=[Plain("quoted", convert=False)])
        .append(Forward(id="forward-1"))
        .extend([Poke(qq="user-3")])
        .build()
    )
    built_payload = await built.to_payload_async()

    assert [item["type"] for item in built_payload] == [
        "text",
        "at",
        "at",
        "image",
        "record",
        "video",
        "file",
        "reply",
        "forward",
        "poke",
    ]
    assert built_payload[2]["data"]["qq"] == "all"
    assert built_payload[6]["data"]["file"] == "https://example.com/doc.bin"
    assert built_payload[7]["data"]["chain"] == [
        {"type": "text", "data": {"text": "quoted"}}
    ]
    assert built_payload[8]["data"]["id"] == "forward-1"
    assert built_payload[9]["data"] == {"type": "126", "id": "user-3"}


@pytest.mark.unit
def test_special_component_roundtrip_preserves_public_payload_shape() -> None:
    payloads = [
        component_to_payload_sync(AtAll()),
        component_to_payload_sync(Forward(id="forward-1")),
        component_to_payload_sync(Poke(qq="user-3")),
        component_to_payload_sync(
            Reply(
                id="reply-1",
                sender_id="user-9",
                sender_nickname="Tester",
                message_str="quoted text",
                chain=[Plain("quoted text", convert=False)],
            )
        ),
        {"type": "unknown-segment", "data": {"foo": "bar"}},
    ]

    components = payloads_to_components(payloads)

    assert isinstance(components[0], AtAll)
    assert isinstance(components[1], Forward)
    assert components[1].id == "forward-1"
    assert isinstance(components[2], Poke)
    assert components[2].target_id() == "user-3"
    assert components[2].toDict() == {
        "type": "poke",
        "data": {"type": "126", "id": "user-3"},
    }
    assert isinstance(components[3], Reply)
    assert components[3].id == "reply-1"
    assert components[3].sender_nickname == "Tester"
    assert components[3].toDict() == payloads[3]
    assert isinstance(components[4], UnknownComponent)
    assert components[4].toDict() == payloads[4]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_media_components_and_helper_use_real_http_and_filesystem_behavior(
    tmp_path: Path,
    media_server,
) -> None:
    base_url, assets = media_server
    local_image = tmp_path / "local-image.jpg"
    local_image.write_bytes(assets["image.jpg"])
    local_record = tmp_path / "local-audio.mp3"
    local_record.write_bytes(assets["audio.mp3"])
    local_video = tmp_path / "local-video.mp4"
    local_video.write_bytes(assets["video.mp4"])
    local_doc = tmp_path / "local-doc.bin"
    local_doc.write_bytes(assets["doc.bin"])

    temp_paths: list[Path] = []
    try:
        assert await Image.fromFileSystem(
            str(local_image)
        ).convert_to_file_path() == str(local_image.resolve())
        assert await Record.fromFileSystem(
            str(local_record)
        ).convert_to_file_path() == str(local_record.resolve())
        assert await Video.fromFileSystem(
            str(local_video)
        ).convert_to_file_path() == str(local_video.resolve())

        image_base64 = Image.fromBase64(base64.b64encode(assets["image.jpg"]).decode())
        base64_path = Path(await image_base64.convert_to_file_path())
        temp_paths.append(base64_path)
        assert base64_path.read_bytes() == assets["image.jpg"]

        image_path = Path(
            await Image.fromURL(f"{base_url}/image.jpg").convert_to_file_path()
        )
        record_path = Path(
            await Record.fromURL(f"{base_url}/audio.mp3").convert_to_file_path()
        )
        video_path = Path(
            await Video.fromURL(f"{base_url}/video.mp4").convert_to_file_path()
        )
        file_component = File(name="doc.bin", url=f"{base_url}/doc.bin")
        file_path = Path(await file_component.get_file())
        temp_paths.extend([image_path, record_path, video_path, file_path])

        assert image_path.read_bytes() == assets["image.jpg"]
        assert record_path.read_bytes() == assets["audio.mp3"]
        assert video_path.read_bytes() == assets["video.mp4"]
        assert file_path.read_bytes() == assets["doc.bin"]
        assert Path(file_component.file) == file_path
        assert await File(name="local-doc.bin", file=str(local_doc)).get_file() == str(
            local_doc.resolve()
        )

        image_component = await MediaHelper.from_url(f"{base_url}/image.jpg")
        record_component = await MediaHelper.from_url(f"{base_url}/audio.mp3")
        video_component = await MediaHelper.from_url(f"{base_url}/video.mp4")
        generic_component = await MediaHelper.from_url(f"{base_url}/doc.bin")
        forced_image = await MediaHelper.from_url(f"{base_url}/doc.bin", kind="image")

        assert isinstance(image_component, Image)
        assert isinstance(record_component, Record)
        assert isinstance(video_component, Video)
        assert isinstance(generic_component, File)
        assert generic_component.name == "doc.bin"
        assert isinstance(forced_image, Image)

        download_dir = tmp_path / "downloads"
        downloaded_path = await MediaHelper.download(
            f"{base_url}/doc.bin", download_dir
        )
        assert downloaded_path == (download_dir / "doc.bin").resolve()
        assert downloaded_path.read_bytes() == assets["doc.bin"]
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)
