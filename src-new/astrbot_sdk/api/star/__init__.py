"""过渡期 ``astrbot_sdk.api.star`` compat facade。"""

from ..._legacy_api import LegacyStar as Star, StarTools, register
from .context import Context
from .star import StarMetadata

__all__ = ["Context", "Star", "StarMetadata", "StarTools", "register"]
