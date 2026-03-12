from __future__ import annotations

import unittest

from astrbot_sdk.protocol.descriptors import CommandTrigger, HandlerDescriptor
from astrbot_sdk.protocol.legacy_adapter import (
    LEGACY_CONTEXT_CAPABILITY,
    LEGACY_HANDSHAKE_METADATA_KEY,
    LegacyAdapter,
)
from astrbot_sdk.protocol.messages import (
    EventMessage,
    InitializeMessage,
    PeerInfo,
    ResultMessage,
)


class LegacyAdapterTest(unittest.TestCase):
    def test_call_handler_roundtrip_preserves_handler_name_in_stream_notifications(
        self,
    ) -> None:
        adapter = LegacyAdapter()

        invoke = adapter.legacy_to_v4(
            {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "call_handler",
                "params": {
                    "handler_full_name": "commands.demo:MyPlugin.handle",
                    "event": {"text": "/hello"},
                    "args": {},
                },
            }
        )

        self.assertEqual(invoke.capability, "handler.invoke")
        self.assertEqual(invoke.input["handler_id"], "commands.demo:MyPlugin.handle")

        started = adapter.event_to_legacy_notification(
            EventMessage(id="call-1", phase="started")
        )
        delta = adapter.event_to_legacy_notification(
            EventMessage(id="call-1", phase="delta", data={"text": "hi"})
        )
        completed = adapter.event_to_legacy_notification(
            EventMessage(id="call-1", phase="completed", output={"text": "hi"})
        )
        response = adapter.result_to_legacy_response(
            ResultMessage(id="call-1", success=True, output={"handled_by": "demo"})
        )

        self.assertEqual(started["method"], "handler_stream_start")
        self.assertEqual(
            delta["params"]["handler_full_name"], "commands.demo:MyPlugin.handle"
        )
        self.assertEqual(delta["params"]["data"], {"text": "hi"})
        self.assertEqual(completed["method"], "handler_stream_end")
        self.assertEqual(response["result"], {"handled_by": "demo"})

    def test_call_context_function_maps_to_internal_capability(self) -> None:
        adapter = LegacyAdapter()
        message = adapter.legacy_to_v4(
            {
                "jsonrpc": "2.0",
                "id": "ctx-1",
                "method": "call_context_function",
                "params": {
                    "name": "ConversationManager.new_conversation",
                    "args": {"unified_msg_origin": "session-1"},
                },
            }
        )

        self.assertEqual(message.capability, LEGACY_CONTEXT_CAPABILITY)
        self.assertEqual(message.input["name"], "ConversationManager.new_conversation")
        self.assertEqual(
            message.input["args"],
            {"unified_msg_origin": "session-1"},
        )

        legacy_request = adapter.invoke_to_legacy_request(message)
        self.assertEqual(legacy_request["method"], "call_context_function")
        self.assertEqual(
            legacy_request["params"]["name"],
            "ConversationManager.new_conversation",
        )

    def test_legacy_handler_stream_notifications_map_back_to_v4_events(self) -> None:
        adapter = LegacyAdapter()

        started = adapter.legacy_to_v4(
            {
                "jsonrpc": "2.0",
                "method": "handler_stream_start",
                "params": {
                    "id": "call-2",
                    "handler_full_name": "commands.demo:MyPlugin.handle",
                },
            }
        )
        delta = adapter.legacy_to_v4(
            {
                "jsonrpc": "2.0",
                "method": "handler_stream_update",
                "params": {
                    "id": "call-2",
                    "handler_full_name": "commands.demo:MyPlugin.handle",
                    "data": {"text": "partial"},
                },
            }
        )
        failed = adapter.legacy_to_v4(
            {
                "jsonrpc": "2.0",
                "method": "handler_stream_end",
                "params": {
                    "id": "call-2",
                    "handler_full_name": "commands.demo:MyPlugin.handle",
                    "error": {
                        "code": "cancelled",
                        "message": "调用被取消",
                        "hint": "",
                        "retryable": False,
                    },
                },
            }
        )

        self.assertEqual(started.phase, "started")
        self.assertEqual(delta.phase, "delta")
        self.assertEqual(delta.data, {"text": "partial"})
        self.assertEqual(failed.phase, "failed")
        self.assertEqual(failed.error.code, "cancelled")

    def test_handshake_payload_maps_to_initialize_and_roundtrips(self) -> None:
        adapter = LegacyAdapter(legacy_peer_name="legacy-plugin")
        legacy_payload = {
            "plugin_one.main": {
                "name": "plugin_one",
                "author": "tester",
                "desc": "legacy",
                "version": "0.1.0",
                "repo": None,
                "module_path": "plugin_one.main",
                "root_dir_name": "plugin_one",
                "reserved": False,
                "activated": True,
                "config": None,
                "star_handler_full_names": [
                    "commands.plugin_one:SampleCommand.handle_plugin_one"
                ],
                "display_name": "plugin_one",
                "logo_path": None,
                "handlers": [
                    {
                        "event_type": 3,
                        "handler_full_name": "commands.plugin_one:SampleCommand.handle_plugin_one",
                        "handler_name": "handle_plugin_one",
                        "handler_module_path": "commands.plugin_one:SampleCommand",
                        "desc": "",
                        "extras_configs": {"priority": 7},
                    }
                ],
            }
        }

        initialize = adapter.legacy_to_v4(
            {
                "jsonrpc": "2.0",
                "id": "handshake-1",
                "result": legacy_payload,
            }
        )

        self.assertIsInstance(initialize, InitializeMessage)
        self.assertEqual(initialize.peer.name, "plugin_one")
        self.assertEqual(
            initialize.handlers[0].id,
            "commands.plugin_one:SampleCommand.handle_plugin_one",
        )
        self.assertEqual(initialize.handlers[0].priority, 7)
        self.assertEqual(
            initialize.metadata[LEGACY_HANDSHAKE_METADATA_KEY],
            legacy_payload,
        )

        roundtrip = adapter.initialize_to_legacy_handshake_response(
            initialize,
            request_id="handshake-1",
        )
        self.assertEqual(roundtrip["result"], legacy_payload)

    def test_handshake_error_becomes_initialize_failure(self) -> None:
        adapter = LegacyAdapter()
        adapter.legacy_to_v4(
            {
                "jsonrpc": "2.0",
                "id": "handshake-2",
                "method": "handshake",
                "params": {},
            }
        )

        result = adapter.legacy_to_v4(
            {
                "jsonrpc": "2.0",
                "id": "handshake-2",
                "error": {
                    "code": -32000,
                    "message": "boom",
                },
            }
        )

        self.assertIsInstance(result, ResultMessage)
        self.assertEqual(result.kind, "initialize_result")
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, "legacy_rpc_error")

    def test_initialize_can_synthesize_legacy_handshake_payload(self) -> None:
        adapter = LegacyAdapter()
        initialize = InitializeMessage(
            id="msg_001",
            protocol_version="1.0",
            peer=PeerInfo(name="v4-plugin", role="plugin", version="1.2.0"),
            handlers=[
                HandlerDescriptor(
                    id="commands.sample:MyPlugin.hello",
                    trigger=CommandTrigger(command="hello", description="hello"),
                    priority=3,
                )
            ],
            metadata={"plugin_id": "v4-plugin"},
        )

        payload = adapter.initialize_to_legacy_handshake_response(
            initialize,
            request_id="handshake-3",
        )
        star_payload = payload["result"]["v4-plugin.main"]

        self.assertEqual(star_payload["name"], "v4-plugin")
        self.assertEqual(
            star_payload["handlers"][0]["handler_full_name"],
            "commands.sample:MyPlugin.hello",
        )
        self.assertEqual(star_payload["handlers"][0]["extras_configs"]["priority"], 3)


if __name__ == "__main__":
    unittest.main()
