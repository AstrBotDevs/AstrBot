from ..stage import Stage, register_stage
from ..context import PipelineContext
from astrbot import logger
from typing import Union, AsyncGenerator
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult, MessageChain
from astrbot.core.message.components import At, AtAll, Reply
from astrbot.core.star.star_handler import star_handlers_registry, EventType
from astrbot.core.star.star import star_map
from astrbot.core.star.filter.permission import PermissionTypeFilter


@register_stage
class WakingCheckStage(Stage):
    """检查是否需要唤醒。唤醒机器人有如下几点条件：

    1. 机器人被 @ 了
    2. 机器人的消息被提到了
    3. 以 wake_prefix 前缀开头，并且消息没有以 At 消息段开头
    4. 插件（Star）的 handler filter 通过
    5. 私聊情况下，位于 admins_id 列表中的管理员的消息（在白名单阶段中）
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化唤醒检查阶段

        Args:
            ctx (PipelineContext): 消息管道上下文对象, 包括配置和插件管理器
        """
        self.ctx = ctx
        self.no_permission_reply = self.ctx.astrbot_config["platform_settings"].get(
            "no_permission_reply", True
        )
        # 私聊是否需要 wake_prefix 才能唤醒机器人
        self.friend_message_needs_wake_prefix = self.ctx.astrbot_config[
            "platform_settings"
        ].get("friend_message_needs_wake_prefix", False)
        # 是否忽略机器人自己发送的消息
        self.ignore_bot_self_message = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_bot_self_message", False
        )
        self.ignore_at_all = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_at_all", False
        )

    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        if (
            self.ignore_bot_self_message
            and event.get_self_id() == event.get_sender_id()
        ):
            # 忽略机器人自己发送的消息
            event.stop_event()
            return
        # 设置 sender 身份
        event.message_str = event.message_str.strip()
        for admin_id in self.ctx.astrbot_config["admins_id"]:
            if str(event.get_sender_id()) == admin_id:
                event.role = "admin"
                break

        # 检查 wake
        wake_prefixes = self.ctx.astrbot_config["wake_prefix"]
        messages = event.get_messages()
        is_wake = False
        for wake_prefix in wake_prefixes:
            if event.message_str.startswith(wake_prefix):
                if (
                    not event.is_private_chat()
                    and isinstance(messages[0], At)
                    and str(messages[0].qq) != str(event.get_self_id())
                    and str(messages[0].qq) != "all"
                ):
                    # 如果是群聊，且第一个消息段是 At 消息，但不是 At 机器人或 At 全体成员，则不唤醒
                    break
                is_wake = True
                event.is_at_or_wake_command = True
                event.is_wake = True
                event.message_str = event.message_str[len(wake_prefix) :].strip()
                break
        if not is_wake:
            # 检查是否有at消息 / at全体成员消息 / 引用了bot的消息
            for message in messages:
                if (
                    (
                        isinstance(message, At)
                        and (str(message.qq) == str(event.get_self_id()))
                    )
                    or (isinstance(message, AtAll) and not self.ignore_at_all)
                    or (
                        isinstance(message, Reply)
                        and str(message.sender_id) == str(event.get_self_id())
                    )
                ):
                    is_wake = True
                    event.is_wake = True
                    wake_prefix = ""
                    event.is_at_or_wake_command = True
                    break
            # 检查是否是私聊
            if event.is_private_chat() and not self.friend_message_needs_wake_prefix:
                is_wake = True
                event.is_wake = True
                event.is_at_or_wake_command = True
                wake_prefix = ""

        # 检查插件的 handler filter
        activated_handlers = []
        handlers_parsed_params = {}  # 注册了指令的 handler

        for handler in star_handlers_registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent
        ):
            # filter 需满足 AND 逻辑关系
            passed = True
            permission_not_pass = False
            permission_filter_raise_error = False
            if len(handler.event_filters) == 0:
                continue

            for filter in handler.event_filters:
                try:
                    if isinstance(filter, PermissionTypeFilter):
                        if not filter.filter(event, self.ctx.astrbot_config):
                            permission_not_pass = True
                            permission_filter_raise_error = filter.raise_error
                    else:
                        if not filter.filter(event, self.ctx.astrbot_config):
                            passed = False
                            break
                except Exception as e:
                    await event.send(
                        MessageEventResult().message(
                            f"插件 {star_map[handler.handler_module_path].name}: {e}"
                        )
                    )
                    event.stop_event()
                    passed = False
                    break
            if passed:
                if permission_not_pass:
                    if not permission_filter_raise_error:
                        # 跳过
                        continue
                    if self.no_permission_reply:
                        await event.send(
                            MessageChain().message(
                                f"您(ID: {event.get_sender_id()})的权限不足以使用此指令。通过 /sid 获取 ID 并请管理员添加。"
                            )
                        )
                    logger.info(
                        f"触发 {star_map[handler.handler_module_path].name} 时, 用户(ID={event.get_sender_id()}) 权限不足。"
                    )
                    event.stop_event()
                    return

                is_wake = True
                event.is_wake = True

                activated_handlers.append(handler)
                if "parsed_params" in event.get_extra():
                    handlers_parsed_params[handler.handler_full_name] = event.get_extra(
                        "parsed_params"
                    )

            event.clear_extra()

        event.set_extra("activated_handlers", activated_handlers)
        event.set_extra("handlers_parsed_params", handlers_parsed_params)

        if not is_wake:
            event.stop_event()
