"""MindSim 私聊模块

包含私聊场景下的主思考模块和相关工具。
"""

from .brain import PrivateBrain
from .prompts import (
    ACTION_OPTIONS_TEMPLATE,
    DECISION_FORMAT_PROMPT,
    MAIN_THINKING_SYSTEM_PROMPT,
    build_action_options_prompt,
    build_action_states_prompt,
    build_history_prompt,
    build_main_thinking_prompt,
)

__all__ = [
    "PrivateBrain",
    "DECISION_FORMAT_PROMPT",
    "ACTION_OPTIONS_TEMPLATE",
    "MAIN_THINKING_SYSTEM_PROMPT",
    "build_action_options_prompt",
    "build_action_states_prompt",
    "build_history_prompt",
    "build_main_thinking_prompt",
]
