import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.message.components import Record


@pytest.mark.asyncio
async def test_record_convert_to_file_path_prefers_url_over_invalid_file_name():
    record = Record(
        file="0f47835d687410ab50cfed981e80c15c.amr",
        url="https://example.com/audio.amr",
    )

    with patch(
        "astrbot.core.message.components.download_image_by_url",
        AsyncMock(return_value="/tmp/audio.amr"),
    ):
        path = await record.convert_to_file_path()

    assert os.path.isabs(path)
    assert os.path.basename(path) == "audio.amr"


@pytest.mark.asyncio
async def test_record_convert_to_base64_prefers_url_over_invalid_file_name():
    record = Record(
        file="0f47835d687410ab50cfed981e80c15c.amr",
        url="https://example.com/audio.amr",
    )

    with (
        patch(
            "astrbot.core.message.components.download_image_by_url",
            AsyncMock(return_value="/tmp/audio.amr"),
        ),
        patch(
            "astrbot.core.message.components.file_to_base64",
            return_value="base64://ZmFrZQ==",
        ),
    ):
        encoded = await record.convert_to_base64()

    assert encoded == "ZmFrZQ=="


@pytest.mark.asyncio
async def test_record_convert_to_file_path_writes_base64_payload_with_audio_extension():
    record = Record(file="base64://ZmFrZQ==")

    path = await record.convert_to_file_path()

    assert os.path.isabs(path)
    assert Path(path).suffix == ".amr"
    assert Path(path).read_bytes() == b"fake"

    Path(path).unlink(missing_ok=True)
