"""Byte limits before image decoding, including input and cleanup ownership."""

import asyncio
import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image as PILImage

from astrbot.core.message.components import Image
from astrbot.core.pipeline.preprocess_stage import stage as preprocess_module
from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils import io, media_utils
from astrbot.core.utils.media_utils import MediaInputTooLargeError, MediaResolver


@pytest.fixture
def media_env(tmp_path, monkeypatch):
    temp = tmp_path / "temp"
    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(temp))
    monkeypatch.setattr(preprocess_module, "get_astrbot_temp_path", lambda: str(temp))
    output = BytesIO()
    PILImage.new("RGB", (4, 4), "red").save(output, "PNG")
    return temp, output.getvalue()


class Response:
    def __init__(self, chunks, length=None):
        self.status = 200
        self.headers = {} if length is None else {"content-length": str(length)}
        self.content = self
        self.chunks = iter(chunks)
        self.read_sizes = []

    async def read(self, size):
        self.read_sizes.append(size)
        chunk = next(self.chunks, b"")
        if isinstance(chunk, BaseException):
            raise chunk
        return chunk

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class Session:
    def __init__(self, response):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def patch_http(monkeypatch, response):
    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **kwargs: object())
    monkeypatch.setattr(io.aiohttp, "ClientSession", lambda **kwargs: Session(response))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["data", "scheme", "bare", "whitespace", "no_padding"])
async def test_bounded_base64_exact_bytes_and_cleanup(media_env, kind):
    temp, original = media_env
    encoded = base64.b64encode(original).decode()
    if kind == "data":
        encoded = "data:image/png;base64," + encoded
    elif kind == "scheme":
        encoded = "base64://" + encoded
    elif kind == "whitespace":
        encoded = "base64://" + " \n".join(encoded)
    elif kind == "no_padding":
        encoded = encoded.rstrip("=")
    async with MediaResolver(
        encoded, media_type="image", max_bytes=len(original)
    ).as_path() as result:
        assert result.path.read_bytes() == original
        assert result.path.suffix == ".png"
        assert result.mime_type == "image/png"
        path = result.path
    assert not path.exists()
    assert not list(temp.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["", "base64://", "data:image/png;base64,"])
async def test_base64_oversize_precedes_decoding(media_env, monkeypatch, prefix):
    temp, original = media_env
    reference = prefix + base64.b64encode(original).decode()

    def forbidden_decode(*args, **kwargs):
        raise AssertionError("Oversized input must not be decoded")

    monkeypatch.setattr(media_utils.base64, "b64decode", forbidden_decode)
    with pytest.raises(MediaInputTooLargeError):
        await MediaResolver(
            reference, media_type="image", max_bytes=len(original) - 1
        ).to_path()
    assert not temp.exists() or not list(temp.iterdir())


@pytest.mark.asyncio
async def test_large_base64_decodes_in_chunks(media_env, monkeypatch):
    temp, original = media_env
    original += b"x" * 200000
    reference = "base64://" + base64.b64encode(original).decode()
    decode = media_utils.base64.b64decode
    lengths = []

    def measured_decode(value, **kwargs):
        lengths.append(len(value))
        assert len(value) <= 65536
        return decode(value, **kwargs)

    monkeypatch.setattr(media_utils.base64, "b64decode", measured_decode)
    async with MediaResolver(
        reference, media_type="image", max_bytes=len(original)
    ).as_path() as result:
        assert result.path.read_bytes() == original
    assert len(lengths) > 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ["YQ==YQ==", "@@@@", "Y", "=YQ=", "YQ==="])
async def test_malformed_base64_rejected_without_orphans(media_env, payload):
    temp, _ = media_env
    with pytest.raises(ValueError):
        await MediaResolver(
            "base64://" + payload, media_type="image", max_bytes=100
        ).to_path()
    assert not temp.exists() or not list(temp.iterdir())


