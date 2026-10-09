from astrbot.core.star import Context, Star, StarTools
from astrbot.core.star.config import *
from astrbot.core.star.register import (
    register_star as register,  # 注册插件（Star）
)
from astrbot.core.utils.lang_utils import get_lang, multi_alias

__all__ = ["Context", "Star", "StarTools", "register", "get_lang", "multi_alias"]
