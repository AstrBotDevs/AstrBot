from astrbot.core.star.register import (
    register_star as register,  # 注册插件（Star）
)

from astrbot.core.star import Context, Star, StarTools
from astrbot.core.star.config import * # 过时 跳过检查 # noqa: F401,F403

__all__ = [
    "register", 
    "Context", 
    "Star", 
    "StarTools"

]
