import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.message.components import (
    File,
    Image,
    Node,
    Nodes,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.pipeline.preprocess_stage import stage as preprocess_stage
from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils import media_utils, platform_files


class FakeEvent:
    def __init__(self, message):
        self.message_obj = SimpleNamespace(message=message, message_str="")
        self.message_str = ""
        self.unified_msg_origin = "test:GroupMessage:group-user"
        self.is_at_or_wake_command = False
        self.temporary_local_files: list[str] = []
        self._temporary_local_files = self.temporary_local_files
        self._extras = {}

    def get_platform_name(self):
        return "test"

    def get_messages(self):
        return self.message_obj.message

    track_temporary_local_file = AstrMessageEvent.track_temporary_local_file
    untrack_temporary_local_file = AstrMessageEvent.untrack_temporary_local_file
    get_extra = AstrMessageEvent.get_extra
    set_extra = AstrMessageEvent.set_extra


@pytest.fixture(autouse=True)
def isolate_attachment_storage(tmp_path, monkeypatch):
    """Keep retained attachments and staging files inside each test directory."""
    monkeypatch.setattr(
        preprocess_stage, "get_astrbot_temp_path", lambda: str(tmp_path)
    )
    monkeypatch.setattr(
        platform_files,
        "get_astrbot_temp_path",
        lambda: preprocess_stage.get_astrbot_temp_path(),
    )


@pytest.mark.asyncio
async def test_preprocess_preserves_image_formats_without_tracking_temp_files(
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
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {}
    stage.stt_settings = {"enable": False}

    await stage.process(event)

    main_image = event.get_messages()[0]
    assert isinstance(main_image, Image)
    assert main_image.file == main_image.path == main_image.url
    assert main_image.file.endswith(".png")
    assert main_image.file not in event.temporary_local_files
    with PILImage.open(main_image.file) as processed_img:
        assert processed_img.format == "PNG"
        assert processed_img.getpixel((0, 0))[3] == 128

    assert reply_image.file == reply_image.path == reply_image.url
    assert reply_image.file.endswith(".gif")
    assert reply_image.file not in event.temporary_local_files
    with PILImage.open(reply_image.file) as processed_img:
        assert processed_img.format == "GIF"
        assert processed_img.is_animated
        assert processed_img.n_frames == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("quoted", [False, True])
@pytest.mark.parametrize(
    "source_kind", ["png", "jpeg", "gif", "webp", "bmp", "invalid"]
)
@pytest.mark.parametrize("pretracked", [False, True])
async def test_preprocess_image_cleanup_preserves_usable_file(
    tmp_path, monkeypatch, quoted, source_kind, pretracked
):
    from pathlib import Path

    from PIL import Image as PILImage

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        preprocess_stage, "get_astrbot_temp_path", lambda: str(tmp_path)
    )
    source_path = tmp_path / f"source.{source_kind}"
    if source_kind == "invalid":
        source_path.write_bytes(b"not an image")
    else:
        PILImage.new("RGB", (2, 2), (255, 0, 0)).save(source_path)

    image = Image.fromFileSystem(str(source_path))
    event = FakeEvent([Reply(id="reply-1", chain=[image])] if quoted else [image])
    original = source_path.read_bytes()
    if pretracked:
        event.track_temporary_local_file(str(source_path))
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {}
    stage.stt_settings = {"enable": False}

    await stage.process(event)

    assert image.file == image.path == image.url
    retained = Path(image.file)
    assert retained.parent == platform_files.platform_files_root(
        event.unified_msg_origin
    )
    assert retained.read_bytes() == original
    assert source_path.read_bytes() == original

    # Exercise event cleanup to verify that the usable image survives.
    AstrMessageEvent.cleanup_temporary_local_files(
        SimpleNamespace(_temporary_local_files=event.temporary_local_files)
    )
    assert retained.read_bytes() == original
    assert source_path.exists() is (not pretracked)
    assert Path(await image.convert_to_file_path()).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("quoted", [False, True])
async def test_preprocess_image_cleanup_removes_invalid_materialized_file(
    tmp_path, monkeypatch, quoted
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        preprocess_stage, "get_astrbot_temp_path", lambda: str(tmp_path)
    )
    reference = "data:image/png;base64," + base64.b64encode(b"not an image").decode()
    image = Image(file=reference)
    event = FakeEvent([Reply(id="reply-1", chain=[image])] if quoted else [image])
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {}
    stage.stt_settings = {"enable": False}

    await stage.process(event)

    materialized = list(tmp_path.glob("media_image_*"))
    assert materialized
    assert image.file == reference
    assert len(event.temporary_local_files) == 1
    AstrMessageEvent.cleanup_temporary_local_files(
        SimpleNamespace(_temporary_local_files=event.temporary_local_files)
    )
    assert not [path for path in materialized if path.exists()]


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
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {"path_mapping": [f"{source_root}:{target_root}"]}
    stage.stt_settings = {"enable": False}

    await stage.process(event)

    image = event.get_messages()[0]
    assert isinstance(image, Image)
    assert image.file == image.path == image.url
    assert Path(image.file).parent == platform_files.platform_files_root(
        event.unified_msg_origin
    )
    assert Path(image.file).read_bytes() == target_image.read_bytes()


@pytest.mark.asyncio
async def test_preprocess_path_mapping_accepts_windows_source_to_posix_target(
    tmp_path,
):
    from PIL import Image as PILImage

    target_root = tmp_path / "target"
    target_root.mkdir()
    target_image = target_root / "photo.jpg"
    PILImage.new("RGB", (2, 2), (255, 0, 0)).save(target_image)

    source_prefix = r"C:\remote\media"
    event = FakeEvent([Image(file="", url=f"{source_prefix}/photo.jpg")])
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {"path_mapping": [f"{source_prefix}:{target_root}"]}
    stage.stt_settings = {"enable": False}

    await stage.process(event)

    image = event.get_messages()[0]
    assert isinstance(image, Image)
    assert image.file == image.path == image.url
    assert Path(image.file).parent == platform_files.platform_files_root(
        event.unified_msg_origin
    )
    assert Path(image.file).read_bytes() == target_image.read_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "image", "record", "video"])
