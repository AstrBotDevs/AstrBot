from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.session_waiter import SessionWaiter, USER_SESSIONS
from sys import maxsize


@register(
    "session_controller",
    "Cvandia & Soulter",
    "为插件支持会话控制",
    "v1.0.1",
    "https://astrbot.app",
)
class Waiter(Star):
    """会话控制"""

    def __init__(self, context: Context):
        super().__init__(context)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize)
    async def handle_session_control_agent(self, event: AstrMessageEvent):
        session_id = event.unified_msg_origin
        if session_id in USER_SESSIONS:
            await SessionWaiter.trigger(session_id, event)
            event.stop_event()
