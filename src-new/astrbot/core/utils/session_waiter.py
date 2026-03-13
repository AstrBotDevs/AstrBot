"""旧版 ``astrbot.core.utils.session_waiter`` 导入路径兼容入口。"""

from astrbot_sdk._session_waiter import SessionController, session_waiter

__all__ = ["SessionController", "session_waiter"]
