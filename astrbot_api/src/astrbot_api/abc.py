from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from importlib.abc import Traversable
from pathlib import Path
from typing import ClassVar

import anyio
import tomli
import yaml
from yarl import URL

from .models import AstrbotPluginMetadata

# region 核心运行时协议

class IAstrbotPaths(ABC):
    """路径管理的抽象基类."""

    @abstractmethod
    def __init__(self, name: str) -> None:
        """初始化路径管理器."""

    @classmethod
    @abstractmethod
    def getPaths(cls, name: str) -> IAstrbotPaths:
        """返回Paths实例,用于访问模块的各类目录."""

    @property
    @abstractmethod
    def root(self) -> Path:
        """获取根目录."""

    @property
    @abstractmethod
    def home(self) -> Path:
        """获取模块/插件主目录."""

    @property
    @abstractmethod
    def config(self) -> Path:
        """获取模块配置目录."""

    @property
    @abstractmethod
    def data(self) -> Path:
        """获取模块数据目录."""

    @property
    @abstractmethod
    def log(self) -> Path:
        """获取模块日志目录."""

    @property
    @abstractmethod
    def temp(self) -> Path:
        """获取模块临时目录."""

    @property
    @abstractmethod
    def plugins(self) -> Path:
        """获取插件目录."""

    @abstractmethod
    def reload(self) -> None:
        """重新加载环境变量."""

    @classmethod
    @abstractmethod
    def is_root(cls, path: Path) -> bool:
        """判断路径是否为根目录."""

    @abstractmethod
    def chdir(self, cwd: str = "home") -> AbstractContextManager[Path]:
        """临时切换到指定目录, 子进程将继承此 CWD。"""

    @abstractmethod
    async def achdir(self, cwd: str = "home") -> AbstractAsyncContextManager[Path]:
        """异步临时切换到指定目录, 子进程将继承此 CWD。"""












