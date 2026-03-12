from __future__ import annotations

import unittest
from unittest.mock import patch

from astrbot_sdk._legacy_api import MIGRATION_DOC_URL, LegacyContext, _warned_methods
from astrbot_sdk.clients._proxy import CapabilityProxy
from astrbot_sdk.clients.memory import MemoryClient
from astrbot_sdk.star import Star


class _DummyPeer:
    def __init__(self) -> None:
        self.remote_capability_map = {}
        self.calls: list[tuple[str, dict]] = []

    async def invoke(self, name: str, payload: dict, *, stream: bool = False) -> dict:
        self.calls.append((name, payload))
        return {}


class ApiContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_star_lifecycle_hooks_exist(self) -> None:
        star = Star()
        self.assertIsNone(await star.on_start())
        self.assertIsNone(await star.on_stop())

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


if __name__ == "__main__":
    unittest.main()
