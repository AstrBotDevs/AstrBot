from collections.abc import Callable

from astrbot import logger
from astrbot.core.i18n import t
from astrbot.core.message.components import At, AtAll, Reply
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.stage import Stage, register_stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry


async def _check_is_advanced_persona(
    ctx: PipelineContext,
    event: AstrMessageEvent,
) -> bool:
    """检查当前会话是否使用高级人格。

    高级人格具有自主思考、主动发言等能力，群聊时不需要唤醒词。
    """
    try:
        persona_manager = ctx.plugin_manager.context.persona_manager
        provider_settings = ctx.astrbot_config.get("provider_settings", {})

        # 解析当前会话使用的人格
        (
            _persona_id,
            persona,
            _force_applied,
            _use_webchat_special,
        ) = await persona_manager.resolve_selected_persona(
            umo=event.session,
            conversation_persona_id=None,
            platform_name=event.get_platform_name(),
            provider_settings=provider_settings,
        )

        if persona and persona.get("is_advanced", False):
            logger.debug(
                f"会话 {event.unified_msg_origin} 使用高级人格 {persona.get('name')}，跳过唤醒词检查"
            )
            return True
    except Exception as e:
        logger.debug(f"检查高级人格时出错: {e}")

    return False


UNIQUE_SESSION_ID_BUILDERS: dict[str, Callable[[AstrMessageEvent], str | None]] = {
    "aiocqhttp": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "slack": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "dingtalk": lambda e: e.get_sender_id(),
    "qq_official": lambda e: e.get_sender_id(),
    "qq_official_webhook": lambda e: e.get_sender_id(),
    "lark": lambda e: f"{e.get_sender_id()}%{e.get_group_id()}",
    "misskey": lambda e: f"{e.get_session_id()}_{e.get_sender_id()}",
    "matrix": lambda e: f"{e.get_sender_id()}_{e.get_group_id() or e.get_session_id()}",
}


def build_unique_session_id(event: AstrMessageEvent) -> str | None:
    platform = event.get_platform_name()
    builder = UNIQUE_SESSION_ID_BUILDERS.get(platform)
    return builder(event) if builder else None