class AstrbotPluginBaseSession(ABC):
    """插件会话的基类."""

    url: URL
    """插件的astrbot专有协议URL地址.

    协议: astrbot://{stdio/web/legacy}/plugin_id
    """


    @abstractmethod
    def connect(self) -> AstrbotPluginBaseSession:
        """连接到插件."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """断开与插件的连接."""
        ...

    @abstractmethod
    async def async_connect(self) -> AstrbotPluginBaseSession:
        """异步连接到插件."""
        ...

    @abstractmethod
    async def async_disconnect(self) -> None:
        """异步断开与插件的连接."""
        ...

    @contextmanager
    def session_scope(self) -> Generator[AstrbotPluginBaseSession]:
        """插件会话的上下文管理器."""
        try:
            yield self.connect()
        finally:
            self.disconnect()

    @asynccontextmanager
    async def async_session_scope(self) -> AsyncGenerator[AstrbotPluginBaseSession]:
        """异步插件会话的上下文管理器."""
        try:
            yield await self.async_connect()
        finally:
            await self.async_disconnect()

# region 数据传输方法

# 主动发送数据
    @abstractmethod
    def send(self, data: bytes) -> bytes:
        """发送数据到插件并接收响应."""
        ...

    @abstractmethod
    async def async_send(self, data: bytes) -> bytes:
        """异步发送数据到插件并接收响应."""
        ...

# 被动接收数据
    @abstractmethod
    def listen(self, callback: Callable[[bytes], bytes | None]) -> None:
        """监听插件发送的数据.

        callback: 一个接受 bytes 类型参数并返回 bytes 或 None 的函数.
        如果返回 None, 则不给插件发送响应.

        """
        ...

    @abstractmethod
    async def async_listen(self, callback: Callable[[bytes], bytes | None]) -> None:
        """异步监听插件发送的数据.

        callback: 一个接受 bytes 类型参数并返回 bytes 或 None 的函数.
        如果返回 None, 则不给插件发送响应.
        """
        ...





class IVirtualAstrbotPlugin(ABC):
    """AstrBot 虚拟插件的基类协议."""

    vpo_map: ClassVar[dict[URL, IVirtualAstrbotPlugin]] = {}
    """虚拟插件对象映射表, key 是插件的 astrbot 协议 URL 地址."""

    url: URL
    """AstrBot 插件的 astrbot 专有协议 URL 地址.
    协议:
        astrbot://{stdio/web/legacy}/plugin_id
    """

    metadata: AstrbotPluginMetadata
    """插件元数据."""

    session: AstrbotPluginBaseSession
    """插件会话对象."""

# region 公共方法
    @classmethod
    @abstractmethod
    def handshake(cls) -> None:
        """通用插件握手方法.

        1. 发送握手请求
        2. 接受插件元数据响应,并设置 metadata 属性
        3. 返回确认消息,表示握手成功
        """
        ...

# part1 ：工厂方法
    @classmethod
    @abstractmethod
    def fromFile(cls, path: Path, * , stdio: bool = False) -> IVirtualAstrbotPlugin:
        """从文件加载插件/插件包的公共方法.

        通过此方法加载经典插件: stdio=False
        或者子进程插件: stdio=True

        任务:
            1. 从 path 加载插件,调用私有方法 _load_metadata 加载插件元数据.
        """
        ...


    @classmethod
    @abstractmethod
    def fromURL(cls, url: URL) -> IVirtualAstrbotPlugin:
        """从URL加载插件/插件包的公共方法."""
        ...


# part2 ：实例方法

    @abstractmethod
    def get_logo(self) -> Traversable | None:
        """获取插件的logo文件路径(Optional).

        请使用importlib.resources.files来访问并返回Traversable对象.
        示例:
            from importlib.resources import files
            logo_path = files("plugin_a/assets/logo.png")
            # 如果插件安装在虚拟环境，可以直接这样获取

            # 如果插件不可以安装到虚拟环境，适用于子进程插件/网络插件，可以这样获取


        返回None表示没有logo文件.
        Returns:
            Traversable | None: 插件logo文件的路径或None.
        """
        ...

    @abstractmethod
    def get_metadata(self) -> AstrbotPluginMetadata:
        """获取插件元数据的公共方法."""
        ...

    @abstractmethod
    def get_url(self) -> URL:
        """获取插件URL(astrbot协议)的公共方法."""
        ...

    @abstractmethod
    def get_session(self) -> AstrbotPluginBaseSession:
        """获取插件会话对象的公共方法."""
        ...



# region 魔术方法

    @abstractmethod
    def __str__(self) -> str:
        """返回插件元数据的字符串表示."""
        ...

    @abstractmethod
    def __repr__(self) -> str:
        """返回插件元数据的正式字符串表示."""
        ...

# region 私有方法
    @classmethod
    def _load_metadata(cls, path: Path) -> AstrbotPluginMetadata:
        """加载插件元数据的私有方法,自动按下列优先级加载: pyproject -> yaml -> toml -> json.

        其中yaml: plugin.yaml > metadata.yaml

        此函数是上述工厂方法的辅助函数,用于加载插件元数据.
        """
        match path.suffix.lower():
            case ".json":
                return cls._load_metadata_json(path)
            case ".toml":
                return cls._load_metadata_toml(path)
            case ".yaml" | ".yml":
                return cls._load_metadata_yaml(path)
            case _:
                raise ValueError(f"不支持的插件元数据文件格式: {path.suffix}")

    @classmethod
    async def _load_metadata_async(cls, path: Path) -> AstrbotPluginMetadata:
        """异步加载插件元数据的私有方法,自动按下列优先级加载: pyproject -> yaml -> toml -> json.

        其中yaml: plugin.yaml > metadata.yaml

        此函数是上述工厂方法的辅助函数,用于加载插件元数据.
        """
        return await anyio.to_thread.run_sync(cls._load_metadata, path)  # type: ignore[attr-defined]

    @classmethod
    def _load_metadata_json(cls, path: Path) -> AstrbotPluginMetadata:
        """从json文件加载插件元数据的私有方法."""
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return AstrbotPluginMetadata.model_validate(**data)

    @classmethod
    async def _load_metadata_json_async(cls, path: Path) -> AstrbotPluginMetadata:
        """异步从json文件加载插件元数据的私有方法."""
        async with await anyio.open_file(path, "r", encoding="utf-8") as f:
            content = await f.read()
        data = json.loads(content)
        return AstrbotPluginMetadata.model_validate(**data)

    @classmethod
    def _load_metadata_toml(cls, path: Path) -> AstrbotPluginMetadata:
        """从toml文件加载插件元数据的私有方法."""
        with path.open("rb") as f:
            data = tomli.load(f)
        return AstrbotPluginMetadata.model_validate(**data)

    @classmethod
    async def _load_metadata_toml_async(cls, path: Path) -> AstrbotPluginMetadata:
        """异步从toml文件加载插件元数据的私有方法."""
        async with await anyio.open_file(path, "rb") as f:
            content = await f.read()
        content_str = content.decode("utf-8")
        data = tomli.loads(content_str)
        return AstrbotPluginMetadata.model_validate(**data)

    @classmethod
    def _load_metadata_yaml(cls, path: Path) -> AstrbotPluginMetadata:
        """从yaml文件加载插件元数据的私有方法."""
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return AstrbotPluginMetadata.model_validate(**data)

    @classmethod
    async def _load_metadata_yaml_async(cls, path: Path) -> AstrbotPluginMetadata:
        """异步从yaml文件加载插件元数据的私有方法."""
        async with await anyio.open_file(path, "r", encoding="utf-8") as f:
            content = await f.read()
        data = yaml.safe_load(content)
        return AstrbotPluginMetadata.model_validate(**data)


# region 插件运行时协议

class IAstrbotPluginRuntime(ABC):
    """AstrBot 插件运行时的基类协议."""

    @abstractmethod
    def start(self) -> None:
        """启动插件运行时."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """停止插件运行时."""
        ...

