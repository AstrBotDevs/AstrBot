"""后台任务状态定义

定义后台任务的状态数据结构和状态转换逻辑。
"""

import time
import uuid
from asyncio import Queue, Event
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 正在执行
    COMPLETED = "completed"  # 执行完成
    FAILED = "failed"  # 执行失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class BackgroundTask:
    """后台任务状态

    Attributes:
        task_id: 任务唯一ID
        tool_name: 工具名称
        tool_args: 工具参数
        session_id: 会话ID (unified_msg_origin)
        status: 任务状态
        created_at: 创建时间
        started_at: 开始时间
        completed_at: 完成时间
        result: 执行结果
        error: 错误信息
        output_log: 输出日志
        event: 原始事件对象（用于主动回调）
    """

    task_id: str
    tool_name: str
    tool_args: dict[str, Any]
    session_id: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: str | None = None
    error: str | None = None
    output_log: list[str] = field(default_factory=list)
    notification_message: str | None = None  # 任务完成后的通知消息
    notification_sent: bool = False  # 通知是否已发送
    event: Any = None  # 原始事件对象，用于主动回调
    event_queue: Queue | None = None  # 事件队列，用于触发AI回调
    is_being_waited: bool = False
    completion_event: Event | None = None  # 任务完成信号  # 是否有LLM正在使用wait_tool_result等待此任务

    @staticmethod
    def generate_id() -> str:
        """生成唯一任务ID"""
        return str(uuid.uuid4())[:8]

    def start(self) -> None:
        """标记任务开始执行"""
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()

    def complete(self, result: str) -> None:
        """标记任务完成"""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = time.time()
        self._signal_completion()

    def fail(self, error: str) -> None:
        """标记任务失败"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = time.time()
        self._signal_completion()

    def cancel(self) -> None:
        """标记任务取消"""
        self.status = TaskStatus.CANCELLED
        self.completed_at = time.time()
        self._signal_completion()

    def append_output(self, line: str) -> None:
        """追加输出日志"""
        self.output_log.append(line)

    def is_finished(self) -> bool:
        """检查任务是否已完成"""
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "session_id": self.session_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "output_log_count": len(self.output_log),
        }

    def _signal_completion(self) -> None:
        """触发完成信号"""
        if self.completion_event is not None:
            self.completion_event.set()

    def release_references(self) -> None:
        """释放大对象引用，防止内存泄露

        任务完成后，不再需要event和event_queue引用，
        释放它们以允许垃圾回收。
        应在所有回调完成后调用。
        """
        self.event = None
        self.event_queue = None
        self.completion_event = None
        self.output_log.clear()  # 日志已保存到OutputBuffer

    def init_completion_event(self) -> None:
        """初始化完成事件"""
        import asyncio
        try:
            self.completion_event = asyncio.Event()
        except RuntimeError:
            pass
