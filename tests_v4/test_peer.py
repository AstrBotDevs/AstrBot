from __future__ import annotations

import asyncio
import unittest

from astrbot_sdk.context import CancelToken
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.protocol.descriptors import CapabilityDescriptor
from astrbot_sdk.protocol.messages import EventMessage, InitializeOutput, PeerInfo, ResultMessage
from astrbot_sdk.runtime.capability_router import CapabilityRouter, StreamExecution
from astrbot_sdk.runtime.peer import Peer
from astrbot_sdk.runtime.transport import WebSocketClientTransport, WebSocketServerTransport

from tests_v4.helpers import make_transport_pair


class PeerRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.left, self.right = make_transport_pair()

    async def test_initialize_and_call_builtin_capabilities(self) -> None:
        router = CapabilityRouter()
        core = Peer(
            transport=self.left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(0, result=InitializeOutput(
                peer=PeerInfo(name="core", role="core", version="v4"),
                capabilities=router.descriptors(),
                metadata={},
            ))
        )
        core.set_invoke_handler(
            lambda message, token: router.execute(
                message.capability,
                message.input,
                stream=message.stream,
                cancel_token=token,
                request_id=message.id,
            )
        )

        plugin = Peer(
            transport=self.right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await core.start()
        await plugin.start()
        await plugin.initialize([])

        result = await plugin.invoke("llm.chat", {"prompt": "hello"})
        self.assertEqual(result["text"], "Echo: hello")

        stream = await plugin.invoke_stream("llm.stream_chat", {"prompt": "hi"})
        chunks = [event.data["text"] async for event in stream]
        self.assertEqual("".join(chunks), "Echo: hi")

        await plugin.stop()
        await core.stop()

    async def test_stream_false_receiving_event_is_protocol_error(self) -> None:
        plugin = Peer(
            transport=self.right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )
        await self.left.start()
        await plugin.start()

        task = asyncio.create_task(
            plugin.invoke("llm.chat", {"prompt": "bad"}, request_id="req-1")
        )
        await asyncio.sleep(0)
        await self.left.send(EventMessage(id="req-1", phase="started").model_dump_json())

        with self.assertRaises(AstrBotError) as raised:
            await task
        self.assertEqual(raised.exception.code, "protocol_error")
        await plugin.stop()
        await self.left.stop()

    async def test_stream_true_receiving_result_is_protocol_error(self) -> None:
        plugin = Peer(
            transport=self.right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )
        await self.left.start()
        await plugin.start()

        stream = await plugin.invoke_stream("llm.stream_chat", {"prompt": "bad"}, request_id="stream-1")
        await self.left.send(ResultMessage(id="stream-1", success=True, output={}).model_dump_json())

        with self.assertRaises(AstrBotError) as raised:
            async for _ in stream:
                pass
        self.assertEqual(raised.exception.code, "protocol_error")
        await plugin.stop()
        await self.left.stop()

    async def test_cancel_waits_for_failed_terminal_event(self) -> None:
        descriptor = CapabilityDescriptor(
            name="slow.stream",
            description="slow stream",
            input_schema={"type": "object", "properties": {}, "required": []},
            output_schema={"type": "object", "properties": {"count": {"type": "number"}}, "required": ["count"]},
            supports_stream=True,
            cancelable=True,
        )

        async def init_handler(_message):
            return InitializeOutput(
                peer=PeerInfo(name="core", role="core", version="v4"),
                capabilities=[descriptor],
                metadata={},
            )

        async def invoke_handler(message, token: CancelToken):
            async def iterator():
                while True:
                    token.raise_if_cancelled()
                    await asyncio.sleep(0.01)
                    yield {"text": "x"}

            return StreamExecution(
                iterator=iterator(),
                finalize=lambda chunks: {"count": len(chunks)},
            )

        core = Peer(
            transport=self.left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )
        core.set_initialize_handler(init_handler)
        core.set_invoke_handler(invoke_handler)
        plugin = Peer(
            transport=self.right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await core.start()
        await plugin.start()
        await plugin.initialize([])

        stream = await plugin.invoke_stream("slow.stream", {}, request_id="cancel-1")
        first = await anext(stream)
        self.assertEqual(first.data["text"], "x")
        await plugin.cancel("cancel-1")

        with self.assertRaises(AstrBotError) as raised:
            await anext(stream)
        self.assertEqual(raised.exception.code, "cancelled")
        await plugin.stop()
        await core.stop()

    async def test_websocket_transport_smoke(self) -> None:
        router = CapabilityRouter()
        server_transport = WebSocketServerTransport(port=0)
        core = Peer(
            transport=server_transport,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(0, result=InitializeOutput(
                peer=PeerInfo(name="core", role="core", version="v4"),
                capabilities=router.descriptors(),
                metadata={},
            ))
        )
        core.set_invoke_handler(
            lambda message, token: router.execute(
                message.capability,
                message.input,
                stream=message.stream,
                cancel_token=token,
                request_id=message.id,
            )
        )

        await core.start()
        client_transport = WebSocketClientTransport(url=server_transport.url)
        plugin = Peer(
            transport=client_transport,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )
        await plugin.start()
        await plugin.initialize([])
        result = await plugin.invoke("llm.chat", {"prompt": "ws"})
        self.assertEqual(result["text"], "Echo: ws")
        await plugin.stop()
        await core.stop()

    async def test_initialize_failure_closes_receiver_connection(self) -> None:
        core = Peer(
            transport=self.left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
            protocol_version="1.0",
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="core", role="core", version="v4"),
                    capabilities=[],
                    metadata={},
                ),
            )
        )
        plugin = Peer(
            transport=self.right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
            protocol_version="2.0",
        )

        await core.start()
        await plugin.start()

        with self.assertRaises(AstrBotError) as raised:
            await plugin.initialize([])
        self.assertEqual(raised.exception.code, "protocol_version_mismatch")

        await asyncio.wait_for(core.wait_closed(), timeout=1.0)
        await asyncio.wait_for(plugin.wait_closed(), timeout=1.0)
        self.assertTrue(core._closed)
        self.assertTrue(plugin._closed)


class CapabilityRouterContractTest(unittest.TestCase):
    def test_capability_names_must_match_namespace_method_format(self) -> None:
        router = CapabilityRouter()
        for name in ("llm", "llm.chat.extra", "LLM.chat", "llm.Chat"):
            with self.assertRaises(ValueError) as raised:
                router.register(
                    CapabilityDescriptor(
                        name=name,
                        description="invalid",
                    )
                )
            self.assertIn(name, str(raised.exception))

    def test_reserved_capability_namespaces_are_rejected_for_exposed_registrations(self) -> None:
        router = CapabilityRouter()
        for name in ("handler.demo", "system.health", "internal.trace"):
            with self.assertRaises(ValueError) as raised:
                router.register(
                    CapabilityDescriptor(
                        name=name,
                        description="reserved",
                    )
                )
            self.assertIn(name, str(raised.exception))

    def test_reserved_capability_namespaces_remain_available_for_hidden_internal_registrations(self) -> None:
        router = CapabilityRouter()
        router.register(
            CapabilityDescriptor(
                name="system.health",
                description="internal only",
            ),
            exposed=False,
        )

        self.assertNotIn("system.health", [item.name for item in router.descriptors()])
