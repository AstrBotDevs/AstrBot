import base64

import pytest

from astrbot.core.utils.io import file_to_base64


@pytest.mark.asyncio
async def test_file_to_base64_reads_file_async(tmp_path):
    sample_file = tmp_path / "sample.bin"
    sample_file.write_bytes(b"astrbot")

    result = await file_to_base64(str(sample_file))

    expected = "base64://" + base64.b64encode(b"astrbot").decode()
    assert result == expected
