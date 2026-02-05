"""核心接口定义

定义工具执行模块的核心接口，遵循依赖倒置原则。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any


class IMethodResolver(ABC):
    """方法解析器接口

    负责从工具对象中解析出可调用的方法。
    """

    @abstractmethod
    def resolve(self, tool: Any) -> tuple[Callable, str]:
        """解析工具的可调用方法

        Args:
            tool: 工具对象

        Returns:
            (handler, method_name) 元组

        Raises:
            MethodResolutionError: 无法解析方法时
        """
        ...


class IParameterValidator(ABC):
    """参数验证器接口

    负责验证工具调用参数。
    """

    @abstractmethod
    def validate(self, handler: Callable, params: dict) -> dict:
        """验证参数

        Args:
            handler: 处理函数
            params: 参数字典

        Returns:
            验证后的参数字典

        Raises:
            ParameterValidationError: 参数验证失败时
        """
        ...


class IResultProcessor(ABC):
    """结果处理器接口

    负责处理工具执行结果。
    """

    @abstractmethod
    async def process(self, result: Any) -> Any:
        """处理执行结果

        Args:
            result: 原始执行结果

        Returns:
            处理后的结果
        """
        ...


class ITimeoutStrategy(ABC):
    """超时策略接口

    负责执行带超时控制的协程。
    """

    @abstractmethod
    async def execute(self, coro: Coroutine, timeout: float) -> Any:
        """执行协程

        Args:
            coro: 协程对象
            timeout: 超时时间（秒）

        Returns:
            执行结果

        Raises:
            TimeoutError: 超时时
        """
        ...


class ITimeoutHandler(ABC):
    """超时处理器接口

    负责处理超时后的逻辑。
    """

    @abstractmethod
    async def handle_timeout(self, context: Any) -> Any:
        """处理超时

        Args:
            context: 执行上下文

        Returns:
            处理结果
        """
        ...


class IBackgroundTaskManager(ABC):
    """后台任务管理器接口"""

    @abstractmethod
    async def submit_task(
        self,
        tool_name: str,
        tool_args: dict,
        session_id: str,
        handler: Callable,
        **kwargs,
    ) -> str:
        """提交后台任务

        Returns:
            任务ID
        """
        ...

    @abstractmethod
    async def wait_task(self, task_id: str, timeout: float | None = None) -> Any:
        """等待任务完成"""
        ...


class ICompletionSignal(ABC):
    """任务完成信号接口（替代轮询）"""

    @abstractmethod
    async def wait(self, timeout: float | None = None) -> bool:
        """等待信号"""
        ...

    @abstractmethod
    def set(self) -> None:
        """设置信号"""
        ...


class ICallbackEventBuilder(ABC):
    """回调事件构建器接口"""

    @abstractmethod
    def build(self, task: Any, original_event: Any) -> Any:
        """构建回调事件

        Args:
            task: 后台任务
            original_event: 原始事件

        Returns:
            新的事件对象
        """
        ...


class IToolInvoker(ABC):
    """工具调用器接口

    抽象LLM工具调用逻辑，避免应用层直接依赖具体实现。
    """

    @abstractmethod
    def invoke(
        self, context: Any, handler: Callable, method_name: str, **kwargs
    ) -> Any:
        """调用工具

        Args:
            context: 运行上下文
            handler: 处理函数
            method_name: 方法名称
            **kwargs: 工具参数

        Returns:
            异步生成器
        """
        ...
