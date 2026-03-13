from __future__ import annotations  # 启用延迟类型注解求值，避免循环引用

import asyncio
from pathlib import Path

from astrbot_sdk.runtime.transport import Transport


class MemoryTransport(Transport):
    """基于内存的传输层实现，用于测试场景。

    继承自Transport基类，模拟两个对等方之间的通信，所有消息在内存中传递，
    无需实际网络连接。主要用于单元测试。
    """

    def __init__(self) -> None:
        """初始化内存传输实例。"""
        super().__init__()  # 调用父类初始化方法
        self.partner: "MemoryTransport | None" = None  # 通信伙伴，可以是对等的另一个MemoryTransport实例

    async def start(self) -> None:
        """启动传输。

        通过清除关闭标志使传输变为可用状态。
        """
        self._closed.clear()  # 清除关闭事件

    async def stop(self) -> None:
        """停止传输。

        设置关闭标志，表示传输已停止。
        """
        self._closed.set()  # 设置关闭事件

    async def send(self, payload: str) -> None:
        """发送消息给伙伴。

        Args:
            payload: 要发送的消息内容字符串

        Raises:
            RuntimeError: 如果没有设置伙伴传输（即self.partner为None）
        """
        if self.partner is None:
            raise RuntimeError("MemoryTransport 未连接 partner")
        # 将消息转发给伙伴的_dispatch方法进行处理
        await self.partner._dispatch(payload)


def make_transport_pair() -> tuple[MemoryTransport, MemoryTransport]:
    """创建一对相互连接的内存传输实例。

    工厂函数，用于创建两个互为通信伙伴的MemoryTransport实例，
    简化测试设置过程。

    Returns:
        tuple[MemoryTransport, MemoryTransport]: 返回左右两个传输实例的元组，
        它们已互相设置为伙伴关系
    """
    left = MemoryTransport()  # 创建左侧传输实例
    right = MemoryTransport()  # 创建右侧传输实例
    left.partner = right  # 设置左侧的伙伴为右侧
    right.partner = left  # 设置右侧的伙伴为左侧
    return left, right  # 返回配对的传输实例


class FakeEnvManager:
    """虚假的环境管理器，用于测试。

    模拟真实环境管理器的行为，但不执行实际的环境准备操作，
    主要用于需要环境管理器但又不希望产生副作用的测试场景。
    """

    def prepare_environment(self, _plugin) -> Path:
        """模拟准备插件环境的方法。

        不实际创建虚拟环境，而是返回当前Python解释器路径作为模拟的环境路径。

        Args:
            _plugin: 插件对象参数，在模拟实现中未使用

        Returns:
            Path: 当前Python解释器的路径
        """
        # 动态导入sys模块并返回可执行文件路径
        return Path(__import__("sys").executable)


async def drain_loop() -> None:
    """清空事件循环的辅助函数。

    通过短暂的异步睡眠，让事件循环有机会处理所有已排队的任务和回调。
    常用于测试中等待异步操作完成，确保所有待处理的事件被处理。

    睡眠时间(0.05秒)足够短不会明显减慢测试，又足够长让事件循环有机会处理任务。
    """
    await asyncio.sleep(0.05)  # 暂停当前协程50毫秒，让出控制权给事件循环