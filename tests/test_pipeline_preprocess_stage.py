"""Preprocessing retains ownership of temporary media on validation failure."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.message.components import Image
from astrbot.core.pipeline.preprocess_stage import stage as preprocess


def test_only_temporary_directory_files_are_tracked(monkeypatch, tmp_path):
    temporary = tmp_path / "temp"
    temporary.mkdir()
    owned, external = temporary / "image.png", tmp_path / "retained.png"
    owned.write_bytes(b"owned")
    external.write_bytes(b"retained")
    monkeypatch.setattr(preprocess, "get_astrbot_temp_path", lambda: str(temporary))
    event = SimpleNamespace(track_temporary_local_file=Mock())
    preprocess.PreProcessStage._track_temp_media(event, str(owned))
    preprocess.PreProcessStage._track_temp_media(event, str(external))
    event.track_temporary_local_file.assert_called_once_with(str(owned.resolve()))
    assert external.read_bytes() == b"retained"


@pytest.mark.parametrize(
    "reference",
    [
        None,
        "",
        "https://example.invalid/image.png",
        "data:image/png;base64,a",
        "base64://a",
    ],
)
def test_remote_and_encoded_images_are_not_existing_local_files(reference):
    assert preprocess.PreProcessStage._is_existing_local_image_ref(reference) is False


def test_existing_local_images_are_recognized(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"image")
    assert preprocess.PreProcessStage._is_existing_local_image_ref(str(image)) is True
    assert (
        preprocess.PreProcessStage._is_existing_local_image_ref(image.as_uri()) is True
    )
    assert (
        preprocess.PreProcessStage._is_existing_local_image_ref(
            str(tmp_path / "missing")
        )
        is False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False])
async def test_materialized_image_is_retained_or_left_for_event_cleanup(
    monkeypatch, tmp_path, valid
):
    image_path = tmp_path / "image.bin"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(preprocess, "get_astrbot_temp_path", lambda: str(tmp_path))
    convert = AsyncMock(return_value=str(image_path))
    detect = AsyncMock(return_value="image/png" if valid else None)
    monkeypatch.setattr(Image, "convert_to_file_path", convert)
    monkeypatch.setattr(preprocess, "detect_image_mime_type_async", detect)
    event = SimpleNamespace(
        track_temporary_local_file=Mock(), untrack_temporary_local_file=Mock()
    )
    component = Image(file="https://example.invalid/image.png")
    stage = preprocess.PreProcessStage()
    if valid:
        await stage._normalize_image_component(event, component)
        assert component.file == component.path == component.url == str(image_path)
        event.untrack_temporary_local_file.assert_called_once_with(str(image_path))
    else:
        with pytest.raises(ValueError, match="could not be identified"):
            await stage._normalize_image_component(event, component)
        event.untrack_temporary_local_file.assert_not_called()
        assert component.file == "https://example.invalid/image.png"
    event.track_temporary_local_file.assert_called_once_with(str(image_path.resolve()))
    convert.assert_awaited_once()
    detect.assert_awaited_once_with(str(image_path), default_mime_type=None)
