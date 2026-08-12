from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from astrbot.core.platform.sources.qqofficial import qqofficial_message_event
from astrbot.core.platform.sources.qqofficial.qqofficial_chunked_upload import (
    QQOfficialChunkedUploader,
    _compute_file_hashes,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)


class _FakeResponse:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def json(self, **_kwargs: object) -> dict[str, Any]:
        return self._payload

    async def text(self, **_kwargs: object) -> str:
        return str(self._payload)


class _FakeSession:
    def __init__(self, part_indexes: list[int]) -> None:
        self.part_indexes = part_indexes
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.put_parts: dict[int, bytes] = {}
        self.finish_attempts: dict[int, int] = {}
        self.merge_attempts = 0

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append((method, url, kwargs))
        if method == "PUT":
            part_index = int(url.rsplit("/", 1)[-1])
            self.put_parts[part_index] = kwargs["data"]
            return _FakeResponse(200, {})

        body = kwargs["json"]
        if url.endswith("/upload_prepare"):
            return _FakeResponse(
                200,
                {
                    "upload_id": "upload-1",
                    "block_size": "4",
                    "parts": [
                        {
                            "index": self.part_indexes[0],
                            "presigned_url": (
                                f"https://cos.test/part/{self.part_indexes[0]}"
                            ),
                            "block_size": "4",
                        },
                        {
                            "index": self.part_indexes[1],
                            "presigned_url": (
                                f"https://cos.test/part/{self.part_indexes[1]}"
                            ),
                            "block_size": "4",
                        },
                        {
                            "index": self.part_indexes[2],
                            "presigned_url": (
                                f"https://cos.test/part/{self.part_indexes[2]}"
                            ),
                            "block_size": "2",
                        },
                    ],
                    "upload_config": {
                        "concurrency": 2,
                        "retry_timeout": 1,
                        "retry_delay": 0,
                    },
                },
            )
        if url.endswith("/upload_part_finish"):
            part_index = body["part_index"]
            self.finish_attempts[part_index] = (
                self.finish_attempts.get(part_index, 0) + 1
            )
            if (
                part_index == self.part_indexes[0]
                and self.finish_attempts[part_index] == 1
            ):
                return _FakeResponse(
                    400,
                    {"code": 40093001, "message": "retry part"},
                )
            return _FakeResponse(200, {})
        if url.endswith("/files"):
            self.merge_attempts += 1
            if self.merge_attempts == 1:
                return _FakeResponse(
                    400,
                    {"code": 40093001, "message": "retry merge"},
                )
            return _FakeResponse(
                200,
                {
                    "file_uuid": "file-uuid",
                    "file_info": "file-info",
                    "ttl": 300,
                },
            )
        raise AssertionError(f"Unexpected request: {method} {url}")