@pytest.mark.parametrize("nested", [False, True])
async def test_incoming_attachments_use_final_session_storage(
    tmp_path, monkeypatch, kind, nested
):
    """Retain all attachment types, including forwarded quotes, through cleanup."""
    from PIL import Image as PILImage

    from astrbot.core.message import components

    source = tmp_path / "input.bin"
    source.write_bytes(b"platform attachment")
    if kind == "file":

        async def download(url, path):
            Path(path).write_bytes(source.read_bytes())

        monkeypatch.setattr(components, "download_file", download)
        monkeypatch.setattr(components, "get_astrbot_temp_path", lambda: str(tmp_path))
        component = File(name="report.txt", url="https://example.test/file")
    elif kind == "image":
        source = tmp_path / "input.png"
        PILImage.new("RGB", (2, 2)).save(source)
        component = Image.fromFileSystem(str(source))
    elif kind == "record":
        import wave

        source = tmp_path / "input.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\0\0" * 80)
        component = Record.fromFileSystem(str(source))
    else:
        component = Video.fromFileSystem(str(source))
    chain = [component]
    if nested:
        chain = [Reply(id="quoted", chain=[Nodes(nodes=[Node(content=chain)])])]
    event = FakeEvent(chain)
    event.unified_msg_origin = "platform-instance:GroupMessage:group-isolated-user"
    event.track_temporary_local_file(str(source))
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {}
    stage.stt_settings = {"enable": False}

    await stage.process(event)

    retained = Path(component.file_ if isinstance(component, File) else component.path)
    assert retained.parent == platform_files.platform_files_root(
        event.unified_msg_origin
    )
    assert retained.read_bytes() == source.read_bytes()
    if isinstance(component, File):
        assert component.name == "report.txt"
        assert await component.get_file() == str(retained)
    else:
        assert component.file == component.path == component.url == str(retained)
    AstrMessageEvent.cleanup_temporary_local_files(event)
    assert retained.is_file()
    assert not source.exists()

    # Reprocessing a retained message must not duplicate or delete the attachment.
    await stage.process(event)
    assert len(list(retained.parent.iterdir())) == 1
    AstrMessageEvent.cleanup_temporary_local_files(event)
    assert retained.is_file()


@pytest.mark.asyncio
async def test_retained_files_are_distinct_across_messages_and_sessions(tmp_path):
    """Equal filenames cannot overwrite another message's or session's content."""
    source = tmp_path / "report.txt"
    source.write_text("first", encoding="utf-8")
    first = await platform_files.retain_platform_file(str(source), "test:friend:one")
    source.write_text("second", encoding="utf-8")
    second = await platform_files.retain_platform_file(str(source), "test:friend:one")
    other = await platform_files.retain_platform_file(str(source), "test:friend:two")
    assert len({first, second, other}) == 3
    assert Path(first).read_text() == "first"
    assert Path(second).read_text() == Path(other).read_text() == "second"
    assert Path(first).parent != Path(other).parent


@pytest.mark.asyncio
async def test_cancelled_attachment_copy_cleans_up_after_worker_finishes(
    tmp_path, monkeypatch
):
    """Cancellation cannot leave a worker writing an orphaned attachment afterward."""
    import asyncio
    import threading

    source = tmp_path / "input.txt"
    source.write_text("content", encoding="utf-8")
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original_copy = platform_files.shutil.copyfile

    def delayed_copy(src, dst):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        return original_copy(src, dst)

    monkeypatch.setattr(platform_files.shutil, "copyfile", delayed_copy)
    task = asyncio.create_task(
        platform_files.retain_platform_file(str(source), "test:friend:one")
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list(platform_files.platform_files_root("test:friend:one").iterdir()) == []
    assert source.read_text() == "content"


@pytest.mark.asyncio
async def test_duplicate_encoded_images_share_retained_file(tmp_path, monkeypatch):
    """An image repeated in a quote shares its retained source and is not decoded twice."""
    from PIL import Image as PILImage

    buffer = BytesIO()
    PILImage.new("RGB", (2, 2)).save(buffer, format="PNG")
    ref = "base64://" + base64.b64encode(buffer.getvalue()).decode()
    original = Image(file=ref)
    quoted = Image(file=ref)
    event = FakeEvent([original, Reply(id="quote", chain=[quoted])])
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {}
    stage.stt_settings = {"enable": False}
    await stage.process(event)
    assert original.path == quoted.path
    root = platform_files.platform_files_root(event.unified_msg_origin)
    assert list(root.iterdir()) == [Path(original.path)]
    AstrMessageEvent.cleanup_temporary_local_files(event)
    assert Path(original.path).read_bytes() == buffer.getvalue()
