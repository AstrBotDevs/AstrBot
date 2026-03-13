"""旧版 ``astrbot_sdk.api.star`` 的兼容入口。"""

from ..._legacy_api import LegacyStar as Star, StarTools, register
from .context import Context
from .star import StarMetadata

__all__ = ["Context", "Star", "StarMetadata", "StarTools", "register"]
