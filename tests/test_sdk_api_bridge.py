from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = PROJECT_ROOT / "astrbot-sdk" / "src"

if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))


def _public_names(module_name: str) -> set[str]:
    module = importlib.import_module(module_name)
    declared_exports = getattr(module, "__all__", None)
    if declared_exports is not None:
        return {str(name) for name in declared_exports}
    return {name for name in dir(module) if not name.startswith("_")}


def test_sdk_namespaced_api_bridge_matches_astrbot_api_exports() -> None:
    from astrbot_sdk.api import llm_tool as sdk_llm_tool
    from astrbot_sdk.api import star as sdk_star_module

    from astrbot.api import llm_tool as api_llm_tool
    from astrbot.api.star import Context as ApiContext

    assert sdk_llm_tool is api_llm_tool
    assert sdk_star_module.Context is ApiContext

    module_pairs = {
        "astrbot.api": "astrbot_sdk.api",
        "astrbot.api.all": "astrbot_sdk.api.all",
        "astrbot.api.event": "astrbot_sdk.api.event",
        "astrbot.api.event.filter": "astrbot_sdk.api.event.filter",
        "astrbot.api.message_components": "astrbot_sdk.api.message_components",
        "astrbot.api.platform": "astrbot_sdk.api.platform",
        "astrbot.api.provider": "astrbot_sdk.api.provider",
        "astrbot.api.star": "astrbot_sdk.api.star",
        "astrbot.api.util": "astrbot_sdk.api.util",
    }

    for api_module_name, sdk_module_name in module_pairs.items():
        api_module = importlib.import_module(api_module_name)
        sdk_module = importlib.import_module(sdk_module_name)
        api_names = _public_names(api_module_name)

        assert api_names <= _public_names(sdk_module_name)
        for name in api_names:
            assert getattr(sdk_module, name) is getattr(api_module, name)


def test_sdk_top_level_api_mirrors_do_not_replace_native_sdk_design() -> None:
    import astrbot_sdk
    from astrbot_sdk.context import Context as NativeContext
    from astrbot_sdk.star import Star as NativeStar

    from astrbot.api.star import Context as ApiContext
    from astrbot.api.star import Star as ApiStar

    mirror_pairs = {
        "astrbot.api.all": "astrbot_sdk.all",
        "astrbot.api.event": "astrbot_sdk.event",
        "astrbot.api.event.filter": "astrbot_sdk.event.filter",
        "astrbot.api.platform": "astrbot_sdk.platform",
        "astrbot.api.provider": "astrbot_sdk.provider",
        "astrbot.api.util": "astrbot_sdk.util",
    }

    for api_module_name, sdk_module_name in mirror_pairs.items():
        api_module = importlib.import_module(api_module_name)
        sdk_module = importlib.import_module(sdk_module_name)
        for name in _public_names(api_module_name):
            assert getattr(sdk_module, name) is getattr(api_module, name)

    assert astrbot_sdk.Context is NativeContext
    assert astrbot_sdk.Star is NativeStar
    assert astrbot_sdk.Context is not ApiContext
    assert astrbot_sdk.Star is not ApiStar


def test_sdk_source_does_not_import_astrbot_core_directly() -> None:
    offenders = []
    for source_path in (SDK_SRC / "astrbot_sdk").rglob("*.py"):
        text = source_path.read_text(encoding="utf-8")
        if "from astrbot.core" in text or "import astrbot.core" in text:
            offenders.append(source_path.relative_to(SDK_SRC).as_posix())

    assert not offenders


def test_sdk_native_protocol_runtime_clients_and_testing_remain_available() -> None:
    from astrbot_sdk.clients import DBClient, LLMClient, PlatformClient
    from astrbot_sdk.context import CancelToken
    from astrbot_sdk.message.components import Plain
    from astrbot_sdk.protocol import (
        InitializeMessage,
        JsonProtocolCodec,
        MsgpackProtocolCodec,
        PeerInfo,
        parse_message,
    )
    from astrbot_sdk.runtime import CapabilityRouter, Peer, StreamExecution, Transport
    from astrbot_sdk.testing import MockPeer, PluginHarness

    assert DBClient.__name__ == "DBClient"
    assert LLMClient.__name__ == "LLMClient"
    assert PlatformClient.__name__ == "PlatformClient"
    assert Peer.__name__ == "Peer"
    assert Transport.__name__ == "Transport"
    assert CapabilityRouter.__name__ == "CapabilityRouter"
    assert StreamExecution.__name__ == "StreamExecution"
    assert MockPeer.__name__ == "MockPeer"
    assert PluginHarness.__name__ == "PluginHarness"

    token = CancelToken()
    assert not token.cancelled
    token.cancel()
    assert token.cancelled

    assert Plain("hello").toDict() == {"type": "text", "data": {"text": "hello"}}

    message = InitializeMessage(
        id="init-1",
        protocol_version="1.0",
        peer=PeerInfo(name="plugin", role="plugin", version="1.0.0"),
    )
    for codec in (JsonProtocolCodec(), MsgpackProtocolCodec()):
        decoded = codec.decode_message(codec.encode_message(message))
        assert decoded == message

    assert parse_message(message.model_dump()) == message


def test_sdk_builtin_capability_schemas_match_runtime_registrations() -> None:
    from astrbot_sdk.protocol import BUILTIN_CAPABILITY_SCHEMAS
    from astrbot_sdk.runtime import CapabilityRouter

    router = CapabilityRouter()
    registered_names = set(getattr(router, "_registrations"))
    schema_names = set(BUILTIN_CAPABILITY_SCHEMAS)

    assert registered_names <= schema_names
    assert schema_names <= registered_names


@pytest.mark.asyncio
async def test_sdk_peer_can_handshake_and_invoke_over_bidirectional_transport() -> None:
    from astrbot_sdk.protocol import InitializeOutput, JsonProtocolCodec, PeerInfo
    from astrbot_sdk.runtime import Peer, Transport

    class MemoryTransport(Transport):
        def __init__(self) -> None:
            super().__init__()
            self.remote: MemoryTransport | None = None

        async def start(self) -> None:
            self._closed.clear()

        async def stop(self) -> None:
            self._closed.set()

        async def send(self, payload: bytes) -> None:
            assert self.remote is not None
            await self.remote._dispatch(payload)

    client_transport = MemoryTransport()
    server_transport = MemoryTransport()
    client_transport.remote = server_transport
    server_transport.remote = client_transport

    client = Peer(
        transport=client_transport,
        peer_info=PeerInfo(name="client-plugin", role="plugin"),
        wire_codec=JsonProtocolCodec(),
    )
    server = Peer(
        transport=server_transport,
        peer_info=PeerInfo(name="astrbot-core", role="core"),
        wire_codec=JsonProtocolCodec(),
    )

    async def initialize_handler(_message):
        return InitializeOutput(
            peer=server.peer_info,
            protocol_version="1.0",
            metadata={"wire_codec": "json"},
        )

    async def invoke_handler(message, cancel_token):
        cancel_token.raise_if_cancelled()
        return {"capability": message.capability, "input": message.input}

    server.set_initialize_handler(initialize_handler)
    server.set_invoke_handler(invoke_handler)

    await client.start()
    await server.start()
    try:
        output = await client.initialize([])
        assert output.peer is server.peer_info or output.peer == server.peer_info
        assert client.remote_peer == server.peer_info
        assert server.remote_peer == client.peer_info

        result = await client.invoke("demo.echo", {"text": "hello"})
        assert result == {"capability": "demo.echo", "input": {"text": "hello"}}
    finally:
        await client.stop()
        await server.stop()
