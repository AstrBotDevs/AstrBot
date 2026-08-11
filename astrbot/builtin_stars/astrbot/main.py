import copy
import traceback
from collections.abc import Iterable
from sys import maxsize

import astrbot.api.message_components as Comp
from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.provider import ProviderRequest

from .group_chat_context import GroupChatContext


def _iter_message_components(event: AstrMessageEvent):
    messages = getattr(getattr(event, "message_obj", None), "message", None)
    if not isinstance(messages, Iterable) or isinstance(messages, (str, bytes)):
        return ()
    return tuple(messages)


class Main(star.Star):
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context
        self.group_chat_context = None
        try:
            self.group_chat_context = GroupChatContext(self.context)
        except Exception as e:
            logger.error(f"group chat context init failed: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize)
    async def handle_session_control_agent(self, event: AstrMessageEvent) -> None:
        """会话控制代理"""
        if await self.context.messages.dispatch_waiter(event):
            event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize - 1)
    async def handle_empty_mention(self, event: AstrMessageEvent):
        """处理只有一个 @ 或仅有唤醒前缀的消息，并等待用户下一条内容。"""
        try:
            messages = event.get_messages()
            cfg = self.context.config.get(umo=event.unified_msg_origin)
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
                    curr_cid = await self.context.conversations.current_id(
                        event.unified_msg_origin,
                    )
                    conversation = None

                    if curr_cid:
                        conversation = await self.context.conversations.get(
                            event.unified_msg_origin,
                            curr_cid,
                        )
                    else:
                        curr_cid = await self.context.conversations.create(
                            event.unified_msg_origin,
                            platform_id=event.get_platform_id(),
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

            async def empty_mention_waiter(
                controller,
                event: AstrMessageEvent,
            ) -> None:
                if not event.message_str or not event.message_str.strip():
                    return
                event.message_obj.message.insert(
                    0,
                    Comp.At(qq=event.get_self_id(), name=event.get_self_id()),
                )
                new_event = copy.copy(event)
                self.context.messages.submit(new_event)
                event.stop_event()
                controller.stop()

            try:
                await self.context.messages.wait_for(
                    event,
                    empty_mention_waiter,
                    timeout_seconds=60,
                )
            except TimeoutError:
                pass
            except Exception as e:
                yield event.plain_result("发生错误，请联系管理员: " + str(e))
            finally:
                event.stop_event()
        except Exception as e:
            logger.error("handle_empty_mention error: " + str(e))

    def group_context_enabled(self, event: AstrMessageEvent):
        group_context_settings = self.context.config.get(umo=event.unified_msg_origin)[
            "provider_ltm_settings"
        ]
        return (
            group_context_settings["group_icl_enable"]
            or group_context_settings["active_reply"]["enable"]
        )

    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """群聊上下文感知"""
        message_components = _iter_message_components(event)
        has_image_or_plain = False
        for comp in message_components:
            if isinstance(comp, Plain) or isinstance(comp, Image):
                has_image_or_plain = True
                break

        group_context_enabled = False
        if self.group_chat_context:
            try:
                group_context_enabled = self.group_context_enabled(event)
            except Exception as e:
                logger.error(f"group chat context: {e}")

        if group_context_enabled and self.group_chat_context and has_image_or_plain:
            need_active = await self.group_chat_context.need_active_reply(event)

            group_icl_enable = self.context.config.get(umo=event.unified_msg_origin)[
                "provider_ltm_settings"
            ]["group_icl_enable"]
            if group_icl_enable:
                # Skip recording if a command handler matched (e.g. /conversation reset,
                # /help, /conversation create). Slash commands are bot instructions, not group
                # chat context that should be injected into future LLM requests.
                if not event.get_extra("handlers_parsed_params", {}):
                    try:
                        await self.group_chat_context.handle_message(event)
                    except Exception as e:
                        logger.error(e)

            if need_active:
                provider = self.context.models.using_chat(event.unified_msg_origin)
                if not provider:
                    logger.error("未找到任何 LLM 提供商。请先配置。无法主动回复")
                    return
                try:
                    session_curr_cid = await self.context.conversations.current_id(
                        event.unified_msg_origin,
                    )

                    if not session_curr_cid:
                        logger.error(
                            "当前未处于对话状态，无法主动回复，请确保 平台设置->会话隔离(unique_session) 未开启，并使用 /conversation create 创建一个会话。",
                        )
                        return

                    conv = await self.context.conversations.get(
                        event.unified_msg_origin,
                        session_curr_cid,
                    )

                    if not conv:
                        logger.error("未找到对话，无法主动回复")
                        return

                    prompt = event.message_str
                    image_urls = []
                    for comp in message_components:
                        if isinstance(comp, Image):
                            try:
                                image_urls.append(await comp.convert_to_file_path())
                            except Exception:
                                logger.exception("主动回复处理图片失败")

                    yield event.request_llm(
                        prompt=prompt,
                        session_id=event.session_id,
                        image_urls=image_urls,
                        conversation=conv,
                    )
                except Exception as e:
                    logger.error(traceback.format_exc())
                    logger.error(f"主动回复失败: {e}")

    @filter.on_llm_request()
    async def decorate_llm_req(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """在请求 LLM 前注入人格信息、Identifier、时间、回复内容等 System Prompt"""
        if self.group_chat_context and self.group_context_enabled(event):
            try:
                await self.group_chat_context.on_req_llm(event, req)
            except Exception as e:
                logger.error(f"group chat context: {e}")

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent) -> None:
        """消息发送后处理"""
        if self.group_chat_context and self.group_context_enabled(event):
            try:
                clean_session = event.get_extra("_clean_group_context_session", False)
                if clean_session:
                    await self.group_chat_context.remove_session(event)
            except Exception as e:
                logger.error(f"group chat context: {e}")