@pytest.mark.asyncio
async def test_local_stat_cap_and_cleanup_ownership(media_env, tmp_path):
    _, original = media_env
    source = tmp_path / "image.png"
    source.write_bytes(original)
    for reference in (str(source), source.as_uri()):
        with pytest.raises(MediaInputTooLargeError):
            await MediaResolver(
                reference, media_type="image", max_bytes=len(original) - 1
            ).to_path()
        async with MediaResolver(
            reference, media_type="image", max_bytes=len(original)
        ).as_path() as result:
            assert result.path == source
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_http_content_length_rejects_before_read(media_env, monkeypatch):
    temp, original = media_env
    response = Response([original], len(original))
    patch_http(monkeypatch, response)
    with pytest.raises(MediaInputTooLargeError):
        await MediaResolver(
            "https://example.test/image", media_type="image", max_bytes=1
        ).to_path()
    assert not response.read_sizes
    assert not list(temp.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [None, 1])
async def test_http_stream_cap_cannot_be_bypassed_by_length(
    media_env, monkeypatch, length
):
    temp, original = media_env
    response = Response([original[:20], original[20:]], length)
    patch_http(monkeypatch, response)
    with pytest.raises(MediaInputTooLargeError):
        await MediaResolver(
            "https://example.test/image", media_type="image", max_bytes=30
        ).to_path()
    assert response.read_sizes == [8192, 8192]
    assert not list(temp.iterdir())


@pytest.mark.asyncio
async def test_http_exact_limit_succeeds_and_renames_without_decoding(
    media_env, monkeypatch
):
    temp, original = media_env
    response = Response([original], len(original))
    patch_http(monkeypatch, response)
    async with MediaResolver(
        "https://example.test/image", media_type="image", max_bytes=len(original)
    ).as_path() as result:
        assert result.path.suffix == ".png"
        assert result.path.read_bytes() == original
    assert not list(temp.iterdir())


@pytest.mark.asyncio
async def test_http_cancellation_removes_partial_file(media_env, monkeypatch):
    temp, original = media_env
    response = Response([original[:20], asyncio.CancelledError()])
    patch_http(monkeypatch, response)
    with pytest.raises(asyncio.CancelledError):
        await MediaResolver(
            "https://example.test/image", media_type="image", max_bytes=100
        ).to_path()
    assert not list(temp.iterdir())


@pytest.mark.asyncio
async def test_base64_cancellation_removes_partial_file(media_env, monkeypatch):
    temp, original = media_env
    reference = "base64://" + base64.b64encode(original + b"x" * 200000).decode()
    decode = media_utils.base64.b64decode

    def cancelled_decode(value, **kwargs):
        result = decode(value, **kwargs)
        asyncio.current_task().cancel()
        return result

    monkeypatch.setattr(media_utils.base64, "b64decode", cancelled_decode)
    with pytest.raises(asyncio.CancelledError):
        await MediaResolver(reference, media_type="image", max_bytes=300000).to_path()
    assert not list(temp.iterdir())


@pytest.mark.asyncio
async def test_default_resolver_preserves_old_download_signature(
    media_env, monkeypatch
):
    temp, original = media_env

    async def legacy_download(url, path):
        Path(path).write_bytes(original)

    monkeypatch.setattr(media_utils, "download_file", legacy_download)
    async with MediaResolver(
        "https://example.test/image", media_type="image"
    ).as_path() as result:
        assert result.path.read_bytes() == original


