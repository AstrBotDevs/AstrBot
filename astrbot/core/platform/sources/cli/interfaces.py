"""CLI核心接口定义

定义CLI模块的核心抽象接口，遵循依赖倒置原则。
所有具体实现依赖于这些接口，而非具体实现。
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from astrbot.core.message.message_event_result import MessageChain


@runtime_checkable
class ITokenValidator(Protocol):
    """Token验证器接口"""

    def validate(self, token: str) -> bool:
        """验证Token"""
        ...


@runtime_checkable
class IMessageConverter(Protocol):
    """消息转换器接口"""

    def convert(
        self,
        text: str,
        request_id: str | None = None,
        use_isolated_session: bool = False,
    ) -> Any:
        """将文本转换为消息对象"""
        ...


@runtime_checkable
class ISessionManager(Protocol):
    """会话管理器接口"""

    def register(self, session_id: str) -> None:
        """注册会话"""
        ...

    def touch(self, session_id: str) -> None:
        """更新会话时间戳"""
        ...

    def is_expired(self, session_id: str) -> bool:
        """检查会话是否过期"""
        ...


class IHandler(ABC):
    """处理器抽象基类

    所有模式处理器（Socket/TTY/File）的共同接口。
    """

    @abstractmethod
    async def run(self) -> None:
        """运行处理器"""
        pass

    @abstractmethod
    def stop(self) -> None:
        """停止处理器"""
        pass


class IResponseBuilder(Protocol):
    """响应构建器接口"""

    def build_success(self, message_chain: MessageChain, request_id: str) -> str:
        """构建成功响应"""
        ...

    def build_error(self, error_msg: str, request_id: str | None = None) -> str:
        """构建错误响应"""
        ...


class IImageProcessor(Protocol):
    """图片处理器接口"""

    def preprocess_chain(self, message_chain: MessageChain) -> None:
        """预处理消息链中的图片"""
        ...

    def extract_images(self, message_chain: MessageChain) -> list[Any]:
        """从消息链中提取图片信息"""
        ...
