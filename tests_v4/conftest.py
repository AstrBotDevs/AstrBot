# Test configuration
import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

# 将 src-new 加入路径 - 这使得测试可以运行，但不算"已安装"
import sys
SRC_NEW_PATH = str(Path(__file__).parent.parent / "src-new")
sys.path.insert(0, SRC_NEW_PATH)


# ============================================================
# Async Configuration
# ============================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ============================================================
# Transport Fixtures
# ============================================================

class MemoryTransport:
    """In-memory transport for testing peer communication."""

    def __init__(self) -> None:
        self._closed = asyncio.Event()
        self._message_handler = None
        self.partner: MemoryTransport | None = None

    def set_message_handler(self, handler) -> None:
        self._message_handler = handler

    async def start(self) -> None:
        self._closed.clear()

    async def stop(self) -> None:
        self._closed.set()

    async def wait_closed(self) -> None:
        await self._closed.wait()

    async def send(self, payload: str) -> None:
        if self.partner is None:
            raise RuntimeError("MemoryTransport 未连接 partner")
        if self.partner._message_handler is not None:
            await self.partner._message_handler(payload)

    async def _dispatch(self, payload: str) -> None:
        if self._message_handler is not None:
            await self._message_handler(payload)


@pytest.fixture
def transport_pair() -> tuple[MemoryTransport, MemoryTransport]:
    """Create a connected pair of in-memory transports."""
    left = MemoryTransport()
    right = MemoryTransport()
    left.partner = right
    right.partner = left
    return left, right


# ============================================================
# Mock/Fake Fixtures
# ============================================================

class FakeEnvManager:
    """Fake environment manager for testing."""

    def prepare_environment(self, _plugin: Any) -> Path:
        return Path(sys.executable)


@pytest.fixture
def fake_env_manager() -> FakeEnvManager:
    """Provide a fake environment manager."""
    return FakeEnvManager()


# ============================================================
# Peer Fixtures
# ============================================================

from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.capability_router import CapabilityRouter
from astrbot_sdk.runtime.peer import Peer


@pytest.fixture
async def core_peer(transport_pair: tuple[MemoryTransport, MemoryTransport]) -> Peer:
    """Create a core peer with default handlers."""
    left, _ = transport_pair
    router = CapabilityRouter()

    peer = Peer(
        transport=left,
        peer_info=PeerInfo(name="core", role="core", version="v4"),
    )

    async def init_handler(_message) -> InitializeOutput:
        return InitializeOutput(
            peer=PeerInfo(name="core", role="core", version="v4"),
            capabilities=router.descriptors(),
            metadata={},
        )

    async def invoke_handler(message, token):
        return await router.execute(
            message.capability,
            message.input,
            stream=message.stream,
            cancel_token=token,
            request_id=message.id,
        )

    peer.set_initialize_handler(init_handler)
    peer.set_invoke_handler(invoke_handler)

    await peer.start()
    yield peer
    await peer.stop()


@pytest.fixture
async def plugin_peer(transport_pair: tuple[MemoryTransport, MemoryTransport]) -> Peer:
    """Create a plugin peer connected to core."""
    _, right = transport_pair

    peer = Peer(
        transport=right,
        peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
    )

    await peer.start()
    yield peer
    await peer.stop()


# ============================================================
# Temporary Plugin Fixtures
# ============================================================

import tempfile
import textwrap


@pytest.fixture
def temp_plugin_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for plugin testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


def create_test_plugin(plugin_root: Path, name: str = "test_plugin") -> None:
    """Helper to create a minimal test plugin."""
    (plugin_root / "commands").mkdir(parents=True, exist_ok=True)
    (plugin_root / "commands" / "__init__.py").write_text("", encoding="utf-8")
    (plugin_root / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_root / "plugin.yaml").write_text(
        textwrap.dedent(
            f"""\
            _schema_version: 2
            name: {name}
            display_name: Test Plugin
            desc: test
            author: tester
            version: 0.1.0
            runtime:
              python: "{sys.version_info.major}.{sys.version_info.minor}"
            components:
              - class: commands.sample:TestPlugin
                type: command
                name: test
                description: test command
            """
        ),
        encoding="utf-8",
    )
    (plugin_root / "commands" / "sample.py").write_text(
        textwrap.dedent(
            """\
            from astrbot_sdk import Context, MessageEvent, Star, on_command


            class TestPlugin(Star):
                @on_command("test")
                async def test_cmd(self, event: MessageEvent, ctx: Context):
                    await event.reply("test ok")
            """
        ),
        encoding="utf-8",
    )


@pytest.fixture
def test_plugin(temp_plugin_dir: Path) -> Path:
    """Create a test plugin and return its root directory."""
    plugin_root = temp_plugin_dir / "plugins" / "test_plugin"
    create_test_plugin(plugin_root)
    return temp_plugin_dir / "plugins"
