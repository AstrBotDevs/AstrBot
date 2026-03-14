"""MindSim 动作模块

包含私聊和群聊场景下的动作实现。
"""

from typing import Type

from astrbot.core.mind_sim.action import Action

# 动作类导入
from .Reply import ReplyAction
from .Wait import WaitAction

# 私聊可用动作
PRIVATE_ACTIONS = [
    ReplyAction,
    WaitAction,
]


def get_available_actions() -> list[Type[Action]]:
    """获取可用的动作类列表"""
    return PRIVATE_ACTIONS


__all__ = [
    "ReplyAction",
    "WaitAction",
    "get_available_actions",
]
