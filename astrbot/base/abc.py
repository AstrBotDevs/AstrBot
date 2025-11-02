from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from pathlib import Path


# TODO: 抽象基类
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

    @abstractmethod
    def reload(self) -> None:
        """重新加载环境变量."""

    @abstractmethod
    @classmethod
    def is_root(cls, path: Path) -> bool:
        """判断路径是否为根目录."""

    @abstractmethod
    def chdir(self, cwd: str = "home") -> AbstractContextManager[Path]:
        """临时切换到指定目录, 子进程将继承此 CWD。"""

    @abstractmethod
    async def achdir(self, cwd: str = "home") -> AbstractAsyncContextManager[Path]:
        """异步临时切换到指定目录, 子进程将继承此 CWD。"""
