from __future__ import annotations

from pathlib import Path

import pytest

from astrbot_sdk.message.components import File, Image, Record, Video


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("factory", "url", "prefix", "suffix"),
    [
        (Image.fromURL, "https://example.com/test.jpg", "imgseg", ".jpg"),
        (Record.fromURL, "https://example.com/test.dat", "recordseg", ".dat"),
        (Video.fromURL, "https://example.com/test.mp4", "videoseg", ""),
    ],
)
async def test_remote_media_download_uses_async_to_thread(
    monkeypatch: pytest.MonkeyPatch,
    factory,
    url: str,
    prefix: str,
    suffix: str,
) -> None:
    calls: list[tuple[object, tuple[object, ...]]] = []

    async def fake_to_thread(func, *args):
        calls.append((func, args))
        return str(Path("C:/tmp/downloaded.bin"))

    monkeypatch.setattr(
        "astrbot_sdk.message.components.asyncio.to_thread", fake_to_thread
    )

    component = factory(url)
    path = await component.convert_to_file_path()

    assert Path(path) == Path("C:/tmp/downloaded.bin")
    assert len(calls) == 1
    _, args = calls[0]
    assert args == (url, prefix, suffix)


@pytest.mark.asyncio
async def test_file_get_file_uses_async_to_thread_for_remote_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, tuple[object, ...]]] = []

    async def fake_to_thread(func, *args):
        calls.append((func, args))
        return str(Path("C:/tmp/file-download.bin"))

    monkeypatch.setattr(
        "astrbot_sdk.message.components.asyncio.to_thread", fake_to_thread
    )

    component = File(name="demo.bin", url="https://example.com/demo.bin")
    path = await component.get_file()

    assert Path(path) == Path("C:/tmp/file-download.bin")
    assert Path(component.file) == Path("C:/tmp/file-download.bin")
    assert len(calls) == 1
    _, args = calls[0]
    assert args == ("https://example.com/demo.bin", "fileseg", ".bin")
