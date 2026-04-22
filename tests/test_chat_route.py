import asyncio
from pathlib import Path

import pytest

from astrbot.dashboard.routes.chat import ChatRoute, _poll_webchat_stream_result


class _QueueThatRaises:
    def __init__(self, exc: BaseException):
        self._exc = exc

    async def get(self):
        raise self._exc


class _QueueWithResult:
    def __init__(self, result):
        self._result = result

    async def get(self):
        return self._result


@pytest.mark.asyncio
async def test_poll_webchat_stream_result_breaks_on_cancelled_error():
    result, should_break = await _poll_webchat_stream_result(
        _QueueThatRaises(asyncio.CancelledError()),
        "alice",
    )

    assert result is None
    assert should_break is True


@pytest.mark.asyncio
async def test_poll_webchat_stream_result_continues_on_generic_exception():
    result, should_break = await _poll_webchat_stream_result(
        _QueueThatRaises(RuntimeError("boom")),
        "alice",
    )

    assert result is None
    assert should_break is False


@pytest.mark.asyncio
async def test_poll_webchat_stream_result_returns_queue_payload():
    payload = {"type": "end", "data": ""}

    result, should_break = await _poll_webchat_stream_result(
        _QueueWithResult(payload),
        "alice",
    )

    assert result == payload
    assert should_break is False


def test_resolve_workspace_path_blocks_traversal(tmp_path: Path):
    route = ChatRoute.__new__(ChatRoute)
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(ValueError):
        route._resolve_workspace_path(root, "../secret.txt")


def test_serialize_workspace_entry_marks_text_previewable(tmp_path: Path):
    route = ChatRoute.__new__(ChatRoute)
    root = tmp_path / "workspace"
    root.mkdir()
    file_path = root / "notes.md"
    file_path.write_text("# notes", encoding="utf-8")

    payload = route._serialize_workspace_entry(root, file_path)

    assert payload["path"] == "notes.md"
    assert payload["type"] == "file"
    assert payload["previewable"] is True
