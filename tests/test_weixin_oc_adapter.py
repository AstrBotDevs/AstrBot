import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter


@pytest.mark.asyncio
async def test_run_continues_after_inbound_long_poll_timeout():
    adapter = WeixinOCAdapter(
        platform_config={
            "id": "weixin_main",
            "type": "weixin_oc",
            "weixin_oc_token": "test-token",
        },
        platform_settings={},
        event_queue=asyncio.Queue(),
    )
    adapter.client.close = AsyncMock()

    call_count = 0

    async def fake_poll_inbound_updates():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise asyncio.TimeoutError()
        adapter._shutdown_event.set()

    adapter._poll_inbound_updates = fake_poll_inbound_updates  # type: ignore[method-assign]

    await adapter.run()

    assert call_count == 2
    adapter.client.close.assert_awaited_once()
