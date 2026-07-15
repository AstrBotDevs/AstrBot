import base64
import math
import os
import struct
import sys
import wave
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import pytest

import astrbot.core.utils.media_utils as media_utils
from astrbot.core.file_token_service import FileTokenService
from astrbot.core.message.components import File, Image, Record, Video
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.path_util import path_Mapping
from astrbot.core.utils.tencent_record_helper import wav_to_tencent_silk


@pytest.mark.asyncio
async def test_resolve_audio_ref_to_base64_data_decodes_data_uri(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
    audio_ref = f"data:audio/wav;base64,{base64.b64encode(audio_bytes).decode()}"

    resolved = await media_utils.resolve_media_ref_to_base64_data(
        audio_ref,
        media_type="audio",
    )

    assert resolved is not None
    assert resolved.base64_data == base64.b64encode(audio_bytes).decode()
    assert resolved.mime_type == "audio/wav"
    assert resolved.format == "wav"
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_media_resolver_context_cleans_materialized_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
    audio_ref = f"data:audio/wav;base64,{base64.b64encode(audio_bytes).decode()}"

    async with media_utils.MediaResolver(
        audio_ref,
        media_type="audio",
    ).as_path(target_format="wav") as resolved:
        resolved_path = resolved.path
        assert resolved_path.exists()
        assert resolved.format == "wav"
        assert resolved.read_bytes() == audio_bytes

    assert not resolved_path.exists()
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_media_resolver_to_path_detaches_for_component_lifetimes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    image_ref = "base64://abcd"

    image_path = await media_utils.MediaResolver(
        image_ref,
        media_type="image",
    ).to_path()

    try:
        assert (tmp_path / Path(image_path).name).exists()
        assert Path(image_path).read_bytes() == base64.b64decode("abcd")
    finally:
        Path(image_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_image_from_base64_uses_detected_image_suffix(tmp_path, monkeypatch):
    from PIL import Image as PILImage

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    image_buffer = BytesIO()
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 128)).save(image_buffer, format="PNG")
    image_base64 = base64.b64encode(image_buffer.getvalue()).decode()

    image_path = await Image.fromBase64(image_base64).convert_to_file_path()

    try:
        assert Path(image_path).suffix == ".png"
        with PILImage.open(image_path) as resolved_img:
            assert resolved_img.format == "PNG"
    finally:
        Path(image_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_http_image_without_suffix_uses_detected_image_suffix(
    tmp_path,
    monkeypatch,
):
    from PIL import Image as PILImage

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    image_buffer = BytesIO()
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 128)).save(image_buffer, format="PNG")

    async def fake_download_file(_url: str, target_path: str) -> None:
        Path(target_path).write_bytes(image_buffer.getvalue())

    monkeypatch.setattr(media_utils, "download_file", fake_download_file)

    image_path = await media_utils.MediaResolver(
        "https://example.com/image?id=123",
        media_type="image",
    ).to_path()

    try:
        assert Path(image_path).suffix == ".png"
        with PILImage.open(image_path) as resolved_img:
            assert resolved_img.format == "PNG"
    finally:
        Path(image_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_resolve_audio_ref_to_base64_data_decodes_base64_scheme(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
    audio_ref = f"base64://{base64.b64encode(audio_bytes).decode()}"

    resolved = await media_utils.resolve_media_ref_to_base64_data(
        audio_ref,
        media_type="audio",
    )

    assert resolved is not None
    assert resolved.base64_data == base64.b64encode(audio_bytes).decode()
    assert resolved.mime_type == "audio/wav"
    assert resolved.format == "wav"
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_resolve_audio_ref_to_base64_data_ignores_internal_whitespace(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
    audio_base64 = base64.b64encode(audio_bytes).decode().rstrip("=")
    audio_ref = f"base64://{audio_base64[:8]}\n {audio_base64[8:]}"

    resolved = await media_utils.resolve_media_ref_to_base64_data(
        audio_ref,
        media_type="audio",
    )

    assert resolved is not None
    assert resolved.base64_data == base64.b64encode(audio_bytes).decode()
    assert resolved.mime_type == "audio/wav"
    assert resolved.format == "wav"
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_record_convert_to_file_path_accepts_bare_base64(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
    audio_base64 = base64.b64encode(audio_bytes).decode()

    audio_path = await Record(file=audio_base64).convert_to_file_path()

    try:
        assert Path(audio_path).exists()
        assert Path(audio_path).read_bytes() == audio_bytes
    finally:
        Path(audio_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_resolve_image_ref_to_base64_data_detects_png(tmp_path):
    from PIL import Image as PILImage

    image_path = tmp_path / "image.png"
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_path)

    resolved = await media_utils.resolve_media_ref_to_base64_data(
        str(image_path),
        media_type="image",
    )

    assert resolved is not None
    assert resolved.mime_type == "image/png"
    assert resolved.to_data_url().startswith("data:image/png;base64,")


def test_detect_image_mime_type_accepts_path(tmp_path):
    from PIL import Image as PILImage

    image_path = tmp_path / "image.png"
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_path)

    assert (
        media_utils.detect_image_mime_type(image_path, default_mime_type=None)
        == "image/png"
    )


@pytest.mark.asyncio
async def test_resolve_image_ref_to_base64_data_decodes_data_uri(tmp_path, monkeypatch):
    from PIL import Image as PILImage

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    image_buffer = BytesIO()
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_buffer, format="PNG")
    image_base64 = base64.b64encode(image_buffer.getvalue()).decode()
    image_ref = f"data:image/png;base64,{image_base64}"

    resolved = await media_utils.resolve_media_ref_to_base64_data(
        image_ref,
        media_type="image",
    )

    assert resolved is not None
    assert resolved.base64_data == image_base64
    assert resolved.mime_type == "image/png"
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_ensure_jpeg_converts_png_to_temp_jpg(tmp_path, monkeypatch):
    from PIL import Image as PILImage

    temp_dir = tmp_path / "temp"
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(temp_dir))
    image_path = tmp_path / "image.png"
    PILImage.new("RGB", (2, 2), (255, 0, 0)).save(image_path)

    converted_path = Path(await media_utils.ensure_jpeg(str(image_path)))

    assert converted_path.suffix == ".jpg"
    assert converted_path.parent == temp_dir
    assert converted_path.exists()
    with PILImage.open(converted_path) as converted_img:
        assert converted_img.format == "JPEG"


@pytest.mark.asyncio
async def test_ensure_jpeg_keeps_alpha_png(tmp_path, monkeypatch):
    from PIL import Image as PILImage

    temp_dir = tmp_path / "temp"
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(temp_dir))
    image_path = tmp_path / "transparent.png"
    PILImage.new("RGBA", (2, 2), (255, 0, 0, 128)).save(image_path)

    converted_path = await media_utils.ensure_jpeg(str(image_path))

    assert converted_path == str(image_path)
    assert not temp_dir.exists()