@register_stage
class WakingCheckStage(Stage):
    """检查是否需要唤醒｡唤醒机器人有如下几点条件:

    1. 机器人被 @ 了
    2. 机器人的消息被提到了
    3. 以 command_prefix 指令前缀开头（只触发指令），或以 wake_prefix 唤醒词开头（触发 LLM），
       且消息没有以 At 消息段开头
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
            "no_permission_reply",
            True,
        )
        # 私聊是否需要 wake_prefix 才能唤醒机器人
        self.friend_message_needs_wake_prefix = self.ctx.astrbot_config[
            "platform_settings"
        ].get("friend_message_needs_wake_prefix", False)
        # 是否忽略机器人自己发送的消息
        self.ignore_bot_self_message = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_bot_self_message",
            False,
        )
        self.ignore_at_all = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_at_all",
            False,
        )
        self.disable_builtin_commands = self.ctx.astrbot_config.get(
            "disable_builtin_commands",
            False,
        )
        platform_settings = self.ctx.astrbot_config.get("platform_settings", {})
        self.unique_session = platform_settings.get("unique_session", False)
        # 以下配置在 process() 中每次读取以支持热更新，此处仅作初始化说明
        # wake_prefix, command_prefix, ignore_unknown_prefix_command 通过 self.ctx.astrbot_config 热读取

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None:
        # apply unique session
        if self.unique_session and event.message_obj.type == MessageType.GROUP_MESSAGE:
            sid = build_unique_session_id(event)
            if sid:
                event.session_id = sid

        # ignore bot self message
        if (
            self.ignore_bot_self_message
            and event.get_self_id() == event.get_sender_id()
        ):
            event.stop_event()
            return

        # 设置 sender 身份
        event.message_str = event.message_str.strip()
        for admin_id in self.ctx.astrbot_config["admins_id"]:
            if str(event.get_sender_id()) == admin_id:
                event.role = "admin"
                break

        # 检查是否是高级人格 - 高级人格在群聊时也不需要唤醒词
        is_advanced_persona = await _check_is_advanced_persona(self.ctx, event)
        if is_advanced_persona:
            event.is_advanced_persona = True
            event.is_wake = True
            event.is_at_or_wake_command = True
            logger.debug(
                f"高级人格模式激活，会话 {event.unified_msg_origin} 无需唤醒词"
            )
        # 检查 wake
        # command_prefix 用于匹配指令前缀，与唤醒词（wake_prefix）分开配置。
        # 启动时 check_config_integrity 保证 command_prefix 已有默认值，不会为 None。
        wake_prefixes = self.ctx.astrbot_config["wake_prefix"]
        command_prefixes = self.ctx.astrbot_config.get("command_prefix", wake_prefixes)
        messages = event.get_messages()
        is_wake = False

        # 提取公共的 At 检查逻辑：群聊中首个消息段是 At 他人（非机器人/全体）时不唤醒
        is_at_others = (
            messages
            and not event.is_private_chat()
            and isinstance(messages[0], At)
            and str(messages[0].qq) != str(event.get_self_id())
            and str(messages[0].qq) != "all"
        )
        # 预计算前缀差异标记：command_prefix 非空且与 wake_prefix 不同时，唤醒词只触发 LLM。
        # command_prefix=[] 时不标记，避免唤醒词触发的指令全部失效。
        is_different_prefixes = bool(
            command_prefixes and set(command_prefixes) != set(wake_prefixes)
        )

        # 先检查是否以指令前缀开头（只匹配指令，不触发 LLM 闲聊）
        # command_prefix 与 wake_prefix 相同时，行为与原版一致。
        # command_prefix 与 wake_prefix 不同时，指令前缀只触发指令，唤醒词只触发 LLM。
        is_command_prefix_triggered = False
        for cmd_prefix in command_prefixes:
            if cmd_prefix and event.message_str.startswith(cmd_prefix):
                if is_at_others:
                    break
                is_command_prefix_triggered = True
                event.message_str = event.message_str[len(cmd_prefix) :].strip()
                is_wake = True
                event.is_wake = True
                event.is_at_or_wake_command = True
                break

        # 再检查是否以唤醒词开头（触发 LLM 对话）
        # 若 command_prefix 与 wake_prefix 不同（分开配置），唤醒词分支不触发指令匹配，
        # 只触发 LLM，CommandFilter 会通过 matched_wake_prefix_only 标记跳过指令检查。
        if not is_wake:
            for wake_prefix in wake_prefixes:
                if wake_prefix and event.message_str.startswith(wake_prefix):
                    if is_at_others:
                        # 如果是群聊，且第一个消息段是 At 消息，但不是 At 机器人或 At 全体成员，则不唤醒
                        break
                    is_wake = True
                    event.is_wake = True
                    event.is_at_or_wake_command = True
                    event.message_str = event.message_str[len(wake_prefix) :].strip()
                    if is_different_prefixes:
                        event.set_extra("matched_wake_prefix_only", True)
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

        # 将 plugins_name 设置到 event 中
        enabled_plugins_name = self.ctx.astrbot_config.get("plugin_set", ["*"])
        if enabled_plugins_name == ["*"]:
            # 如果是 *,则表示所有插件都启用
            event.plugins_name = None
        else:
            event.plugins_name = enabled_plugins_name
        logger.debug(f"enabled_plugins_name: {enabled_plugins_name}")

        for handler in star_handlers_registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent,
            plugins_name=event.plugins_name,
        ):
            if (
                self.disable_builtin_commands
                and handler.handler_module_path
                == "astrbot.builtin_stars.builtin_commands.main"
            ):
                continue

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
                    elif not filter.filter(event, self.ctx.astrbot_config):
                        passed = False
                        break
                except Exception as e:
                    await event.send(
                        MessageEventResult().message(
                            t(
                                "pipeline.filter_error",
                                locale=self.ctx.get_current_language(),
                                plugin_name=star_map[handler.handler_module_path].name,
                                error=e,
                            ),
                        ),
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
                                t(
                                    "pipeline.no_permission",
                                    locale=self.ctx.get_current_language(),
                                    sender_id=event.get_sender_id(),
                                ),
                            ),
                        )
                    logger.info(
                        f"触发 {star_map[handler.handler_module_path].name} 时, 用户(ID={event.get_sender_id()}) 权限不足｡",
                    )
                    event.stop_event()
                    return

                is_wake = True
                event.is_wake = True

                is_group_cmd_handler = any(
                    isinstance(f, CommandGroupFilter) for f in handler.event_filters
                )
                if not is_group_cmd_handler:
                    activated_handlers.append(handler)
                    if "parsed_params" in event.get_extra(default={}):
                        handlers_parsed_params[handler.handler_full_name] = (
                            event.get_extra("parsed_params")
                        )

            event._extras.pop("parsed_params", None)

        # 根据会话配置过滤插件处理器
        activated_handlers = await SessionPluginManager.filter_handlers_by_session(
            event,
            activated_handlers,
        )

        event.set_extra("activated_handlers", activated_handlers)
        event.set_extra("handlers_parsed_params", handlers_parsed_params)

        # 若消息以指令前缀开头，但没有任何「带 CommandFilter 的指令 handler」命中，
        # 且 ignore_unknown_prefix_command=True，则静默忽略，不触发 LLM。
        # 默认 False（保持原版行为）；设为 True 后可避免误响应其他机器人的指令（如 /grok）。
        # 注意：部分 handler（如 on_message）没有 CommandFilter，不算指令 handler。
        ignore_unknown = self.ctx.astrbot_config.get("platform_settings", {}).get(
            "ignore_unknown_prefix_command", False
        )
        if is_command_prefix_triggered and ignore_unknown:
            # 检查是否有真正的指令 handler 被激活（含 CommandFilter 或 CommandGroupFilter）
            has_command_handler = any(
                any(
                    isinstance(f, (CommandFilter, CommandGroupFilter))
                    for f in handler.event_filters
                )
                for handler in activated_handlers
            )
            if not has_command_handler:
                event.stop_event()
                return

        if not is_wake:
            event.stop_event()
