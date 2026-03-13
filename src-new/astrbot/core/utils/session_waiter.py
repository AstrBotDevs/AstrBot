"""旧版 ``astrbot.core.utils.session_waiter`` 导入路径兼容入口。"""

from astrbot_sdk._session_waiter import SessionController, SessionWaiter, session_waiter

__all__ = ["SessionController", "SessionWaiter", "session_waiter"]
