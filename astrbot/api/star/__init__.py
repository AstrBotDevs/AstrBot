from astrbot.core.star.base import Star
from astrbot.core.star.config import *
from astrbot.core.star.context import Context
from astrbot.core.star.register import (
    register_star as register,  # 注册插件（Star）
)
from astrbot.core.star.star_tools import StarTools

__all__ = ["Context", "Star", "StarTools", "register"]
