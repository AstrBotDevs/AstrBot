import copy
import traceback
from collections.abc import Iterable
from sys import maxsize

import astrbot.api.message_components as Comp
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.core import logger
from astrbot.core.utils.session_waiter import (
    FILTERS,
    USER_SESSIONS,
    SessionController,
    SessionWaiter,
    session_waiter,
)

from .long_term_memory import LongTermMemory


def _iter_message_components(event: AstrMessageEvent):
    messages = getattr(getattr(event, "message_obj", None), "message", None)
    if not isinstance(messages, Iterable) or isinstance(messages, (str, bytes)):
        return ()
    return tuple(messages)


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context
        self.ltm = None
        try:
            self.ltm = LongTermMemory(self.context.astrbot_config_mgr, self.context)
        except BaseException as e:
            logger.error(f"聊天增强 err: {e}")

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
        """处理只有一个 @ 或仅有唤醒前缀的消息，并等待用户下一条内容。"""
        try:
            messages = event.get_messages()
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            p_settings = cfg["platform_settings"]
            wake_prefix = cfg.get("wake_prefix", [])
            if len(messages) != 1:
                return

            is_empty_mention = (
                isinstance(messages[0], Comp.At)
                and str(messages[0].qq) == str(event.get_self_id())
                and p_settings.get("empty_mention_waiting", True)
            )
            is_wake_prefix_only = (
                isinstance(messages[0], Comp.Plain)
                and messages[0].text.strip() in wake_prefix
            )

            if not (is_empty_mention or is_wake_prefix_only):
                return

            if p_settings.get("empty_mention_waiting_need_reply", True):
                try:
                    curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                        event.unified_msg_origin,
                    )
                    conversation = None

                    if curr_cid:
                        conversation = (
                            await self.context.conversation_manager.get_conversation(
                                event.unified_msg_origin,
                                curr_cid,
                            )
                        )
                    else:
                        curr_cid = (
                            await self.context.conversation_manager.new_conversation(
                                event.unified_msg_origin,
                                platform_id=event.get_platform_id(),
                            )
                        )

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
                    logger.error(f"LLM response failed: {e!s}")
                    yield event.plain_result("想要问什么呢？😄")

            @session_waiter(60)
            async def empty_mention_waiter(
                controller: SessionController,
                event: AstrMessageEvent,
            ) -> None:
                if not event.message_str or not event.message_str.strip():
                    return
                event.message_obj.message.insert(
                    0,
                    Comp.At(qq=event.get_self_id(), name=event.get_self_id()),
                )
                new_event = copy.copy(event)
                self.context.get_event_queue().put_nowait(new_event)
                event.stop_event()
                controller.stop()

            try:
                await empty_mention_waiter(event)
            except TimeoutError:
                pass
            except Exception as e:
                yield event.plain_result("发生错误，请联系管理员: " + str(e))
            finally:
                event.stop_event()
        except Exception as e:
            logger.error("handle_empty_mention error: " + str(e))

    def ltm_enabled(self, event: AstrMessageEvent):
        ltmse = self.context.get_config(umo=event.unified_msg_origin)[
            "provider_ltm_settings"
        ]
        return ltmse["group_icl_enable"] or ltmse["active_reply"]["enable"]

    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """群聊记忆增强"""
        message_components = _iter_message_components(event)
        has_image_or_plain = False
        for comp in message_components:
            if isinstance(comp, Plain) or isinstance(comp, Image):
                has_image_or_plain = True
                break

        if self.ltm_enabled(event) and self.ltm and has_image_or_plain:
            need_active = await self.ltm.need_active_reply(event)

            group_icl_enable = self.context.get_config(umo=event.unified_msg_origin)[
                "provider_ltm_settings"
            ]["group_icl_enable"]
            if group_icl_enable:
                """记录对话"""
                try:
                    await self.ltm.handle_message(event)
                except BaseException as e:
                    logger.error(e)

            if need_active:
                """主动回复"""
                provider = self.context.get_using_provider(event.unified_msg_origin)
                if not provider:
                    logger.error("未找到任何 LLM 提供商。请先配置。无法主动回复")
                    return
                try:
                    conv = None
                    session_curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
                        event.unified_msg_origin,
                    )

                    if not session_curr_cid:
                        logger.error(
                            "当前未处于对话状态，无法主动回复，请确保 平台设置->会话隔离(unique_session) 未开启，并使用 /switch 序号 切换或者 /new 创建一个会话。",
                        )
                        return

                    conv = await self.context.conversation_manager.get_conversation(
                        event.unified_msg_origin,
                        session_curr_cid,
                    )

                    prompt = event.message_str
                    image_urls = []
                    for comp in message_components:
                        if isinstance(comp, Image):
                            try:
                                image_urls.append(await comp.convert_to_file_path())
                            except Exception:
                                logger.exception("主动回复处理图片失败")

                    if not conv:
                        logger.error("未找到对话，无法主动回复")
                        return

                    yield event.request_llm(
                        prompt=prompt,
                        session_id=event.session_id,
                        image_urls=image_urls,
                        conversation=conv,
                    )
                except BaseException as e:
                    logger.error(traceback.format_exc())
                    logger.error(f"主动回复失败: {e}")

    @filter.on_llm_request()
    async def decorate_llm_req(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """在请求 LLM 前注入人格信息、Identifier、时间、回复内容等 System Prompt"""
        if self.ltm and self.ltm_enabled(event):
            try:
                await self.ltm.on_req_llm(event, req)
            except BaseException as e:
                logger.error(f"ltm: {e}")

    @filter.on_llm_response()
    async def record_llm_resp_to_ltm(
        self, event: AstrMessageEvent, resp: LLMResponse
    ) -> None:
        """在 LLM 响应后记录对话"""
        if self.ltm and self.ltm_enabled(event):
            try:
                await self.ltm.after_req_llm(event, resp)
            except Exception as e:
                logger.error(f"ltm: {e}")

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent) -> None:
        """消息发送后处理"""
        if self.ltm and self.ltm_enabled(event):
            try:
                clean_session = event.get_extra("_clean_ltm_session", False)
                if clean_session:
                    await self.ltm.remove_session(event)
            except Exception as e:
                logger.error(f"ltm: {e}")
