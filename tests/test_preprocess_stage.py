import base64
from io import BytesIO
from types import SimpleNamespace

import pytest

from astrbot.core.message.components import Image, Plain, Reply
from astrbot.core.pipeline.preprocess_stage import stage as preprocess_stage
from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage
from astrbot.core.utils import media_utils


class FakeEvent:
    def __init__(self, message):
        self.message_obj = SimpleNamespace(message=message, message_str="")
        self.message_str = ""
        self.is_at_or_wake_command = False
        self.temporary_local_files: list[str] = []

    def get_platform_name(self):
        return "test"

    def get_messages(self):
        return self.message_obj.message

    def track_temporary_local_file(self, path: str) -> None:
        if path not in self.temporary_local_files:
            self.temporary_local_files.append(path)


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
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {}
    stage.stt_settings = {"enable": False}

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
    stage = PreProcessStage()
    stage.config = {}
    stage.platform_settings = {"path_mapping": [f"{source_root}:{target_root}"]}
    stage.stt_settings = {"enable": False}

    await stage.process(event)

    image = event.get_messages()[0]
    assert isinstance(image, Image)
    assert image.file == image.path == image.url == str(target_image)
