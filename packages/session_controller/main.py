import astrbot.api.message_components as Comp
import copy
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.session_waiter import (
    SessionWaiter,
    USER_SESSIONS,
    FILTERS,
    session_waiter,
    SessionController,
)
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

        self.empty_mention_waiting = self.context.get_config()["platform_settings"][
            "empty_mention_waiting"
        ]
        self.wake_prefix = self.context.get_config()["wake_prefix"]

    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize)
    async def handle_session_control_agent(self, event: AstrMessageEvent):
        """会话控制代理"""
        for session_filter in FILTERS:
            session_id = session_filter.filter(event)
            if session_id in USER_SESSIONS:
                await SessionWaiter.trigger(session_id, event)
                event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize - 1)
    async def handle_empty_mention(self, event: AstrMessageEvent):
        """实现了对只有一个 @ 的消息内容的处理"""
        try:
            messages = event.get_messages()
            if len(messages) == 1:
                if (
                    isinstance(messages[0], Comp.At)
                    and str(messages[0].qq) == str(event.get_self_id())
                    and self.empty_mention_waiting
                ) or (
                    isinstance(messages[0], Comp.Plain)
                    and messages[0].text.strip() in self.wake_prefix
                ):
                    yield event.plain_result("想要问什么呢？😄")

                    @session_waiter(60)
                    async def empty_mention_waiter(
                        controller: SessionController, event: AstrMessageEvent
                    ):
                        logger.info("empty_mention_waiter")
                        event.message_obj.message.insert(
                            0, Comp.At(qq=event.get_self_id(), name=event.get_self_id())
                        )
                        new_event = copy.copy(event)
                        self.context.get_event_queue().put_nowait(
                            new_event
                        )  # 重新推入事件队列
                        event.stop_event()
                        controller.stop()

                    try:
                        await empty_mention_waiter(event)
                    except TimeoutError as _:
                        yield event.plain_result("如果需要帮助，请再次 @ 我哦~")
                    except Exception as e:
                        yield event.plain_result("发生错误，请联系管理员: " + str(e))
                    finally:
                        event.stop_event()
        except Exception as e:
            logger.error("handle_empty_mention error: " + str(e))
