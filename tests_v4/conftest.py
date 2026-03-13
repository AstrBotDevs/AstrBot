"""Pytest共享的fixture和测试引导辅助函数。"""

# ruff: noqa: E402  # 忽略E402（模块导入顺序）警告

# 测试配置
import asyncio
import sys
import tempfile
import textwrap
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

# 将src-new目录添加到Python路径 - 这使得测试可以运行，但不算作"已安装"的包
SRC_NEW_PATH = str(Path(__file__).parent.parent / "src-new")
sys.path.insert(0, SRC_NEW_PATH)


# ============================================================
# 异步测试配置
# ============================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """为异步测试创建事件循环。

    这是一个会话级别的fixture，在整个测试会话期间只创建一次事件循环。
    """
    policy = asyncio.get_event_loop_policy()  # 获取当前事件循环策略
    loop = policy.new_event_loop()  # 创建新的事件循环
    yield loop  # 提供事件循环给测试使用
    loop.close()  # 测试结束后关闭事件循环


# ============================================================
# 传输层Fixture（用于模拟网络通信）
# ============================================================


class MemoryTransport:
    """用于测试对等通信的内存传输模拟。

    这个类模拟了两个对等方之间的通信通道，所有消息都在内存中传递，
    无需实际网络连接。
    """

    def __init__(self) -> None:
        self._closed = asyncio.Event()  # 用于跟踪传输是否已关闭
        self._message_handler = None  # 消息处理函数
        self.partner: MemoryTransport | None = None  # 通信伙伴

    def set_message_handler(self, handler) -> None:
        """设置消息处理函数。

        Args:
            handler: 接收消息的异步函数
        """
        self._message_handler = handler

    async def start(self) -> None:
        """启动传输。

        清除关闭状态，使传输可用。
        """
        self._closed.clear()

    async def stop(self) -> None:
        """停止传输。

        设置关闭事件，表示传输已停止。
        """
        self._closed.set()

    async def wait_closed(self) -> None:
        """等待传输关闭。

        阻塞直到传输完全关闭。
        """
        await self._closed.wait()

    async def send(self, payload: str) -> None:
        """发送消息给伙伴。

        Args:
            payload: 要发送的消息内容

        Raises:
            RuntimeError: 如果没有设置伙伴传输
        """
        if self.partner is None:
            raise RuntimeError("MemoryTransport 未连接 partner")
        if self.partner._message_handler is not None:
            await self.partner._message_handler(payload)  # 将消息分发给伙伴的处理函数

    async def _dispatch(self, payload: str) -> None:
        """内部方法：将消息分发给本地处理函数。

        Args:
            payload: 接收到的消息内容
        """
        if self._message_handler is not None:
            await self._message_handler(payload)


@pytest.fixture
def transport_pair() -> tuple[MemoryTransport, MemoryTransport]:
    """创建一对相互连接的内存传输实例。

    返回的左右两个传输实例互为伙伴，可用于模拟两个对等方之间的通信。

    Returns:
        (left_transport, right_transport) 的元组
    """
    left = MemoryTransport()
    right = MemoryTransport()
    left.partner = right  # 左传输的伙伴是右传输
    right.partner = left  # 右传输的伙伴是左传输
    return left, right


# ============================================================
# 模拟/Fake Fixture（用于测试的假对象）
# ============================================================


class FakeEnvManager:
    """用于测试的虚假环境管理器。

    模拟真实的环境管理器行为，但不执行实际的环境准备操作。
    """

    def prepare_environment(self, _plugin: Any) -> Path:
        """模拟准备插件环境。

        Args:
            _plugin: 插件对象（未使用）

        Returns:
            返回当前Python解释器路径作为模拟的环境路径
        """
        return Path(sys.executable)


@pytest.fixture
def fake_env_manager() -> FakeEnvManager:
    """提供一个虚假的环境管理器fixture。"""
    return FakeEnvManager()


# 导入需要使用的类型
from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.capability_router import CapabilityRouter
from astrbot_sdk.runtime.peer import Peer


@pytest.fixture
async def core_peer(transport_pair: tuple[MemoryTransport, MemoryTransport]) -> Peer:
    """创建一个配置了默认处理函数的核心对等方。

    这个fixture创建并启动一个核心角色的对等方，设置了初始化和调用处理函数。

    Args:
        transport_pair: 传输对fixture

    Returns:
        已启动的核心对等方实例
    """
    left, _ = transport_pair  # 使用传输对中的左传输
    router = CapabilityRouter()  # 创建能力路由器

    # 创建核心对等方
    peer = Peer(
        transport=left,
        peer_info=PeerInfo(name="core", role="core", version="v4"),
    )

    # 定义初始化处理函数
    async def init_handler(_message) -> InitializeOutput:
        return InitializeOutput(
            peer=PeerInfo(name="core", role="core", version="v4"),
            capabilities=router.descriptors(),  # 获取路由器描述的能力列表
            metadata={},
        )

    # 定义调用处理函数
    async def invoke_handler(message, token):
        return await router.execute(
            message.capability,  # 要执行的能力
            message.input,       # 输入参数
            stream=message.stream,  # 是否流式输出
            cancel_token=token,     # 取消令牌
            request_id=message.id,  # 请求ID
        )

    # 设置处理函数
    peer.set_initialize_handler(init_handler)
    peer.set_invoke_handler(invoke_handler)

    await peer.start()  # 启动对等方
    yield peer
    await peer.stop()  # 测试结束后停止


@pytest.fixture
async def plugin_peer(transport_pair: tuple[MemoryTransport, MemoryTransport]) -> Peer:
    """创建一个连接到核心的插件对等方。

    这个fixture创建并启动一个插件角色的对等方。

    Args:
        transport_pair: 传输对fixture

    Returns:
        已启动的插件对等方实例
    """
    _, right = transport_pair  # 使用传输对中的右传输

    # 创建插件对等方
    peer = Peer(
        transport=right,
        peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
    )

    await peer.start()  # 启动对等方
    yield peer
    await peer.stop()  # 测试结束后停止


@pytest.fixture
def temp_plugin_dir() -> Generator[Path, None, None]:
    """创建用于插件测试的临时目录。

    这个fixture创建一个临时目录，并在测试结束后自动清理。

    Yields:
        临时目录的Path对象
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


