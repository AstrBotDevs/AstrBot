"""MindSim 动作模块

包含私聊和群聊场景下的动作实现。
"""

from astrbot.core.mind_sim.action import Action

# 动作类导入
from .EndConversation import EndConversationAction
from .NoOp import NoOpAction
from .Reply import ReplyAction
from .RunTask import RunTaskAction
from .Wait import WaitAction

# 私聊可用动作
PRIVATE_ACTIONS = [
    ReplyAction,
    WaitAction,
    NoOpAction,
    EndConversationAction,
    RunTaskAction,
]


def get_available_actions() -> list[type[Action]]:
    """获取可用的动作类列表"""
    return PRIVATE_ACTIONS


__all__ = [
    "ReplyAction",
    "WaitAction",
    "NoOpAction",
    "EndConversationAction",
    "RunTaskAction",
    "get_available_actions",
]
