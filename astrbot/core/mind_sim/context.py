"""mind_sim 上下文状态"""

from dataclasses import dataclass, field
from typing import Any

from .messages import ActionState


@dataclass
class MindContext:
    """mind_sim 会话上下文

    包含会话的所有状态信息，主思考和所有动作共享此上下文。
    """

    # 会话标识
    session_id: str
    unified_msg_origin: str
    is_private: bool

    # 人格配置
    persona_id: str
    system_prompt: str = ""
    personality_config: dict = field(default_factory=dict)
    chat_config: dict = field(default_factory=dict)
    robot_config: dict = field(default_factory=dict)

    # 动作状态（主思考从这里读取）
    action_states: dict[str, ActionState] = field(default_factory=dict)

    # 对话历史（给主思考用）
    conversation_history: list[dict] = field(default_factory=list)

    # 用户信息
    user_id: str = ""
    user_name: str = ""

    # 自由存储区（动作可以存取）
    memory: dict = field(default_factory=dict)

    def get_action_state(self, action_name: str) -> ActionState | None:
        """获取指定动作的状态"""
        return self.action_states.get(action_name)

    def get_running_actions(self) -> list[str]:
        """获取所有正在运行的动作名称"""
        return [
            name for name, state in self.action_states.items()
            if state.status == "running"
        ]

    def has_running_action(self, action_name: str) -> bool:
        """检查指定动作是否正在运行"""
        state = self.action_states.get(action_name)
        return state is not None and state.status == "running"

    def to_prompt_context(self) -> dict:
        """转换为提示词上下文（供主思考使用）"""
        return {
            "session_id": self.session_id,
            "is_private": self.is_private,
            "persona_id": self.persona_id,
            "user_name": self.user_name,
            "running_actions": self.get_running_actions(),
            "memory_keys": list(self.memory.keys()),
        }
