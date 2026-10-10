import base64
import pathlib

import pytest

from astrbot.api.message_components import File
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.mark.asyncio
async def test_local_file_segment_uses_base64_payload(tmp_path):
    source_file = tmp_path / "cash.py"
    source_file.write_bytes(b"print('hello')\n")
    file_component = File(file=str(source_file), name="cash.py")

    payload = await AiocqhttpMessageEvent._from_segment_to_dict(file_component)

    encoded_file = base64.b64encode(source_file.read_bytes()).decode()
    assert payload == {
        "type": "file",
        "data": {
            "name": "cash.py",
            "file": f"base64://{encoded_file}",
        },
    }


@pytest.mark.asyncio
async def test_local_file_segment_derives_name_from_path(tmp_path):
    source_file = tmp_path / "report.txt"
    source_file.write_bytes(b"ready")
    file_component = File(name="", file=str(source_file))

    payload = await AiocqhttpMessageEvent._from_segment_to_dict(file_component)

    encoded_file = base64.b64encode(source_file.read_bytes()).decode()
    assert payload == {
        "type": "file",
        "data": {
            "name": "report.txt",
            "file": f"base64://{encoded_file}",
        },
    }


@pytest.mark.asyncio
async def test_file_segment_falls_back_to_uri_when_contents_unavailable(
    tmp_path,
    monkeypatch,
):
    source_file = tmp_path / "cash.py"
    source_file.write_bytes(b"print('hello')\n")

    def deny_file_read(self):
        raise PermissionError("file contents unavailable")

    monkeypatch.setattr(pathlib.Path, "read_bytes", deny_file_read)
    file_component = File(name="cash.py", file=str(source_file))

    payload = await AiocqhttpMessageEvent._from_segment_to_dict(file_component)

    assert payload == {
        "type": "file",
        "data": {
            "name": "cash.py",
            "file": source_file.as_uri(),
        },
    }
