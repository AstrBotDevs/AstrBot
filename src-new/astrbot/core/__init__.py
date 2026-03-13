"""旧版 ``astrbot.core`` 导入路径兼容入口。"""

from loguru import logger

from astrbot_sdk._shared_preferences import sp
from astrbot_sdk.api.basic import AstrBotConfig

from . import config, message, platform, utils


class _HtmlRendererCompat:
    """旧版 ``html_renderer`` 的导入占位。

    v4 兼容层目前没有复刻旧 core 的整套 HTML 渲染系统。
    保留符号用于导入兼容，真实调用时显式报错，避免静默伪兼容。
    TODO: 后续如果需要，可以在这里实现一个基于当前平台能力的 HTML 渲染适配器。
    """

    def __call__(self, *args, **kwargs):
        raise NotImplementedError(
            "astrbot.core.html_renderer 在 v4 兼容层中尚未提供，请改用当前平台发送/渲染能力。"
        )

    def __getattr__(self, _name: str):
        raise NotImplementedError(
            "astrbot.core.html_renderer 在 v4 兼容层中尚未提供，请改用当前平台发送/渲染能力。"
        )


html_renderer = _HtmlRendererCompat()

__all__ = [
    "AstrBotConfig",
    "config",
    "html_renderer",
    "logger",
    "message",
    "platform",
    "sp",
    "utils",
]
