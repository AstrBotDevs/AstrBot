from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.platform.contracts.onebot import (
    OneBotActionRejected,
    OneBotActionResult,
    OneBotActionTimeout,
    OneBotActionUnavailable,
    OneBotActionValidationError,
    OneBotCapabilityUnavailable,
    OneBotMessageEvent,
    OneBotTransportError,
)
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.onebot_capability import OneBotCapability
from astrbot.core.platform.sources.napcat.exceptions import (
    NapCatApiError,
    NapCatTransportError,
)
from astrbot.core.platform.sources.napcat.inbound_events import dispatch_inbound_event
from astrbot.core.platform.sources.napcat.napcat_platform_adapter import (
    NapCatPlatformAdapter,
)
from astrbot.core.platform.sources.napcat.types import (
    NapCatLoginInfo,
    NapCatSendMessageResult,
    NapCatStatus,
    NapCatVersionInfo,
)


def _event(*, payload: dict, platform_id: str = "napcat-main") -> MagicMock:
    event = MagicMock()
    event.get_extra.side_effect = lambda key, default=None: {
        "napcat_raw_payload": payload,
        "platform_event": "napcat",
    }.get(key, default)
    event.get_platform_id.return_value = platform_id
    return event


def test_capability_facade_rejects_non_onebot_events() -> None:
    facade = OneBotCapability(MagicMock())
    event = MagicMock()
    event.get_extra.return_value = None

    assert facade.event(event) is None
    assert facade.for_event(event) is None
    assert facade.supports(event, "onebot.v11") is False


def test_napcat_extensions_require_napcat_provider_marker() -> None:
    facade = OneBotCapability(MagicMock())
    event = MagicMock()
    event.get_extra.side_effect = lambda key, default=None: {
        "napcat_raw_payload": {"post_type": "message", "self_id": 1},
        "platform_event": "other-platform",
    }.get(key, default)

    assert facade.supports(event, "onebot.v11", "get_status") is True
    assert facade.supports(event, "napcat.qq", "send_like") is False


@pytest.mark.asyncio
async def test_event_bound_client_invokes_only_registered_capability() -> None:
    execution = MagicMock()
    execution.invoke_platform_capability = AsyncMock(return_value="receipt")
    facade = OneBotCapability(execution)
    event = _event(
        payload={
            "post_type": "message",
            "self_id": 1,
            "message_type": "private",
            "user_id": 2,
            "message_id": 3,
            "message": "hello",
        }
    )

    onebot_event = facade.event(event)
    client = facade.for_event(event)

    assert isinstance(onebot_event, OneBotMessageEvent)
    assert client is not None
    assert facade.supports(event, "onebot.v11", "delete") is True
    assert facade.supports(event, "napcat.qq", "send_like") is True
    assert hasattr(client, "call_action") is False

    result = await client.messages.delete(message_id=3)

    assert result == "receipt"
    execution.invoke_platform_capability.assert_awaited_once_with(
        "napcat-main", "onebot.v11", "delete", message_id=3
    )


@pytest.mark.asyncio
async def test_platform_manager_validates_capability_and_action_registry() -> None:
    manager = PlatformManager.__new__(PlatformManager)
    provider = AsyncMock(return_value="ok")
    manager._find_inst_by_id = MagicMock(
        return_value=SimpleNamespace(invoke_capability=provider)
    )

    async def run_without_limit(_platform_id: str, operation):
        return await operation()

    manager.run_with_platform_limit = run_without_limit

    assert (
        await manager.invoke_capability("napcat-main", "onebot.v11", "get_status")
        == "ok"
    )
    provider.assert_awaited_once_with("onebot.v11", "get_status")

    with pytest.raises(OneBotActionUnavailable):
        await manager.invoke_capability("napcat-main", "onebot.v11", "raw_call")

    with pytest.raises(OneBotActionUnavailable):
        await manager.invoke_capability("napcat-main", "napcat.qq", "get_status")

    manager._find_inst_by_id.return_value = None
    with pytest.raises(OneBotCapabilityUnavailable):
        await manager.invoke_capability("missing", "onebot.v11", "get_status")


