from __future__ import annotations

import unittest
from unittest.mock import patch

from astrbot_sdk import MessageEvent, Star, on_command
from astrbot_sdk._legacy_api import (
    CommandComponent,
    MIGRATION_DOC_URL,
    LegacyContext,
    _warned_methods,
)
from astrbot_sdk.clients._proxy import CapabilityProxy
from astrbot_sdk.clients.memory import MemoryClient


class _DummyPeer:
    def __init__(self) -> None:
        self.remote_capability_map = {}
        self.calls: list[tuple[str, dict]] = []

    async def invoke(self, name: str, payload: dict, *, stream: bool = False) -> dict:
        self.calls.append((name, payload))
        return {}


class _HandlerPlugin(Star):
    @on_command("ping")
    async def ping(self, event: MessageEvent) -> None:
        return None


class ApiContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_star_lifecycle_hooks_exist(self) -> None:
        star = Star()
        self.assertIsNone(await star.on_start())
        self.assertIsNone(await star.on_stop())

    async def test_star_materializes_class_level_handlers(self) -> None:
        self.assertEqual(_HandlerPlugin.__handlers__, ("ping",))

    async def test_command_component_is_compat_star_subclass(self) -> None:
        self.assertTrue(issubclass(CommandComponent, Star))
        self.assertFalse(CommandComponent.__astrbot_is_new_star__())

    async def test_message_event_reply_uses_bound_reply_handler(self) -> None:
        sent: list[str] = []
        event = MessageEvent(text="hello", session_id="session-1")
        event.bind_reply_handler(lambda text: _collect_reply(sent, text))

        await event.reply("pong")

        self.assertEqual(sent, ["pong"])

    async def test_memory_client_save_accepts_expanded_keyword_payload(self) -> None:
        peer = _DummyPeer()
        client = MemoryClient(CapabilityProxy(peer))

        await client.save("memory-key", foo="bar", score=3)

        self.assertEqual(
            peer.calls,
            [
                (
                    "memory.save",
                    {
                        "key": "memory-key",
                        "value": {"foo": "bar", "score": 3},
                    },
                )
            ],
        )

    async def test_compat_warning_includes_migration_doc_url(self) -> None:
        _warned_methods.clear()
        legacy_context = LegacyContext("compat-plugin")
        with patch("astrbot_sdk._legacy_api.logger.warning") as warning:
            await legacy_context.add_llm_tools()

        warning.assert_called_once()
        self.assertEqual(warning.call_args.args[-1], MIGRATION_DOC_URL)

    async def test_compat_llm_generate_warning_matches_chat_raw_mapping(self) -> None:
        class _DummyLLM:
            async def chat_raw(self, *args, **kwargs):
                return {}

        class _DummyRuntimeContext:
            llm = _DummyLLM()

        _warned_methods.clear()
        legacy_context = LegacyContext("compat-plugin")
        legacy_context.bind_runtime_context(_DummyRuntimeContext())
        with patch("astrbot_sdk._legacy_api.logger.warning") as warning:
            await legacy_context.llm_generate("provider-1", prompt="hi")

        warning.assert_called_once()
        self.assertEqual(warning.call_args.args[2], "ctx.llm.chat_raw(...)")


async def _collect_reply(sent: list[str], text: str) -> None:
    sent.append(text)


if __name__ == "__main__":
    unittest.main()
