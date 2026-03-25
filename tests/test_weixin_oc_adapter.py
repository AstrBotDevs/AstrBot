import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter


def _make_adapter() -> WeixinOCAdapter:
    return WeixinOCAdapter(
        platform_config={
            "id": "weixin_main",
            "type": "weixin_oc",
            "weixin_oc_token": "test-token",
        },
        platform_settings={},
        event_queue=asyncio.Queue(),
    )


@pytest.mark.asyncio
async def test_run_keeps_polling_after_inbound_timeout():
    adapter = _make_adapter()
    adapter.client.close = AsyncMock()

    calls = 0

    async def fake_poll_inbound_updates():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise asyncio.TimeoutError()
        adapter._shutdown_event.set()

    adapter._poll_inbound_updates = fake_poll_inbound_updates  # type: ignore[method-assign]

    with patch(
        "astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter.logger"
    ) as mock_logger:
        await adapter.run()

    assert calls == 2
    mock_logger.debug.assert_any_call(
        "weixin_oc(%s): inbound long-poll timeout",
        "weixin_main",
    )
    mock_logger.exception.assert_not_called()
    adapter.client.close.assert_awaited_once()
