"""执行结果类型定义"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecutionStatus(Enum):
    """执行状态枚举"""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BACKGROUND = "background"


@dataclass
class ExecutionResult:
    """执行结果"""

    status: ExecutionStatus
    value: Any = None
    error: str | None = None
    task_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class TimeoutContext:
    """超时上下文"""

    tool_name: str
    tool_args: dict
    session_id: str
    handler: Any
    event: Any = None
    event_queue: Any = None
