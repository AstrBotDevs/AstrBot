import copy
from sys import maxsize

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core import t
from astrbot.core.utils.session_waiter import (
    FILTERS,
    USER_SESSIONS,
    SessionController,
    SessionWaiter,
    session_waiter,
)


class Main(Star):
    """会话控制"""

    def __init__(self, context: Context) -> None:
        super().__init__(context)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize)
    async def handle_session_control_agent(self, event: AstrMessageEvent) -> None:
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
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            p_settings = cfg["platform_settings"]
            wake_prefix = cfg.get("wake_prefix", [])
            if len(messages) == 1:
                if (
                    isinstance(messages[0], Comp.At)
                    and str(messages[0].qq) == str(event.get_self_id())
                    and p_settings.get("empty_mention_waiting", True)
                ) or (
                    isinstance(messages[0], Comp.Plain)
                    and messages[0].text.strip() in wake_prefix
                ):
                    if p_settings.get("empty_mention_waiting_need_reply", True):
                        try:
                            # 尝试使用 LLM 生成更生动的回复
                            # func_tools_mgr = self.context.get_llm_tool_manager()

                            # 获取用户当前的对话信息
                            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                                event.unified_msg_origin,
                            )
                            conversation = None

                            if curr_cid:
                                conversation = await self.context.conversation_manager.get_conversation(
                                    event.unified_msg_origin,
                                    curr_cid,
                                )
                            else:
                                # 创建新对话
                                curr_cid = await self.context.conversation_manager.new_conversation(
                                    event.unified_msg_origin,
                                    platform_id=event.get_platform_id(),
                                )

                            # 使用 LLM 生成回复
                            yield event.request_llm(
                                prompt=(
                                    "注意，你正在社交媒体上中与用户进行聊天，用户只是通过@来唤醒你，但并未在这条消息中输入内容，他可能会在接下来一条发送他想发送的内容。"
                                    "你友好地询问用户想要聊些什么或者需要什么帮助，回复要符合人设，不要太过机械化。"
                                    "请注意，你仅需要输出要回复用户的内容，不要输出其他任何东西"
                                ),
                                session_id=curr_cid,
                                contexts=[],
                                system_prompt="",
                                conversation=conversation,
                            )
                        except Exception as e:
                            logger.error(
                                t(
                                    "builtin-stars-session-controller-llm-response-failed",
                                    error=str(e),
                                )
                            )
                            # LLM 回复失败，使用原始预设回复
                            yield event.plain_result(
                                t(
                                    "builtin-stars-session-controller-empty-mention-fallback-reply"
                                )
                            )

                    @session_waiter(60)
                    async def empty_mention_waiter(
                        controller: SessionController,
                        event: AstrMessageEvent,
                    ) -> None:
                        event.message_obj.message.insert(
                            0,
                            Comp.At(qq=event.get_self_id(), name=event.get_self_id()),
                        )
                        new_event = copy.copy(event)
                        # 重新推入事件队列
                        self.context.get_event_queue().put_nowait(new_event)
                        event.stop_event()
                        controller.stop()

                    try:
                        await empty_mention_waiter(event)
                    except TimeoutError as _:
                        pass
                    except Exception as e:
                        yield event.plain_result(
                            t(
                                "builtin-stars-session-controller-empty-mention-handler-error",
                                error=str(e),
                            )
                        )
                    finally:
                        event.stop_event()
        except Exception as e:
            logger.error(
                t(
                    "builtin-stars-session-controller-handle-empty-mention-error",
                    error=str(e),
                )
            )
