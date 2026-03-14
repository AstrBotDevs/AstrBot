import pytest

from astrbot_sdk.testing import MockContext, MockMessageEvent
from main import HelloPlugin


@pytest.mark.asyncio
async def test_hello_handler() -> None:
    plugin = HelloPlugin()
    ctx = MockContext(plugin_id="hello_plugin")
    event = MockMessageEvent(text="/hello", context=ctx)

    await plugin.hello(event, ctx)

    assert event.replies == ["Hello, World!"]
    ctx.platform.assert_sent("Hello, World!")


@pytest.mark.asyncio
async def test_about_handler() -> None:
    plugin = HelloPlugin()
    ctx = MockContext(plugin_id="hello_plugin")
    event = MockMessageEvent(text="/about", context=ctx)

    await plugin.about(event, ctx)

    assert any("hello_plugin" in reply for reply in event.replies)
