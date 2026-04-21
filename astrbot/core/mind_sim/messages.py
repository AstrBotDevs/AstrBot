"""mind_sim 内部消息类型定义

消息流向：
- 外部 → mind_sim: IncomingUserMessage
- mind_sim → Action: ActionStartMsg, ActionSendMsg, ActionStopMsg
- Action → mind_sim: ActionStateUpdate, ActionOutput
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MindMessage:
    """mind_sim 内部消息基类"""

    pass


@dataclass
class ActionState:
    """动作状态快照 - 主思考读取这个来了解动作情况"""

    action_name: str
    status: str = (
        "idle"  # "idle" | "running" | "paused" | "completed" | "error" | "stopped"
    )
    progress: str | None = None  # 人类可读的进度描述
    data: dict = field(default_factory=dict)  # 动作自定义数据
    prompt_contribution: str | None = None  # 贡献给主思考的动态提示词
    can_receive: bool = True  # 是否能接收主思考的消息
    error: str | None = None  # 错误信息
    created_at: float = 0
    updated_at: float = 0


@dataclass
class ActionStartMsg(MindMessage):
    """主思考 → 动作：启动"""

    action_name: str
    params: dict = field(default_factory=dict)


@dataclass
class ActionSendMsg(MindMessage):
    """主思考 → 动作：发送消息（影响运行中的动作）"""

    action_name: str
    message: str
    data: dict = field(default_factory=dict)


@dataclass
class ActionStopMsg(MindMessage):
    """主思考 → 动作：停止"""

    action_name: str
    reason: str = ""


@dataclass
class ActionStateUpdate(MindMessage):
    """动作 → mind_sim：状态更新"""

    action_name: str
    state: ActionState


@dataclass
class ActionOutput(MindMessage):
    """动作 → mind_sim：产出"""

    action_name: str
    type: (
        str  # "reply" | "typing" | "internal" | "error" | "request_think" | "completed"
    )
    content: str | None = None
    metadata: dict = field(default_factory=dict)
    prompt: str | None = None  # 触发思考的原因（用于 request_think）


@dataclass
class IncomingUserMessage(MindMessage):
    """外部 → mind_sim：收到用户消息"""

    sender_id: str
    sender_name: str
    content: str
    is_private: bool
    timestamp: float
    message_obj: Any = None  # 原始消息对象


@dataclass
class Decision:
    """主思考的决策"""

    action: str  # "START" | "SEND" | "STOP" | "REPLY" | "THINK" | "WAIT"
    target: str | None  # 目标动作名称
    message: str | None  # 消息内容
    reasoning: str | None = None  # 决策理由
    params: dict = field(default_factory=dict)


class MindEventType(Enum):
    """mind_sim 对外输出的事件类型"""

    REPLY = "reply"  # 回复用户
    TYPING = "typing"  # 正在输入
    THINKING = "thinking"  # 思考过程
    ACTION_START = "action_start"  # 动作开始
    ACTION_OUTPUT = "action_output"  # 动作产出（reply/typing/error 等）
    ACTION_END = "action_end"  # 动作结束
    INTERNAL = "internal"  # 内部状态变化
    TRIGGER_THINK = "trigger_think"  # 触发主思考（动作完成/等待结束后请求再次思考）
    PIPELINE_YIELD = "pipeline_yield"  # 请求 pipeline 框架 yield（让 RespondStage 发送 event.result）
    END = "end"  # 思考结束（事件流结束）
    ERROR = "error"  # 错误


@dataclass
class MindEvent:
    """mind_sim 对外输出的事件"""

    type: MindEventType
    data: dict = field(default_factory=dict)

    @classmethod
    def reply(cls, text: str, metadata: dict | None = None) -> "MindEvent":
        return cls(type=MindEventType.REPLY, data={"text": text, **(metadata or {})})

    @classmethod
    def typing(cls) -> "MindEvent":
        return cls(type=MindEventType.TYPING)

    @classmethod
    def thinking(cls, content: str) -> "MindEvent":
        return cls(type=MindEventType.THINKING, data={"content": content})

    @classmethod
    def action_start(cls, action_name: str, params: dict) -> "MindEvent":
        return cls(
            type=MindEventType.ACTION_START,
            data={"action": action_name, "params": params},
        )

    @classmethod
    def action_end(cls, action_name: str, result: dict | None = None) -> "MindEvent":
        return cls(
            type=MindEventType.ACTION_END,
            data={"action": action_name, "result": result or {}},
        )

    @classmethod
    def action_output(
        cls,
        action_name: str,
        output_type: str,
        content: str,
        metadata: dict | None = None,
    ) -> "MindEvent":
        """动作产出事件（reply/typing/error 等）"""
        return cls(
            type=MindEventType.ACTION_OUTPUT,
            data={
                "action": action_name,
                "output_type": output_type,
                "content": content,
                **(metadata or {}),
            },
        )

    @classmethod
    def trigger_think(cls, reason: str = "") -> "MindEvent":
        """触发主思考事件（动作完成后请求再次思考）"""
        return cls(type=MindEventType.TRIGGER_THINK, data={"reason": reason})

    @classmethod
    def end(cls, reason: str = "") -> "MindEvent":
        """思考结束事件"""
        return cls(type=MindEventType.END, data={"reason": reason})

    @classmethod
    def pipeline_yield(cls, done_event: Any = None) -> "MindEvent":
        """请求 pipeline yield 事件

        AgentMindSubStage.call() 设置好 event.result 后发出此事件，
        InternalMindSubStage 收到后 yield 给 pipeline 框架，
        RespondStage 处理完后 yield 返回，通知 done_event。

        Args:
            done_event: asyncio.Event，pipeline yield 完成后 set()
        """
        return cls(
            type=MindEventType.PIPELINE_YIELD,
            data={"done_event": done_event},
        )

    @classmethod
    def error(cls, message: str, metadata: dict | None = None) -> "MindEvent":
        """错误事件"""
        return cls(
            type=MindEventType.ERROR, data={"message": message, **(metadata or {})}
        )
