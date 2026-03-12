# =============================================================================
# 新旧对比 - star.py
# =============================================================================
#
# 【旧版 src/astrbot_sdk/api/star/star.py】
# - StarMetadata: 插件元数据类（dataclass）
#   - 属性: name, author, desc, version, repo, module_path, root_dir_name,
#          reserved, activated, config, star_handler_full_names, display_name, logo_path
# - 旧版没有 Star 基类定义（定义在其他文件中）
#
# 【新版 src-new/astrbot_sdk/star.py】
# - Star: 插件基类
#   - __handlers__: 处理器方法名元组
#   - __init_subclass__(): 自动收集装饰器标记的方法
#   - on_start(), on_stop(), on_error(): 生命周期钩子
#   - __astrbot_is_new_star__(): 标识新版 Star
#
# 【架构差异】
# - 旧版: StarMetadata 独立定义，Star 类在其他地方
# - 新版: Star 基类在此文件，元数据通过装饰器自动收集
#
# =============================================================================
# TODO: 功能缺失
# =============================================================================
#
# 1. 缺少 StarMetadata 类
#    - 旧版: @dataclass class StarMetadata
#    - 新版: 无对应实现
#    - 属性: name, author, desc, version, repo, module_path, root_dir_name,
#           reserved, activated, config, star_handler_full_names, display_name, logo_path
#    - 迁移: 可能需要在 api/star/__init__.py 或单独文件中实现
#
# 2. 生命周期方法差异
#    - 新版 on_start/on_stop 参数类型为 Any | None
#    - 应该使用更精确的类型注解
#
# 3. 缺少旧版 Star 接口方法（如果有的话）
#    - 需要确认旧版 Star 是否有其他必须实现的接口方法
#
# =============================================================================

from __future__ import annotations

import traceback
from typing import Any

from loguru import logger

from .errors import AstrBotError


class Star:
    __handlers__: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from .decorators import get_handler_meta

        handlers: dict[str, None] = {}
        for base in reversed(cls.__mro__):
            for name, attr in getattr(base, "__dict__", {}).items():
                func = getattr(attr, "__func__", attr)
                meta = get_handler_meta(func)
                if meta is not None and meta.trigger is not None:
                    handlers[name] = None
        cls.__handlers__ = tuple(handlers.keys())

    async def on_start(self, ctx: Any | None = None) -> None:
        return None

    async def on_stop(self, ctx: Any | None = None) -> None:
        return None

    async def on_error(self, error: Exception, event, ctx) -> None:
        if isinstance(error, AstrBotError):
            if error.retryable:
                await event.reply("请求失败，请稍后重试")
            elif error.hint:
                await event.reply(error.hint)
            else:
                await event.reply(error.message)
        else:
            await event.reply("出了点问题，请联系插件作者")
        logger.error("handler 执行失败\n{}", traceback.format_exc())

    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        return True