@pytest.mark.parametrize("maximum", [0, -1, True, "64", 0.5])
def test_invalid_cap_rejected(maximum):
    with pytest.raises(ValueError):
        MediaResolver("image.png", media_type="image", max_bytes=maximum)


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_preprocess_feature_selects_bounded_resolver(
    media_env, monkeypatch, tmp_path, enabled
):
    _, original = media_env
    path = tmp_path / "source.png"
    path.write_bytes(original)
    component = Image(file=str(path))
    event = SimpleNamespace(_temporary_local_files=[])
    event.track_temporary_local_file = lambda p: (
        AstrMessageEvent.track_temporary_local_file(event, p)
    )
    event.untrack_temporary_local_file = lambda p: (
        AstrMessageEvent.untrack_temporary_local_file(event, p)
    )
    stage = PreProcessStage()
    stage.config = {"provider_settings": {"image_context_enabled": enabled}}
    legacy = AsyncMock(return_value=str(path))
    monkeypatch.setattr(Image, "convert_to_file_path", legacy)
    await stage._normalize_image_component(event, component)
    assert component.file == str(path)
    assert legacy.await_count == (0 if enabled else 1)
    assert event._temporary_local_files == []


def test_large_rejected_reference_logging_does_not_decode(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Logging must not decode large rejected input")

    monkeypatch.setattr(media_utils.base64, "b64decode", forbidden)
    for reference in (
        "A" * 100000,
        "base64://" + "A" * 100000,
        "data:image/png;base64," + "A" * 100000,
    ):
        description = media_utils.describe_media_ref(reference)
        assert len(description) < 200


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate", "gzip, identity"])
async def test_bounded_http_rejects_compressed_transport_before_read(
    media_env, monkeypatch, encoding
):
    temp, original = media_env
    response = Response([original], len(original))
    response.headers["content-encoding"] = encoding
    options = []

    class InspectSession(Session):
        def get(self, *args, **kwargs):
            options.append(kwargs)
            return self.response

    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **kwargs: object())
    monkeypatch.setattr(
        io.aiohttp, "ClientSession", lambda **kwargs: InspectSession(response)
    )
    with pytest.raises(ValueError, match="Encoded HTTP"):
        await MediaResolver(
            "https://example.test/image", media_type="image", max_bytes=100
        ).to_path()
    assert options[0]["auto_decompress"] is False
    assert options[0]["headers"] == {"Accept-Encoding": "identity"}
    assert not response.read_sizes
    assert not list(temp.iterdir())


@pytest.mark.asyncio
async def test_unbounded_http_keeps_existing_transport_options(media_env, monkeypatch):
    _, original = media_env
    response = Response([original], len(original))
    response.headers["content-encoding"] = "gzip"
    options = []

    class InspectSession(Session):
        def get(self, *args, **kwargs):
            options.append(kwargs)
            return self.response

    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **kwargs: object())
    monkeypatch.setattr(
        io.aiohttp, "ClientSession", lambda **kwargs: InspectSession(response)
    )
    async with MediaResolver(
        "https://example.test/image", media_type="image"
    ).as_path() as result:
        assert result.path.read_bytes() == original
    assert "auto_decompress" not in options[0]
    assert "headers" not in options[0]


@pytest.mark.asyncio
async def test_bounded_http_ssl_fallback_keeps_limits(media_env, monkeypatch):
    temp, original = media_env

    class CertificateFailure(Exception):
        pass

    monkeypatch.setattr(io.aiohttp, "ClientConnectorSSLError", CertificateFailure)
    monkeypatch.setattr(
        io.aiohttp, "ClientConnectorCertificateError", CertificateFailure
    )
    response = Response([original], len(original))
    options = []

    class FallbackSession(Session):
        def get(self, *args, **kwargs):
            options.append(kwargs)
            if len(options) == 1:
                raise CertificateFailure()
            return self.response

    monkeypatch.setattr(io.aiohttp, "TCPConnector", lambda **kwargs: object())
    monkeypatch.setattr(
        io.aiohttp, "ClientSession", lambda **kwargs: FallbackSession(response)
    )
    with pytest.raises(MediaInputTooLargeError):
        await MediaResolver(
            "https://example.test/image", media_type="image", max_bytes=1
        ).to_path()
    assert len(options) == 2
    assert all(
        option["auto_decompress"] is False
        and option["headers"] == {"Accept-Encoding": "identity"}
        for option in options
    )
    assert not response.read_sizes
    assert not list(temp.iterdir())
