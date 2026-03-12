from __future__ import annotations

import unittest

from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    HandlerDescriptor,
    ScheduleTrigger,
)
from astrbot_sdk.protocol.messages import (
    CancelMessage,
    EventMessage,
    InitializeMessage,
    InvokeMessage,
    PeerInfo,
    ResultMessage,
    parse_message,
)


class ProtocolModelsTest(unittest.TestCase):
    def test_parse_message_roundtrip(self) -> None:
        message = InitializeMessage(
            id="msg_001",
            protocol_version="1.0",
            peer=PeerInfo(name="plugin", role="plugin", version="1.0.0"),
            handlers=[
                HandlerDescriptor(
                    id="handler_1",
                    trigger=CommandTrigger(command="hello"),
                )
            ],
            metadata={"a": 1},
        )
        parsed = parse_message(message.model_dump_json())
        self.assertEqual(parsed.id, "msg_001")
        self.assertEqual(parsed.peer.name, "plugin")

        for sample in [
            InvokeMessage(id="msg_002", capability="llm.chat", input={"prompt": "hi"}),
            ResultMessage(id="msg_002", success=True, output={"text": "ok"}),
            EventMessage(id="msg_003", phase="started"),
            CancelMessage(id="msg_003"),
        ]:
            self.assertEqual(parse_message(sample.model_dump()).type, sample.type)

    def test_schedule_trigger_requires_exactly_one_strategy(self) -> None:
        with self.assertRaises(ValueError):
            ScheduleTrigger()
        with self.assertRaises(ValueError):
            ScheduleTrigger(cron="* * * * *", interval_seconds=10)
        trigger = ScheduleTrigger(interval_seconds=30)
        self.assertEqual(trigger.interval_seconds, 30)