def _make_adapter() -> NapCatPlatformAdapter:
    return NapCatPlatformAdapter(
        {
            "id": "napcat-test",
            "ws_url": "ws://127.0.0.1:3001",
            "timeout_seconds": 5,
        },
        {},
        asyncio.Queue(),
    )


@pytest.mark.asyncio
async def test_napcat_capability_mapping_normalizes_wire_parameters() -> None:
    adapter = _make_adapter()
    adapter.client.call_action = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )

    result = await adapter.invoke_capability(
        "onebot.v11",
        "set_group_ban",
        group_id=123,
        user_id=456,
        duration=2,
    )

    assert isinstance(result, OneBotActionResult)
    adapter.client.call_action.assert_awaited_once_with(
        "set_group_ban",
        group_id="123",
        user_id="456",
        duration=2.0,
    )


def test_napcat_results_are_converted_to_stable_dtos() -> None:
    adapter = _make_adapter()

    receipt = adapter._to_onebot_result(
        "send_group", NapCatSendMessageResult(message_id=9)
    )
    login = adapter._to_onebot_result(
        "get_login_info", NapCatLoginInfo(user_id=10, nickname="bot")
    )
    status = adapter._to_onebot_result(
        "get_status", NapCatStatus(online=True, good=True)
    )
    version = adapter._to_onebot_result(
        "get_version_info",
        NapCatVersionInfo(app_name="NapCat", app_version="1", protocol_version="11"),
    )

    assert receipt.message_id == "9"
    assert login.data["user_id"] == "10"
    assert status.data["online"] is True
    assert version.data["protocol_version"] == "11"


@pytest.mark.asyncio
async def test_napcat_capability_errors_are_stable_and_redacted() -> None:
    adapter = _make_adapter()
    adapter.client.call_action = AsyncMock(
        side_effect=NapCatApiError(
            "set_group_ban",
            status="failed",
            retcode=100,
            message="Bearer secret-token at ws://private.example",
            wording=None,
        )
    )

    with pytest.raises(OneBotActionRejected) as raised:
        await adapter.invoke_capability(
            "onebot.v11", "set_group_ban", group_id=1, user_id=2
        )

    assert raised.value.message == "OneBot action was rejected"
    assert "secret-token" not in str(raised.value)
    assert "private.example" not in str(raised.value)

    adapter.client.call_action.side_effect = NapCatTransportError(
        "set_group_ban", "timed out waiting for response"
    )
    with pytest.raises(OneBotActionTimeout):
        await adapter.invoke_capability(
            "onebot.v11", "set_group_ban", group_id=1, user_id=2
        )

    adapter.client.call_action.side_effect = NapCatTransportError(
        "set_group_ban", "connection closed"
    )
    with pytest.raises(OneBotTransportError):
        await adapter.invoke_capability(
            "onebot.v11", "set_group_ban", group_id=1, user_id=2
        )

    with pytest.raises(OneBotActionValidationError):
        await adapter.invoke_capability(
            "unknown", "set_group_ban", group_id=1, user_id=2
        )


@pytest.mark.asyncio
async def test_forward_action_cancellation_removes_pending_echo() -> None:
    adapter = _make_adapter()
    sent = asyncio.Event()

    class Socket:
        async def send(self, _payload: str) -> None:
            sent.set()

    adapter.client._socket = Socket()
    adapter.client._connected_event.set()
    task = asyncio.create_task(adapter.client.call_action("get_status"))
    await sent.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert adapter.client._pending == {}


@pytest.mark.asyncio
async def test_inbound_dispatch_keeps_unknown_wire_fields() -> None:
    received: list[object] = []

    async def on_event(event: object) -> None:
        received.append(event)

    payload = {
        "post_type": "notice",
        "self_id": 1,
        "time": 10,
        "notice_type": "future_notice",
        "future_field": {"preserved": True},
    }
    assert await dispatch_inbound_event(
        payload,
        on_event,
        started_at=0,
        validation_slow_log_threshold_s=999,
        payload_handle_slow_log_threshold_s=999,
    )

    assert len(received) == 1
    assert getattr(received[0], "__astrbot_raw_payload__")["future_field"] == {
        "preserved": True
    }
