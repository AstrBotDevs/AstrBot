import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import dingtalk_stream
import pytest
import requests
from wechatpy.enterprise import WeChatClient

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Plain, Reply
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import event_context
from astrbot.core.platform.sources.dingtalk import dingtalk_adapter
from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
    DingtalkPlatformAdapter,
)
from astrbot.core.platform.sources.dingtalk.dingtalk_event import DingtalkMessageEvent
from astrbot.core.platform.sources.wecom.wecom_adapter import WecomPlatformAdapter
from astrbot.core.platform.sources.wecom.wecom_event import WecomPlatformEvent
from astrbot.core.platform.sources.wecom.wecom_kf_message import WeChatKFMessage
from astrbot.core.star.context import Context


@pytest.fixture
def platform_sender(request, monkeypatch):
    """Use real adapters and SDK parsing with only HTTP and storage controlled."""
    name = request.param
    requests_sent = []
    results = []
    monkeypatch.setattr("astrbot.core.platform.platform.Metric.upload", AsyncMock())

    if name == "dingtalk":

        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def raise_for_status(self):
                pass

            async def text(self):
                return "{}"

            async def json(self):
                result = (
                    results.pop(0)
                    if results
                    else {"processQueryKey": f"tracking-{len(requests_sent)}"}
                )
                if isinstance(result, Exception):
                    raise result
                return result

        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def post(self, url, **kwargs):
                requests_sent.append((url, kwargs["json"]))
                return Response()

        monkeypatch.setattr(dingtalk_adapter.aiohttp, "ClientSession", Session)
        adapter = object.__new__(DingtalkPlatformAdapter)
        adapter.client_id = "example-robot"
        adapter.get_access_token = AsyncMock(return_value="example-token")
        adapter._get_sender_staff_id = AsyncMock(return_value="alice")
    else:

        def request_http(_session, method, url, **kwargs):
            requests_sent.append((url, json.loads(kwargs["data"])))
            result = (
                results.pop(0)
                if results
                else {"errcode": 0, "msgid": f"message-{len(requests_sent)}"}
            )
            if isinstance(result, Exception):
                raise result
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(result).encode()
            return response

        monkeypatch.setattr(requests.Session, "request", request_http)
        adapter = object.__new__(WecomPlatformAdapter)
        adapter.agent_id = "100001"
        adapter.client = WeChatClient(
            "example-corp",
            "example-secret",
            access_token="example-token",
            auto_retry=False,
        )

    adapter.config = {"id": "platform"}
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "100001"
    message.session_id = "alice"
    message.sender = MessageMember("alice", "Alice")
    message.message_id = "incoming-message"
    message.message = []
    message.message_str = ""
    message.raw_message = (
        dingtalk_stream.ChatbotMessage.from_dict(
            {"conversationType": "1", "senderId": "sender", "senderStaffId": "alice"}
        )
        if name == "dingtalk"
        else {}
    )
    event = (
        DingtalkMessageEvent("", message, adapter.meta(), "alice", adapter=adapter)
        if name == "dingtalk"
        else WecomPlatformEvent("", message, adapter.meta(), "alice", adapter.client)
    )
    context = Context.__new__(Context)
    context.platform_manager = SimpleNamespace(platform_insts=[adapter])
    context.get_config = lambda **kwargs: {
        "provider_ltm_settings": {"group_message_history_enable": True}
    }
    context.message_history_manager = SimpleNamespace(insert_message_chain=AsyncMock())
    return SimpleNamespace(
        name=name,
        adapter=adapter,
        event=event,
        context=context,
        sent=requests_sent,
        results=results,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["dingtalk", "wecom"], indirect=True)
@pytest.mark.parametrize("route", ["event", "context", "legacy_context"])
async def test_text_receipt_uses_original_public_send_once(platform_sender, route):
    sender = platform_sender
    chain = MessageChain([Plain("Hello")])
    if route == "event":
        receipt = await sender.event.send(chain)
    else:
        method = (
            sender.context.send_message
            if route == "legacy_context"
            else (sender.context.send_message_with_receipt)
        )
        receipt = await method("platform:FriendMessage:alice", chain)
    assert len(sender.sent) == 1
    if route == "legacy_context":
        assert receipt is True
    else:
        assert receipt is not None
        from astrbot.api.platform import MessageSendReceipt

        assert isinstance(receipt, MessageSendReceipt)
        assert receipt.message_ids == (("message-1",) if sender.name == "wecom" else ())
        assert receipt.tracking_keys == (
            ("tracking-1",) if sender.name == "dingtalk" else ()
        )
    payload = sender.sent[0][1]
    assert payload.get("touser", payload.get("userIds")) in ("alice", ["alice"])


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["dingtalk", "wecom"], indirect=True)
async def test_partial_text_failure_propagates_without_resending(platform_sender):
    sender = platform_sender
    sender.results.extend(
        [
            {"processQueryKey": "first"}
            if sender.name == "dingtalk"
            else {"errcode": 0},
            RuntimeError("second request failed"),
        ]
    )
    with pytest.raises(RuntimeError, match="second request failed"):
        await sender.context.send_message_with_receipt(
            "platform:FriendMessage:alice",
            MessageChain([Plain("First"), Plain("Second"), Plain("Third")]),
        )
    assert len(sender.sent) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["dingtalk", "wecom"], indirect=True)
