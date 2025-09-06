"""
astrbot.api.star
该模块包括所有插件注册相关模块以及插件使用的数据
"""

from astrbot.core.star.register import (
    register_star as register,  # 注册插件（Star）
)

from astrbot.core.star import Context, Star, StarTools
from astrbot.core.star.config import load_config, put_config, update_config  # 已弃用

__all__ = ["register", "Context", "Star", "StarTools"]