@pytest.mark.asyncio
async def test_ensure_jpeg_keeps_animated_gif(tmp_path, monkeypatch):
    from PIL import Image as PILImage

    temp_dir = tmp_path / "temp"
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(temp_dir))
    image_path = tmp_path / "animated.gif"
    PILImage.new("RGB", (2, 2), (255, 0, 0)).save(
        image_path,
        format="GIF",
        save_all=True,
        append_images=[PILImage.new("RGB", (2, 2), (0, 0, 255))],
        duration=100,
        loop=0,
    )

    converted_path = await media_utils.ensure_jpeg(str(image_path))

    assert converted_path == str(image_path)
    assert not temp_dir.exists()


@pytest.mark.asyncio
async def test_ensure_jpeg_keeps_existing_jpg(tmp_path, monkeypatch):
    from PIL import Image as PILImage

    temp_dir = tmp_path / "temp"
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(temp_dir))
    image_path = tmp_path / "image.jpg"
    PILImage.new("RGB", (2, 2), (255, 0, 0)).save(image_path)

    converted_path = await media_utils.ensure_jpeg(str(image_path))

    assert converted_path == str(image_path)
    assert not temp_dir.exists()


@pytest.mark.asyncio
async def test_compress_image_preserves_alpha_png(tmp_path, monkeypatch):
    from PIL import Image as PILImage

    temp_dir = tmp_path / "temp"
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(temp_dir))
    image_path = tmp_path / "transparent.png"
    PILImage.new("RGBA", (8, 8), (255, 0, 0, 128)).save(image_path)

    compressed_path = Path(
        await media_utils.compress_image(str(image_path), max_size=2)
    )

    try:
        assert compressed_path != image_path
        assert compressed_path.suffix == ".png"
        assert compressed_path.parent == temp_dir
        with PILImage.open(compressed_path) as compressed_img:
            assert compressed_img.format == "PNG"
            assert compressed_img.mode == "RGBA"
            assert max(compressed_img.size) <= 2
            assert compressed_img.getpixel((0, 0))[3] == 128
    finally:
        compressed_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_compress_image_keeps_animated_gif(tmp_path, monkeypatch):
    from PIL import Image as PILImage

    temp_dir = tmp_path / "temp"
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(temp_dir))
    image_path = tmp_path / "animated.gif"
    PILImage.new("RGB", (8, 8), (255, 0, 0)).save(
        image_path,
        format="GIF",
        save_all=True,
        append_images=[PILImage.new("RGB", (8, 8), (0, 0, 255))],
        duration=100,
        loop=0,
    )

    compressed_path = await media_utils.compress_image(str(image_path), max_size=2)

    assert compressed_path == str(image_path)
    assert not list(temp_dir.iterdir())


