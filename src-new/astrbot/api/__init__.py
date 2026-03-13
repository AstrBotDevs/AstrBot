"""旧版 ``astrbot.api`` 导入路径兼容入口。"""

from loguru import logger

from astrbot_sdk._shared_preferences import sp
from astrbot_sdk.api import (
    AstrBotConfig,
    components,
    event,
    message,
    message_components,
    star,
)
from astrbot_sdk.api.event.filter import llm_tool

from . import platform, provider, util


def agent(*args, **kwargs):
    raise NotImplementedError(
        "astrbot.api.agent() 尚未在 v4 兼容层实现，请改用新版 capability/handler 结构。"
    )


def html_renderer(*args, **kwargs):
    raise NotImplementedError(
        "astrbot.api.html_renderer 在 v4 兼容层中尚未提供，请改用当前平台发送/渲染能力。"
    )


__all__ = [
    "AstrBotConfig",
    "agent",
    "components",
    "event",
    "html_renderer",
    "llm_tool",
    "logger",
    "message",
    "message_components",
    "platform",
    "provider",
    "sp",
    "star",
    "util",
]
