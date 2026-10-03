import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from slack_sdk.web.internal_utils import _to_v2_file_upload_item

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Plain
from astrbot.api.platform import MessageType
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent
from astrbot.core.utils import media_utils


@pytest.fixture
def download(monkeypatch, tmp_path):
    paths = []

    async def fake_download(url, path):
        assert url in {"http://example.com/README.md", "https://example.com/README.md"}
        target = Path(path)
        target.write_bytes(b"# README\n")
        paths.append(target)

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    mock = AsyncMock(side_effect=fake_download)
    monkeypatch.setattr(media_utils, "download_file", mock)
    return mock, paths


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("name", ["README.md", "说明文档.md", ""])
async def test_slack_remote_file_upload_uses_content_and_cleans_temp(
    download, scheme, name
):
    client = AsyncMock()

    async def upload(**kwargs):
        # Exercise the real SDK input conversion which previously opened the URL.
        item = _to_v2_file_upload_item(kwargs)
        assert download[1][0].exists()
        assert kwargs["filename"] == (name or "file")
        assert item["data"] == b"# README\n"
        assert item["filename"] == (name or "file")
        assert item["title"] == (name or "file")
        return {"ok": True, "files": [{"permalink": "https://slack.test/file"}]}

    client.files_upload_v2.side_effect = upload
    segment = File(name=name, url=f"{scheme}://example.com/README.md")
    blocks, text = await SlackMessageEvent._parse_slack_blocks(
        MessageChain([Plain("Attached README"), segment]), client
    )

    assert blocks[0]["text"]["text"] == "Attached README"
    assert (
        blocks[1]["text"]["text"] == f"文件: <https://slack.test/file|{name or '文件'}>"
    )
    assert text == ""
    assert not download[1][0].exists()
    assert segment.file_ == ""
    client.files_upload_v2.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("file_uri", [False, True])
@pytest.mark.parametrize("fail_upload", [False, True])
@pytest.mark.parametrize("local_url", [False, True])
async def test_slack_local_file_is_preserved(
    tmp_path, download, file_uri, fail_upload, local_url
):
    path = tmp_path / "local.md"
    path.write_bytes(b"local content")
    client = AsyncMock()
    client.files_upload_v2.return_value = {
        "ok": True,
        "files": [{"permalink": "https://slack.test/local"}],
    }
    if fail_upload:
        client.files_upload_v2.side_effect = RuntimeError("upload failed")
    source = path.as_uri() if file_uri else str(path)
    segment = File(name="local.md", file=source, url=source if local_url else "")

    if fail_upload:
        with pytest.raises(RuntimeError, match="upload failed"):
            await SlackMessageEvent._from_segment_to_slack_block(segment, client)
    else:
        await SlackMessageEvent._from_segment_to_slack_block(segment, client)

    client.files_upload_v2.assert_awaited_once_with(
        file=b"local content", filename="local.md"
    )
    assert path.read_bytes() == b"local content"
    download[0].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["download", "upload", "response"])
async def test_slack_file_failure_cleans_download(download, failure):
    client = AsyncMock()
    if failure == "download":
        original = download[0].side_effect

        async def fail_download(url, path):
            await original(url, path)
            raise RuntimeError("download failed")

        download[0].side_effect = fail_download
    elif failure == "upload":
        client.files_upload_v2.side_effect = RuntimeError("upload failed")
    else:
        client.files_upload_v2.return_value = {"ok": False, "error": "upload failed"}

    segment = File(name="README.md", url="https://example.com/README.md")
    if failure == "response":
        block = await SlackMessageEvent._from_segment_to_slack_block(segment, client)
        assert block["text"]["text"] == "文件上传失败"
    else:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            await SlackMessageEvent._parse_slack_blocks(
                MessageChain([Plain("Attached README"), segment]), client
            )
    assert download[1]
    assert all(not path.exists() for path in download[1])
    client.chat_postMessage.assert_not_awaited()
    if failure == "download":
        client.files_upload_v2.assert_not_awaited()


@pytest.mark.asyncio
async def test_slack_cancelled_download_cleans_partial_file(download, tmp_path):
    client = AsyncMock()
    started = asyncio.Event()
    original = download[0].side_effect
    local_file = tmp_path / "keep.md"
    local_file.write_bytes(b"local content")

    async def interrupted_download(url, path):
        await original(url, path)
        started.set()
        await asyncio.Event().wait()

    download[0].side_effect = interrupted_download
    task = asyncio.create_task(
        SlackMessageEvent._from_segment_to_slack_block(
            File(name="README.md", url="https://example.com/README.md"), client
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert download[1]
    assert all(not path.exists() for path in download[1])
    assert local_file.read_bytes() == b"local content"
    client.files_upload_v2.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_local_file", [False, True])
@pytest.mark.parametrize(
    "url",
    [
        "[README](https://example.com/README.md)",
        "ftp://example.com/file",
        "file:///etc/passwd",
        "data:text/plain;base64,eA==",
    ],
)
async def test_slack_invalid_file_url_fails_before_upload(
    download, tmp_path, url, missing_local_file
):
    client = AsyncMock()
    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        await SlackMessageEvent._from_segment_to_slack_block(
            File(
                name="README.md",
                file=str(tmp_path / "missing.md") if missing_local_file else "",
                url=url,
            ),
            client,
        )
    download[0].assert_not_awaited()
    client.files_upload_v2.assert_not_awaited()


@pytest.mark.asyncio
async def test_slack_missing_file_fails_before_upload(tmp_path, download):
    client = AsyncMock()
    with pytest.raises(ValueError, match="existing file"):
        await SlackMessageEvent._from_segment_to_slack_block(
            File(name="missing", file=str(tmp_path / "missing")), client
        )
    download[0].assert_not_awaited()
    client.files_upload_v2.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_upload", [False, True])
async def test_slack_send_by_session_preserves_plain_and_failure_behavior(
    download, fail_upload, monkeypatch
):
    monkeypatch.setattr(Platform, "send_by_session", AsyncMock())
    adapter = object.__new__(SlackAdapter)
    adapter.web_client = AsyncMock()
    adapter.web_client.files_upload_v2.return_value = {
        "ok": True,
        "files": [{"permalink": "https://slack.test/file"}],
    }
    if fail_upload:
        adapter.web_client.files_upload_v2.side_effect = RuntimeError("upload failed")
    session = MessageSesion(
        platform_name="slack", message_type=MessageType.GROUP_MESSAGE, session_id="C123"
    )
    chain = MessageChain(
        [
            Plain("Attached README"),
            File(name="README.md", url="https://example.com/README.md"),
        ]
    )

    if fail_upload:
        with pytest.raises(RuntimeError, match="upload failed"):
            await adapter.send_by_session(session, chain)
        adapter.web_client.chat_postMessage.assert_not_awaited()
    else:
        await adapter.send_by_session(session, chain)
        kwargs = adapter.web_client.chat_postMessage.await_args.kwargs
        assert kwargs["channel"] == "C123"
        assert kwargs["blocks"][0]["text"]["text"] == "Attached README"
        assert "https://slack.test/file" in kwargs["blocks"][1]["text"]["text"]
    assert download[1]
    assert all(not path.exists() for path in download[1])