@pytest.mark.asyncio
async def test_resolve_image_ref_to_base64_data_keeps_base64_scheme_fallback(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))

    resolved = await media_utils.resolve_media_ref_to_base64_data(
        "base64://abcd",
        media_type="image",
    )

    assert resolved is not None
    assert resolved.base64_data == "abcd"
    assert resolved.mime_type == "image/jpeg"
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_resolve_image_ref_to_base64_data_accepts_bare_base64(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))

    resolved = await media_utils.resolve_media_ref_to_base64_data(
        "abcd",
        media_type="image",
    )

    assert resolved is not None
    assert resolved.base64_data == "abcd"
    assert resolved.mime_type == "image/jpeg"
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_media_resolver_accepts_unpadded_base64_payloads(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    payload = base64.b64encode(b"abcd").decode().rstrip("=")

    image_data = await media_utils.resolve_media_ref_to_base64_data(
        f"base64://{payload}",
        media_type="image",
    )
    file_bytes = await media_utils.MediaResolver(
        f"data:application/octet-stream;base64,{payload}",
    ).to_bytes()

    assert image_data is not None
    assert image_data.base64_data == base64.b64encode(b"abcd").decode()
    assert file_bytes == b"abcd"
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_media_resolver_cleans_materialized_file_when_audio_conversion_fails(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))

    async def fail_ensure_wav(*args, **kwargs):
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(media_utils, "ensure_wav", fail_ensure_wav)

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        await media_utils.MediaResolver(
            f"base64://{base64.b64encode(b'not wav').decode()}",
            media_type="audio",
        ).to_base64_data(strict=True)

    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_media_resolver_cleans_http_target_when_download_fails(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))

    async def fail_download(url: str, target_path: str) -> None:
        Path(target_path).write_bytes(b"partial")
        raise RuntimeError("download failed")

    monkeypatch.setattr(media_utils, "download_file", fail_download)

    with pytest.raises(RuntimeError, match="download failed"):
        await media_utils.MediaResolver(
            "https://example.com/audio.wav?token=secret",
            media_type="audio",
        ).to_base64_data(strict=True)

    assert not list(tmp_path.iterdir())


