import base64
import os
from pathlib import Path

import pytest
from aiohttp import web

from astrbot.core.message import components as components_module
from astrbot.core.message.components import File, Image, Record
from tests.fixtures.helpers import get_bound_tcp_port


@pytest.mark.asyncio
async def test_image_convert_to_file_path_returns_absolute_path(tmp_path):
    file_path = tmp_path / "img.bin"
    file_path.write_bytes(b"img")

    image = Image(file=str(file_path))
    resolved = await image.convert_to_file_path()

    assert resolved == os.path.abspath(str(file_path))


@pytest.mark.asyncio
async def test_record_convert_to_file_path_returns_absolute_path(tmp_path):
    file_path = tmp_path / "record.bin"
    file_path.write_bytes(b"record")

    record = Record(file=str(file_path))
    resolved = await record.convert_to_file_path()

    assert resolved == os.path.abspath(str(file_path))


@pytest.mark.asyncio
async def test_file_component_get_file_returns_absolute_path(tmp_path):
    file_path = tmp_path / "file.bin"
    file_path.write_bytes(b"file")

    file_component = File(name="file.bin", file=str(file_path))
    resolved = await file_component.get_file()

    assert resolved == os.path.abspath(str(file_path))


@pytest.mark.asyncio
async def test_image_convert_to_base64_raises_on_missing_file(tmp_path):
    image = Image(file=str(tmp_path / "missing.bin"))

    with pytest.raises(Exception, match="not a valid file"):
        await image.convert_to_base64()


@pytest.mark.asyncio
async def test_record_convert_to_base64_raises_on_missing_file(tmp_path):
    record = Record(file=str(tmp_path / "missing.bin"))

    with pytest.raises(Exception, match="not a valid file"):
        await record.convert_to_base64()


@pytest.mark.asyncio
async def test_image_convert_to_base64_reads_existing_local_file(tmp_path):
    raw = b"image-bytes"
    file_path = tmp_path / "exists_image.bin"
    file_path.write_bytes(raw)

    image = Image(file=str(file_path))
    encoded = await image.convert_to_base64()

    assert base64.b64decode(encoded) == raw


@pytest.mark.asyncio
async def test_record_convert_to_base64_reads_existing_local_file(tmp_path):
    raw = b"record-bytes"
    file_path = tmp_path / "exists_record.bin"
    file_path.write_bytes(raw)

    record = Record(file=str(file_path))
    encoded = await record.convert_to_base64()

    assert base64.b64decode(encoded) == raw


@pytest.mark.asyncio
async def test_image_convert_to_base64_maps_permission_error(monkeypatch):
    async def _raise_permission_error(_path: str) -> str:
        raise PermissionError("permission denied")

    monkeypatch.setattr(components_module, "file_to_base64", _raise_permission_error)

    image = Image(file="/tmp/forbidden-image")
    with pytest.raises(Exception, match="not a valid file"):
        await image.convert_to_base64()


@pytest.mark.asyncio
async def test_record_convert_to_base64_maps_permission_error(monkeypatch):
    async def _raise_permission_error(_path: str) -> str:
        raise PermissionError("permission denied")

    monkeypatch.setattr(components_module, "file_to_base64", _raise_permission_error)

    record = Record(file="/tmp/forbidden-record")
    with pytest.raises(Exception, match="not a valid file"):
        await record.convert_to_base64()


@pytest.mark.asyncio
async def test_image_convert_to_file_path_from_base64_creates_absolute_file():
    payload = b"image-base64-payload"
    image = Image(file=f"base64://{base64.b64encode(payload).decode()}")

    resolved = await image.convert_to_file_path()
    resolved_path = Path(resolved)

    assert resolved_path.is_absolute()
    assert resolved_path.exists()
    assert resolved_path.read_bytes() == payload


@pytest.mark.asyncio
async def test_record_convert_to_file_path_from_base64_creates_absolute_file():
    payload = b"record-base64-payload"
    record = Record(file=f"base64://{base64.b64encode(payload).decode()}")

    resolved = await record.convert_to_file_path()
    resolved_path = Path(resolved)

    assert resolved_path.is_absolute()
    assert resolved_path.exists()
    assert resolved_path.read_bytes() == payload


async def _serve_payload(payload: bytes, route: str):
    async def handle(_request):
        return web.Response(body=payload)

    app = web.Application()
    app.router.add_get(route, handle)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, get_bound_tcp_port(site)


@pytest.mark.asyncio
async def test_image_convert_to_file_path_from_http_creates_absolute_file():
    payload = b"image-http-payload"
    runner, port = await _serve_payload(payload, "/img.bin")
    try:
        image = Image(file=f"http://127.0.0.1:{port}/img.bin")
        resolved = await image.convert_to_file_path()
        resolved_path = Path(resolved)

        assert resolved_path.is_absolute()
        assert resolved_path.exists()
        assert resolved_path.read_bytes() == payload
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_record_convert_to_file_path_from_http_creates_absolute_file():
    payload = b"record-http-payload"
    runner, port = await _serve_payload(payload, "/record.bin")
    try:
        record = Record(file=f"http://127.0.0.1:{port}/record.bin")
        resolved = await record.convert_to_file_path()
        resolved_path = Path(resolved)

        assert resolved_path.is_absolute()
        assert resolved_path.exists()
        assert resolved_path.read_bytes() == payload
    finally:
        await runner.cleanup()
