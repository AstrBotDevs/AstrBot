"""旧版 ``astrbot.api.util`` 导入路径兼容入口。"""

from astrbot.core.utils.session_waiter import (
    SessionController,
    SessionWaiter,
    session_waiter,
)

__all__ = ["SessionController", "SessionWaiter", "session_waiter"]
