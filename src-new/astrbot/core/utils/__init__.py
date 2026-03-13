"""旧版 ``astrbot.core.utils`` 兼容入口。"""

from .session_waiter import SessionController, session_waiter

__all__ = ["SessionController", "session_waiter"]