@pytest.mark.parametrize(
    "parts",
    [
        [],
        [Reply(id="parent")],
        [Reply(id="parent"), Plain("Hi")],
        [Plain("Hi"), At(qq="bob")],
    ],
)
async def test_unconfirmed_content_does_not_get_receipt(platform_sender, parts):
    assert await platform_sender.event.send(MessageChain(parts)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, True, {"message_id": "legacy"}])
async def test_context_preserves_unknown_legacy_results(result):
    platform = SimpleNamespace(
        meta=lambda: PlatformMetadata("legacy", "Legacy", "platform"),
        send_by_session=AsyncMock(return_value=result),
    )
    context = Context.__new__(Context)
    context.platform_manager = SimpleNamespace(platform_insts=[platform])
    context.get_config = lambda **kwargs: {}
    chain = MessageChain([Plain("Hello")])
    assert (
        await context.send_message_with_receipt("platform:FriendMessage:alice", chain)
        is None
    )
    platform.send_by_session.assert_awaited_once()
    assert await context.send_message("platform:FriendMessage:alice", chain) is True
    context.platform_manager.platform_insts.clear()
    assert (
        await context.send_message_with_receipt("missing:FriendMessage:alice", chain)
        is False
    )
    assert await context.send_message("missing:FriendMessage:alice", chain) is False
    assert platform.send_by_session.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["dingtalk"], indirect=True)
async def test_receipt_context_preserves_trace_and_group_history(platform_sender):
    sender = platform_sender
    sender.event.trace = MagicMock()
    chain = MessageChain([Plain("Group reply")])
    with event_context(sender.event):
        receipt = await sender.context.send_message_with_receipt(
            "platform:GroupMessage:conversation", chain
        )
    assert receipt.tracking_keys == ("tracking-1",)
    assert sender.sent[0][1]["openConversationId"] == "conversation"
    sent_traces = [
        c
        for c in sender.event.trace.record.call_args_list
        if c.args[0] == "response_sent"
    ]
    assert len(sent_traces) == 1
    assert sent_traces[0].kwargs["target_umo"] == "platform:GroupMessage:conversation"
    sender.context.message_history_manager.insert_message_chain.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["dingtalk"], indirect=True)
@pytest.mark.parametrize(
    "key", ["filteredStaffIdList", "flowControlledStaffIdList", "invalidStaffIdList"]
)
async def test_dingtalk_rejected_recipient_raises(platform_sender, key):
    platform_sender.results.append({"processQueryKey": "tracked", key: ["alice"]})
    with pytest.raises(RuntimeError, match="recipient"):
        await platform_sender.event.send(MessageChain([Plain("Hello")]))
    assert len(platform_sender.sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["dingtalk"], indirect=True)
async def test_dingtalk_missing_staff_mapping_does_not_change_recipient(
    platform_sender,
):
    platform_sender.adapter._get_sender_staff_id.return_value = ""
    with pytest.raises(RuntimeError, match="staff_id"):
        await platform_sender.context.send_message_with_receipt(
            "platform:FriendMessage:sender", MessageChain([Plain("Hello")])
        )
    assert platform_sender.sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["wecom"], indirect=True)
@pytest.mark.parametrize("key", ["invaliduser", "unlicenseduser"])
async def test_wecom_rejected_recipient_raises(platform_sender, key):
    platform_sender.event.message_obj.session_id = "Alice"
    platform_sender.results.append({"errcode": 0, "msgid": "id", key: "alice"})
    with pytest.raises(RuntimeError, match="recipient"):
        await platform_sender.event.send(MessageChain([Plain("Hello")]))
    assert len(platform_sender.sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["wecom"], indirect=True)
@pytest.mark.parametrize("recipient", ["alice|bob", "@all"])
async def test_wecom_batch_and_broadcast_keep_unknown_receipt(
    platform_sender, recipient
):
    platform_sender.results.append({"errcode": 0, "invaliduser": "bob"})
    assert (
        await platform_sender.context.send_message_with_receipt(
            f"platform:FriendMessage:{recipient}", MessageChain([Plain("Hello")])
        )
        is None
    )
    assert platform_sender.sent[0][1]["touser"] == recipient


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["wecom"], indirect=True)
async def test_wecom_customer_service_has_no_application_receipt(platform_sender):
    kf = MagicMock(spec=WeChatKFMessage)
    platform_sender.adapter.client.kf_message = kf
    assert await platform_sender.event.send(MessageChain([Plain("Hello")])) is None
    kf.send_text.assert_called_once()
    assert platform_sender.sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_sender", ["dingtalk"], indirect=True)
async def test_dingtalk_token_fallback_reads_top_level_access_token(platform_sender):
    sender = platform_sender
    sender.adapter.client_secret = "example-secret"
    sender.adapter.client_ = SimpleNamespace(get_access_token=lambda: None)
    sender.results.append({"accessToken": "fallback-token", "expireIn": 7200})

    assert (
        await DingtalkPlatformAdapter.get_access_token(sender.adapter)
        == "fallback-token"
    )
    assert len(sender.sent) == 1
    assert sender.sent[0][0].endswith("/v1.0/oauth2/accessToken")
