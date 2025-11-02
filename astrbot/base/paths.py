from __future__ import annotations

import os
from contextlib import (
    asynccontextmanager,
    contextmanager,
)
from os import getenv
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from dotenv import load_dotenv
from packaging.utils import NormalizedName, canonicalize_name

from astrbot.base.abc import IAstrbotPaths

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator


class AstrbotPaths(IAstrbotPaths):
    """Class to manage and provide paths used by Astrbot Canary."""

    load_dotenv()
    astrbot_root: ClassVar[Path] = Path(
        getenv("ASTRBOT_ROOT", Path.home() / ".astrbot")
    ).absolute()

    def __init__(self, name: str) -> None:
        self.name: str = name
        # 确保根目录存在
        self.astrbot_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def getPaths(cls, name: str) -> AstrbotPaths:
        """返回Paths实例,用于访问模块的各类目录."""
        normalized_name: NormalizedName = canonicalize_name(name)
        instance: AstrbotPaths = cls(normalized_name)
        instance.name = normalized_name
        return instance

    @property
    def root(self) -> Path:
        """返回根目录."""
        return (
            self.astrbot_root if self.astrbot_root.exists() else Path.cwd() / ".astrbot"
        )

    @property
    def home(self) -> Path:
        """模块/插件主目录.

        通过此属性获取模块/插件主目录.
        """
        my_home = self.astrbot_root / "home" / self.name
        my_home.mkdir(parents=True, exist_ok=True)
        return my_home

    @property
    def config(self) -> Path:
        """返回模块/插件配置目录.

        搭配 astrbot_config 使用.
        """
        config_path = self.astrbot_root / "config" / self.name
        config_path.mkdir(parents=True, exist_ok=True)
        return config_path

    @property
    def data(self) -> Path:
        """返回模块数据目录."""
        data_path = self.astrbot_root / "data" / self.name
        data_path.mkdir(parents=True, exist_ok=True)
        return data_path

    @property
    def log(self) -> Path:
        """返回模块日志目录."""
        log_path = self.astrbot_root / "logs" / self.name
        log_path.mkdir(parents=True, exist_ok=True)
        return log_path

    @classmethod
    def is_root(cls, path: Path) -> bool:
        """检查路径是否为 Astrbot 根目录."""
        if not path.exists() or not path.is_dir():
            return False
        # 检查此目录内是是否包含.astrbot标记文件
        if not (path / ".astrbot").exists():
            return False
        return True

    def reload(self) -> None:
        """重新加载环境变量."""
        load_dotenv()
        self.__class__.astrbot_root = Path(
            getenv("ASTRBOT_ROOT", Path.home() / ".astrbot")
        ).absolute()

    @contextmanager
    def chdir(self, cwd: str = "home") -> Generator[Path]:
        """临时切换到指定目录, 子进程将继承此 CWD。"""
        original_cwd = Path.cwd()
        target_dir = self.root / cwd
        try:
            os.chdir(target_dir)
            yield target_dir
        finally:
            os.chdir(original_cwd)

    # 上面类型标注没错，这里mypy报错，但是这不应该错误，直接忽略掉
    @asynccontextmanager
    async def achdir(self, cwd: str = "home") -> AsyncGenerator[Path]:  # type: ignore
        """异步上下文管理器: 临时切换到指定目录, 子进程将继承此 CWD。"""
        original_cwd = Path.cwd()
        target_dir = self.root / cwd
        try:
            os.chdir(target_dir)
            yield target_dir
        finally:
            os.chdir(original_cwd)