def create_test_plugin(plugin_root: Path, name: str = "test_plugin") -> None:
    """辅助函数：创建一个最小的测试插件。

    在指定目录创建插件所需的基本文件结构：
    - commands/__init__.py
    - commands/sample.py（包含测试命令）
    - requirements.txt（空文件）
    - plugin.yaml（插件配置文件）

    Args:
        plugin_root: 插件根目录
        name: 插件名称，默认为"test_plugin"
    """
    # 创建commands目录和__init__.py文件
    (plugin_root / "commands").mkdir(parents=True, exist_ok=True)
    (plugin_root / "commands" / "__init__.py").write_text("", encoding="utf-8")

    # 创建空的requirements.txt
    (plugin_root / "requirements.txt").write_text("", encoding="utf-8")

    # 创建插件配置文件plugin.yaml
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
              python: "{sys.version_info.major}.{sys.version_info.minor}"  # 使用当前Python版本
            components:
              - class: commands.sample:TestPlugin
                type: command
                name: test
                description: test command
            """
        ),
        encoding="utf-8",
    )

    # 创建测试命令文件sample.py
    (plugin_root / "commands" / "sample.py").write_text(
        textwrap.dedent(
            """\
            from astrbot_sdk import Context, MessageEvent, Star, on_command


            class TestPlugin(Star):
                @on_command("test")  # 注册test命令
                async def test_cmd(self, event: MessageEvent, ctx: Context):
                    await event.reply("test ok")  # 回复消息
            """
        ),
        encoding="utf-8",
    )


@pytest.fixture
def test_plugin(temp_plugin_dir: Path) -> Path:
    """创建一个测试插件并返回其根目录。

    这个fixture使用create_test_plugin函数创建插件，并返回插件目录路径。

    Args:
        temp_plugin_dir: 临时插件目录fixture

    Returns:
        包含插件的目录路径
    """
    plugin_root = temp_plugin_dir / "plugins" / "test_plugin"
    create_test_plugin(plugin_root)  # 创建测试插件
    return temp_plugin_dir / "plugins"