import asyncio
import base64
from io import BytesIO
from types import SimpleNamespace

import pytest

from astrbot.core.message.components import Image, Plain, Record, Reply
from astrbot.core.pipeline.preprocess_stage import stage as preprocess_stage
from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage
from astrbot.core.utils import media_utils


class FakeEvent:
    def __init__(self, message):
        self.message_obj = SimpleNamespace(message=message, message_str="")
        self.message_str = ""
        self.is_at_or_wake_command = False
        self.unified_msg_origin = "test:session"
        self.temporary_local_files: list[str] = []
        self.reactions: list[str] = []

    def get_platform_name(self):
        return "test"

    def get_messages(self):
        return self.message_obj.message

    def track_temporary_local_file(self, path: str) -> None:
        if path not in self.temporary_local_files:
            self.temporary_local_files.append(path)

    async def react(self, emoji: str) -> None:
        self.reactions.append(emoji)


def _stage(**settings) -> PreProcessStage:
    stage = PreProcessStage()
    stage.config = settings
    stage.platform_settings = settings.get("platform_settings", {})
    stage.stt_settings = settings.get("provider_stt_settings", {"enable": False})
    stage.ctx = SimpleNamespace(
        execution_context=SimpleNamespace(get_using_stt_provider=lambda _umo: None)
    )
    return stage