class _FakeHttp:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session
        self._headers = {"Authorization": "QQBot token"}
        self.is_sandbox = False

    async def check_session(self) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "target", "base_path", "part_indexes"),
    [
        (
            "upload_c2c",
            {"user_openid": "user-1"},
            "/v2/users/user-1",
            [0, 1, 2],
        ),
        (
            "upload_group",
            {"group_openid": "group-1"},
            "/v2/groups/group-1",
            [1, 2, 3],
        ),
    ],
)
async def test_chunked_upload_supports_destination_index_base(
    tmp_path: Path,
    method_name: str,
    target: dict[str, str],
    base_path: str,
    part_indexes: list[int],
) -> None:
    """C2C and group uploads should honor their server-provided index bases."""
    file_data = b"abcdefghij"
    file_path = tmp_path / "report.bin"
    file_path.write_bytes(file_data)
    session = _FakeSession(part_indexes)
    uploader = QQOfficialChunkedUploader(_FakeHttp(session))  # type: ignore[arg-type]

    upload = getattr(uploader, method_name)
    media = await upload(
        file_path=file_path,
        file_type=4,
        file_name="report.bin",
        **target,
    )

    assert media == {
        "file_uuid": "file-uuid",
        "file_info": "file-info",
        "ttl": 300,
    }
    assert b"".join(session.put_parts[index] for index in part_indexes) == file_data
    assert session.finish_attempts == {
        part_indexes[0]: 2,
        part_indexes[1]: 1,
        part_indexes[2]: 1,
    }
    assert session.merge_attempts == 2

    prepare_call = next(
        call for call in session.calls if call[1].endswith("/upload_prepare")
    )
    assert prepare_call[1] == f"https://api.sgroup.qq.com{base_path}/upload_prepare"
    assert prepare_call[2]["json"] == {
        "file_type": 4,
        "file_size": "10",
        "file_name": "report.bin",
        "md5": hashlib.md5(file_data, usedforsecurity=False).hexdigest(),
        "sha1": hashlib.sha1(file_data, usedforsecurity=False).hexdigest(),
        "md5_10m": hashlib.md5(file_data, usedforsecurity=False).hexdigest(),
    }

    finish_calls = [
        call for call in session.calls if call[1].endswith("/upload_part_finish")
    ]
    finish_bodies = [call[2]["json"] for call in finish_calls]
    assert {body["part_index"] for body in finish_bodies} == set(part_indexes)
    assert all(isinstance(body["block_size"], str) for body in finish_bodies)
    assert all(
        set(body) == {"upload_id", "part_index", "block_size", "md5"}
        for body in finish_bodies
    )

    merge_call = next(call for call in session.calls if call[1].endswith("/files"))
    assert merge_call[2]["json"] == {
        "file_type": 4,
        "srv_send_msg": False,
        "file_name": "report.bin",
        "upload_id": "upload-1",
    }


def test_hashes_use_qq_exact_md5_10m_prefix(tmp_path: Path) -> None:
    """md5_10m should hash exactly QQ's documented 10,002,432-byte prefix."""
    prefix = b"x" * 10_002_432
    file_path = tmp_path / "large.bin"
    file_path.write_bytes(prefix + b"suffix")

    hashes = _compute_file_hashes(file_path)

    assert (
        hashes["md5"]
        == hashlib.md5(prefix + b"suffix", usedforsecurity=False).hexdigest()
    )
    assert (
        hashes["sha1"]
        == hashlib.sha1(prefix + b"suffix", usedforsecurity=False).hexdigest()
    )
    assert hashes["md5_10m"] == hashlib.md5(prefix, usedforsecurity=False).hexdigest()


@pytest.mark.asyncio
async def test_large_local_media_uses_chunked_uploader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The existing upload entrypoint should delegate large local files."""
    captured: dict[str, Any] = {}

    class _CapturingUploader:
        def __init__(self, http: object) -> None:
            captured["http"] = http

        async def upload_group(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "file_uuid": "file-uuid",
                "file_info": "file-info",
                "ttl": 0,
            }

    file_path = tmp_path / "large.bin"
    file_path.write_bytes(b"ab")
    http = object()
    owner = SimpleNamespace(_bot=SimpleNamespace(api=SimpleNamespace(_http=http)))
    monkeypatch.setattr(
        qqofficial_message_event,
        "QQOFFICIAL_CHUNKED_UPLOAD_THRESHOLD",
        1,
    )
    monkeypatch.setattr(
        qqofficial_message_event,
        "QQOfficialChunkedUploader",
        _CapturingUploader,
    )

    media = await QQOfficialMessageEvent.upload_group_and_c2c_media(
        owner,  # type: ignore[arg-type]
        str(file_path),
        QQOfficialMessageEvent.FILE_FILE_TYPE,
        file_name="large.bin",
        group_openid="group-1",
    )

    assert media == {
        "file_uuid": "file-uuid",
        "file_info": "file-info",
        "ttl": 0,
    }
    assert captured == {
        "http": http,
        "file_path": file_path,
        "file_type": 4,
        "file_name": "large.bin",
        "srv_send_msg": False,
        "group_openid": "group-1",
    }
