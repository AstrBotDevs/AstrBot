from pathlib import Path

import pytest

from astrbot_sdk.testing import PluginHarness


@pytest.mark.asyncio
async def test_dispatch_hello_command() -> None:
    plugin_dir = Path(__file__).resolve().parents[1]

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        records = await harness.dispatch_text("hello")

    assert any(record.text == "Hello, World!" for record in records)