@pytest.mark.asyncio
async def test_preprocess_preserves_image_formats_and_tracks_temp_files(
    tmp_path, monkeypatch
):
    from PIL import Image as PILImage

    temp_dir = tmp_path / "temp"
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(temp_dir))
    monkeypatch.setattr(
        preprocess_stage,
        "get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    main_image_buffer = BytesIO()
    PILImage.new("RGBA", (2, 2), (255, 0, 0, 128)).save(
        main_image_buffer,
        format="PNG",
    )
    main_image_ref = (
        "data:image/png;base64,"
        + base64.b64encode(main_image_buffer.getvalue()).decode()
    )

    reply_image_buffer = BytesIO()
    PILImage.new("RGB", (2, 2), (0, 255, 0)).save(
        reply_image_buffer,
        format="GIF",
        save_all=True,
        append_images=[PILImage.new("RGB", (2, 2), (0, 0, 255))],
        duration=100,
        loop=0,
    )
    reply_image_ref = (
        "data:image/gif;base64,"
        + base64.b64encode(reply_image_buffer.getvalue()).decode()
    )

    reply_image = Image(file=reply_image_ref)
    event = FakeEvent(
        [
            Image(file=main_image_ref),
            Reply(
                id="reply-1",
                chain=[Plain(text="quoted"), reply_image],
                sender_nickname="Alice",
                message_str="quoted",
            ),
        ]
    )
    stage = _stage()

    await stage.process(event)

    main_image = event.get_messages()[0]
    assert isinstance(main_image, Image)
    assert main_image.file == main_image.path == main_image.url
    assert main_image.file.endswith(".png")
    assert main_image.file in event.temporary_local_files
    with PILImage.open(main_image.file) as processed_img:
        assert processed_img.format == "PNG"
        assert processed_img.getpixel((0, 0))[3] == 128

    assert reply_image.file == reply_image.path == reply_image.url
    assert reply_image.file.endswith(".gif")
    assert reply_image.file in event.temporary_local_files
    with PILImage.open(reply_image.file) as processed_img:
        assert processed_img.format == "GIF"
        assert processed_img.is_animated
        assert processed_img.n_frames == 2


@pytest.mark.asyncio
async def test_preprocess_path_mapping_accepts_file_uri(tmp_path):
    from PIL import Image as PILImage

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()
    source_image = source_root / "photo.jpg"
    target_image = target_root / "photo.jpg"
    PILImage.new("RGB", (2, 2), (255, 0, 0)).save(target_image)
    event = FakeEvent([Image(file="", url=source_image.as_uri())])
    stage = _stage(platform_settings={"path_mapping": [f"{source_root}:{target_root}"]})

    await stage.process(event)

    image = event.get_messages()[0]
    assert isinstance(image, Image)
    assert image.file == image.path == image.url == str(target_image)


@pytest.mark.asyncio
async def test_pre_ack_emoji_only_reacts_for_awakened_supported_platform(monkeypatch):
    event = FakeEvent([Plain("hello")])
    event.is_at_or_wake_command = True
    monkeypatch.setattr(event, "get_platform_name", lambda: "telegram")
    stage = _stage(
        platform_specific={
            "telegram": {"pre_ack_emoji": {"enable": True, "emojis": ["👍"]}}
        }
    )

    await stage.process(event)

    assert event.reactions == ["👍"]


@pytest.mark.asyncio
async def test_pre_ack_emoji_failure_does_not_interrupt_preprocessing(
    caplog, monkeypatch
):
    event = FakeEvent([Plain("hello")])
    event.is_at_or_wake_command = True
    monkeypatch.setattr(event, "get_platform_name", lambda: "discord")

    async def fail_react(_: str) -> None:
        raise RuntimeError("reaction unavailable")

    monkeypatch.setattr(event, "react", fail_react)
    stage = _stage(
        platform_specific={
            "discord": {"pre_ack_emoji": {"enable": True, "emojis": ["👍"]}}
        }
    )

    await stage.process(event)

    assert "预回应表情发送失败" in caplog.text


def test_path_mapping_handles_windows_posix_invalid_entries_and_first_prefix_only(
    caplog,
):
    windows_image = Image(file="", url=r"C:\source\C:\source\photo.jpg")
    posix_record = Record(file="", url="/source/source/voice.wav")
    stage = _stage(
        platform_settings={
            "path_mapping": [
                "invalid",
                r"C:\source:D:\target",
                "/source:/target",
            ]
        }
    )

    stage._apply_path_mappings([windows_image, posix_record])

    assert windows_image.url == r"D:\target\C:\source\photo.jpg"
    assert posix_record.url == "/target/source/voice.wav"
    assert "无效的路径映射配置" in caplog.text


@pytest.mark.asyncio
async def test_record_normalization_tracks_top_level_and_reply_temp_files(
    tmp_path, monkeypatch
):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    top_source = temp_dir / "top-source.wav"
    reply_source = temp_dir / "reply-source.wav"
    top_target = temp_dir / "top.wav"
    reply_target = temp_dir / "reply.wav"
    for path in (top_source, reply_source, top_target, reply_target):
        path.touch()
    monkeypatch.setattr(
        preprocess_stage, "get_astrbot_temp_path", lambda: str(temp_dir)
    )

    top = Record(file="top")
    reply_record = Record(file="reply")

    async def record_path(self):
        return str(top_source if self is top else reply_source)

    async def wav(path: str) -> str:
        return str(top_target if path == str(top_source) else reply_target)

    monkeypatch.setattr(Record, "convert_to_file_path", record_path)
    monkeypatch.setattr(preprocess_stage, "ensure_wav", wav)
    event = FakeEvent([top, Reply(id="r", chain=[reply_record])])

    await _stage().process(event)

    assert top.file == top.path == str(top_target)
    assert reply_record.file == reply_record.path == str(reply_target)
    assert set(event.temporary_local_files) == {
        str(path.resolve())
        for path in (top_source, reply_source, top_target, reply_target)
    }


@pytest.mark.asyncio
async def test_image_normalization_failure_redacts_original_media_reference(
    caplog, monkeypatch
):
    image = Image(file="", url="https://secret.example/private/token.jpg")

    async def fail_conversion(self) -> str:
        raise RuntimeError("download failed")

    monkeypatch.setattr(Image, "convert_to_file_path", fail_conversion)

    await _stage().process(FakeEvent([image]))

    assert "Image processing failed" in caplog.text
    assert "https://secret.example/private/token.jpg" not in caplog.text


@pytest.mark.asyncio
async def test_stt_replaces_top_level_and_reply_records_and_updates_message_strings(
    monkeypatch,
):
    top = Record(file="top")
    reply_record = Record(file="reply")
    event = FakeEvent([top, Reply(id="r", chain=[reply_record])])
    calls = 0

    async def record_path(self) -> str:
        return f"/{self.file}.wav"

    class Provider:
        async def get_text(self, *, audio_url: str) -> str:
            nonlocal calls
            calls += 1
            return "top text" if calls == 1 else "reply text"

    monkeypatch.setattr(Record, "convert_to_file_path", record_path)
    stage = _stage(provider_stt_settings={"enable": True})
    stage.ctx.execution_context.get_using_stt_provider = lambda _umo: Provider()

    await stage.process(event)

    assert isinstance(event.get_messages()[0], Plain)
    assert isinstance(event.get_messages()[1].chain[0], Plain)
    assert event.message_str == event.message_obj.message_str == "top textreply text"


@pytest.mark.asyncio
async def test_stt_retries_missing_file_and_keeps_message_on_non_retryable_error(
    monkeypatch,
):
    record = Record(file="voice")
    event = FakeEvent([record])
    calls = 0

    async def record_path(self) -> str:
        return "/voice.wav"

    class Provider:
        async def get_text(self, *, audio_url: str) -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise FileNotFoundError
            raise RuntimeError("provider failure")

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(Record, "convert_to_file_path", record_path)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    stage = _stage(provider_stt_settings={"enable": True})
    stage.ctx.execution_context.get_using_stt_provider = lambda _umo: Provider()

    await stage.process(event)

    assert calls == 3
    assert event.get_messages()[0] is record


@pytest.mark.asyncio
async def test_stt_without_provider_keeps_current_message(monkeypatch):
    record = Record(file="voice")
    event = FakeEvent([record])
    stage = _stage(provider_stt_settings={"enable": True})
    stage.ctx.execution_context.get_using_stt_provider = lambda _umo: None

    await stage.process(event)

    assert event.get_messages()[0] is record