def test_describe_media_ref_does_not_include_payload_or_query():
    data_ref = "data:image/png;base64," + "A" * 128
    url_ref = "https://example.com/path/image.png?token=secret"
    described_url_ref = media_utils.describe_media_ref(url_ref)

    assert "A" * 64 not in media_utils.describe_media_ref(data_ref)
    assert "token=secret" not in described_url_ref
    assert described_url_ref == "https URL host='example.com' file='image.png' len=47"


@pytest.mark.asyncio
async def test_provider_request_assemble_context_uses_media_resolver(
    tmp_path, monkeypatch
):
    from PIL import Image as PILImage

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    image_buffer = BytesIO()
    PILImage.new("RGBA", (1, 1), (255, 0, 0, 255)).save(image_buffer, format="PNG")
    image_base64 = base64.b64encode(image_buffer.getvalue()).decode()
    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
    audio_base64 = base64.b64encode(audio_bytes).decode()

    request = ProviderRequest(
        prompt="look",
        image_urls=[f"data:image/png;base64,{image_base64}"],
        audio_urls=[f"data:audio/wav;base64,{audio_base64}"],
    )

    context = await request.assemble_context()

    assert context["content"] == [
        {"type": "text", "text": "look"},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
        },
        {
            "type": "audio_url",
            "audio_url": {"url": f"data:audio/wav;base64,{audio_base64}"},
        },
    ]
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_image_and_record_components_use_media_resolver(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    image = Image.fromBase64("abcd")
    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
    record = Record.fromBase64(base64.b64encode(audio_bytes).decode())

    image_path = await image.convert_to_file_path()
    record_path = await record.convert_to_file_path()

    try:
        assert Path(image_path).read_bytes() == base64.b64decode("abcd")
        assert Path(record_path).read_bytes() == audio_bytes
        assert await image.convert_to_base64() == "abcd"
        assert (
            await record.convert_to_base64() == base64.b64encode(audio_bytes).decode()
        )
    finally:
        Path(image_path).unlink(missing_ok=True)
        Path(record_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_video_component_uses_media_resolver_for_data_uri(tmp_path, monkeypatch):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    video_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8
    video = Video(
        file=f"data:video/mp4;base64,{base64.b64encode(video_bytes).decode()}"
    )

    video_path = await video.convert_to_file_path()

    try:
        assert Path(video_path).read_bytes() == video_bytes
        assert Path(video_path).suffix == ".mp4"
    finally:
        Path(video_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_record_and_video_components_accept_generic_data_uri(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
    video_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8
    record = Record(
        file=f"data:application/octet-stream;base64,{base64.b64encode(audio_bytes).decode()}"
    )
    video = Video(
        file=f"data:application/octet-stream;base64,{base64.b64encode(video_bytes).decode()}"
    )

    record_path = await record.convert_to_file_path()
    video_path = await video.convert_to_file_path()

    try:
        assert Path(record_path).read_bytes() == audio_bytes
        assert Path(video_path).read_bytes() == video_bytes
    finally:
        Path(record_path).unlink(missing_ok=True)
        Path(video_path).unlink(missing_ok=True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("file:///tmp/a", True),
        ("file:/tmp/a", True),
        ("FILE:///tmp/a", True),
        ("/tmp/a", False),
        ("relative/a", False),
        ("C:/Users/a.jpg", False),
        (None, False),
        (Path("/tmp/a"), False),
    ],
)
def test_is_file_uri_uses_parsed_file_scheme(value, expected):
    assert media_utils.is_file_uri(value) is expected


def test_file_uri_to_path_supports_localhost_and_encoded_paths(tmp_path):
    media_path = tmp_path / "voice note.wav"
    media_path.write_bytes(b"audio")
    file_uri = f"file://localhost{quote(media_path.as_posix())}"

    assert media_utils.file_uri_to_path(file_uri) == str(media_path)


def test_file_uri_to_path_supports_standard_and_legacy_posix_file_uris(tmp_path):
    media_path = tmp_path / "voice note.wav"
    media_path.write_bytes(b"audio")

    assert media_utils.file_uri_to_path(media_path.as_uri()) == str(media_path)
    assert media_utils.file_uri_to_path(f"file:{quote(media_path.as_posix())}") == str(
        media_path
    )
    assert media_utils.file_uri_to_path(
        media_path.as_uri().replace("file:", "FILE:", 1)
    ) == str(media_path)

    if os.name != "nt":
        legacy_file_uri = f"file:///{media_path.as_posix()}"
        assert legacy_file_uri.startswith("file:////")
        assert media_utils.file_uri_to_path(legacy_file_uri) == str(media_path)


def test_file_uri_to_path_preserves_posix_root_for_container_paths():
    if os.name != "nt":
        assert media_utils.file_uri_to_path("file:///AstrBot/data/cache/image.png") == (
            "/AstrBot/data/cache/image.png"
        )


def test_from_file_system_uses_pathlib_file_uri(tmp_path):
    media_path = tmp_path / "media file.bin"
    media_path.write_bytes(b"media")
    expected_uri = media_path.resolve(strict=False).as_uri()
    expected_path = str(media_path.resolve(strict=False))

    for component in (
        Image.fromFileSystem(media_path),
        Record.fromFileSystem(media_path),
        Video.fromFileSystem(media_path),
    ):
        assert component.file == expected_uri
        assert component.path == expected_path
        if os.name != "nt":
            assert not component.file.startswith("file:////")


@pytest.mark.asyncio
async def test_video_and_file_components_accept_standard_file_uri(tmp_path):
    video_path = tmp_path / "video.mp4"
    file_path = tmp_path / "document.txt"
    video_path.write_bytes(b"video")
    file_path.write_text("document", encoding="utf-8")

    assert await Video(file=video_path.as_uri()).convert_to_file_path() == str(
        video_path
    )

    file_component = File(name="document.txt", file=file_path.as_uri())
    assert file_component.file == str(file_path)
    assert await file_component.get_file() == str(file_path)


@pytest.mark.asyncio
async def test_file_token_service_accepts_standard_file_uri(tmp_path):
    file_path = tmp_path / "document with space.txt"
    file_path.write_text("document", encoding="utf-8")
    service = FileTokenService()

    token = await service.register_file(file_path.as_uri())

    assert await service.handle_file(token) == str(file_path)


def test_path_mapping_accepts_standard_and_legacy_file_uri(tmp_path):
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()
    source_file = source_root / "image.png"
    source_file.write_bytes(b"image")
    mapping = [f"{source_root}:{target_root}"]
    expected_path = str(target_root / "image.png")

    assert path_Mapping(mapping, source_file.as_uri()) == expected_path

    if os.name != "nt":
        legacy_file_uri = f"file:///{source_file.as_posix()}"
        assert path_Mapping(mapping, legacy_file_uri) == expected_path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rate, channels",
    [
        (24000, 1),  # supported, no resample
        (44100, 1),  # unsupported rate, triggers resample
        (22050, 1),  # unsupported rate, triggers resample
        (48000, 2),  # stereo at supported rate, triggers downmix
        (44100, 2),  # stereo + unsupported rate, triggers both
    ],
    ids=["24k-mono", "44.1k-mono", "22.05k-mono", "48k-stereo", "44.1k-stereo"],
)
async def test_tencent_silk_encoding_uses_pysilk_tencent_format(
    rate, channels, tmp_path, monkeypatch
):
    """Real pysilk end-to-end across sample rates that previously failed.

    44100 Hz was the regression trigger: pysilk rejects it with
    ENC_INPUT_INVALID_NO_OF_SAMPLES. The fix resamples to 24 kHz mono via
    audioop.ratecv before encoding.
    """
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    wav_path = tmp_path / "tone.wav"
    silk_path = tmp_path / "tone.silk"
    secs = 0.2
    frames = int(rate * secs)
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for i in range(frames):
            sample = int(0.2 * 32767 * math.sin(2 * math.pi * 440 * i / rate))
            for _ in range(channels):
                wav.writeframesraw(struct.pack("<h", sample))

    duration = await wav_to_tencent_silk(str(wav_path), str(silk_path))
    silk_bytes = silk_path.read_bytes()
    async with media_utils.MediaResolver(
        str(wav_path),
        media_type="audio",
        default_suffix=".wav",
    ).as_path(target_format="tencent_silk") as resolved:
        resolved_silk_path = resolved.path
        resolved_silk_bytes = resolved_silk_path.read_bytes()
        assert resolved.format == "tencent_silk"
        assert resolved.mime_type == "audio/silk"

    assert duration == pytest.approx(secs, abs=0.05)
    assert silk_bytes.startswith(b"\x02#!SILK_V3")
    assert resolved_silk_bytes.startswith(b"\x02#!SILK_V3")
    assert not resolved_silk_path.exists()


def _make_wav(path, rate, channels=1, secs=0.2, freq=440):
    """Write a short sine-tone WAV at the given rate/channels."""
    nframes = int(rate * secs)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for i in range(nframes):
            sample = int(0.2 * 32767 * math.sin(2 * math.pi * freq * i / rate))
            for _ in range(channels):
                wav.writeframesraw(struct.pack("<h", sample))


class _FakePysilk:
    """Stand-in for the ``pysilk`` module that records encode() calls."""

    def __init__(self):
        self.calls = []

    def encode(self, input_io, output_io, sample_rate, bit_rate, tencent=True):
        self.calls.append({"sample_rate": sample_rate, "tencent": tencent})
        output_io.write(b"\x02#!SILK_V3")


@pytest.mark.asyncio
async def test_wav_to_tencent_silk_resamples_unsupported_rate(tmp_path, monkeypatch):
    """44100 Hz input must be resampled to 24 kHz before pysilk.encode."""
    fake = _FakePysilk()
    monkeypatch.setitem(sys.modules, "pysilk", fake)

    wav_path = tmp_path / "tts_44100.wav"
    _make_wav(wav_path, 44100)

    silk_path = tmp_path / "out.silk"
    await wav_to_tencent_silk(str(wav_path), str(silk_path))

    assert len(fake.calls) == 1
    assert fake.calls[0]["sample_rate"] == 24000
    assert fake.calls[0]["tencent"] is True
    assert silk_path.read_bytes().startswith(b"\x02#!SILK_V3")


@pytest.mark.asyncio
async def test_wav_to_tencent_silk_resamples_stereo(tmp_path, monkeypatch):
    """Stereo input at a supported rate must still be downmixed to mono."""
    fake = _FakePysilk()
    monkeypatch.setitem(sys.modules, "pysilk", fake)

    wav_path = tmp_path / "stereo_48k.wav"
    _make_wav(wav_path, 48000, channels=2)

    await wav_to_tencent_silk(str(wav_path), str(tmp_path / "out.silk"))

    assert len(fake.calls) == 1
    # 48000 Hz is supported, so only downmix happens -- rate stays unchanged.
    assert fake.calls[0]["sample_rate"] == 48000


@pytest.mark.asyncio
async def test_wav_to_tencent_silk_skips_resample_for_supported_rate(
    tmp_path, monkeypatch
):
    """24000 Hz mono must go straight to pysilk without resampling."""
    fake = _FakePysilk()
    monkeypatch.setitem(sys.modules, "pysilk", fake)

    wav_path = tmp_path / "tone_24k.wav"
    _make_wav(wav_path, 24000)

    await wav_to_tencent_silk(str(wav_path), str(tmp_path / "out.silk"))

    assert len(fake.calls) == 1
    assert fake.calls[0]["sample_rate"] == 24000
