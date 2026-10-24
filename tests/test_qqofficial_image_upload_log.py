from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from astrbot.core.platform.sources.qqofficial import qqofficial_message_event
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)


class _NoneReturningHTTP:
    """Minimal botpy HTTP stub: every upload request returns ``None``."""

    def __init__(self) -> None:
        self.calls = 0

    async def request(self, _route: object, json: object = None) -> None:
        self.calls += 1
        return None


def _fake_event(http: _NoneReturningHTTP) -> SimpleNamespace:
    return SimpleNamespace(bot=SimpleNamespace(api=SimpleNamespace(_http=http)))


@pytest.mark.asyncio
async def test_image_upload_failure_never_logs_image_bytes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed image upload must log one compact line, never the base64 payload.

    The upload payload carries the whole image as base64 (megabytes for a card
    image). Dumping it into the log froze the log stream / web dashboard.
    """

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    http = _NoneReturningHTTP()
    event = _fake_event(http)
    image_base64 = "iVBORw0KGgo" + "A" * 8192

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        with pytest.raises(qqofficial_message_event.APIReturnNoneError):
            await QQOfficialMessageEvent.upload_group_and_c2c_image(
                event, image_base64, 1, group_openid="group-openid"
            )

    assert http.calls == qqofficial_message_event._IMAGE_UPLOAD_MAX_ATTEMPTS

    messages = [record.getMessage() for record in caplog.records]
    assert all(image_base64 not in message for message in messages), (
        "日志不得包含图片 base64 数据"
    )
    assert all("file_data" not in message for message in messages)

    summary = [message for message in messages if "上传图片失败" in message]
    assert len(summary) == 1, f"失败只应留下一条汇总日志，实际: {summary}"
    assert "group-openid" in summary[0]
