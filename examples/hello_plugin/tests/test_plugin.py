import importlib.util
from pathlib import Path

import pytest

from astrbot_sdk.testing import MockContext, MockMessageEvent

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_plugin_class():
    module_path = PLUGIN_DIR / "main.py"
    spec = importlib.util.spec_from_file_location(
        "examples_hello_plugin_main",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.HelloPlugin


HelloPlugin = _load_plugin_class()


@pytest.mark.asyncio
async def test_hello_handler() -> None:
    plugin = HelloPlugin()
    ctx = MockContext(
        plugin_id="hello_plugin",
        plugin_metadata={"display_name": "Hello Plugin"},
    )
    event = MockMessageEvent(text="/hello", context=ctx)

    await plugin.hello(event, ctx)

    assert event.replies == ["Hello, World!"]
    ctx.platform.assert_sent("Hello, World!")


@pytest.mark.asyncio
async def test_about_handler() -> None:
    plugin = HelloPlugin()
    ctx = MockContext(
        plugin_id="hello_plugin",
        plugin_metadata={"display_name": "Hello Plugin"},
    )
    event = MockMessageEvent(text="/about", context=ctx)

    await plugin.about(event, ctx)

    assert any("Hello Plugin" in reply for reply in event.replies)
