import base64
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import pytest

import astrbot.core.utils.media_utils as media_utils
from astrbot.core.message.components import Image, Record, Video
from astrbot.core.provider.entities import ProviderRequest


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
    PILImage.new("RGBA", (2, 2), (255, 0, 0, 128)).save(image_path)

    converted_path = Path(await media_utils.ensure_jpeg(str(image_path)))

    assert converted_path.suffix == ".jpg"
    assert converted_path.parent == temp_dir
    assert converted_path.exists()
    with PILImage.open(converted_path) as converted_img:
        assert converted_img.format == "JPEG"


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

    assert "A" * 64 not in media_utils.describe_media_ref(data_ref)
    assert "token=secret" not in media_utils.describe_media_ref(url_ref)
    assert "example.com" in media_utils.describe_media_ref(url_ref)


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


def test_file_uri_to_path_supports_localhost_and_encoded_paths(tmp_path):
    media_path = tmp_path / "voice note.wav"
    media_path.write_bytes(b"audio")
    file_uri = f"file://localhost{quote(media_path.as_posix())}"

    assert media_utils.file_uri_to_path(file_uri) == str(media_path)
