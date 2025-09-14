import re
from collections import defaultdict
from typing import AsyncGenerator, Union
from astrbot import logger
from astrbot.core.message.components import At, AtAll, Reply
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from ..context import PipelineContext
from ..stage import Stage, register_stage


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

    def _find_command_filter(self, handler):
        """查找command filter

        Args:
            handler (StarHandlerMetadata): handler 元数据对象
        Returns:
            CommandFilter | None: 找到则返回 CommandFilter 对象，否则返回 None
        """
        for f in handler.event_filters:
            if hasattr(f, "command_name"):
                return f
        return None

    async def _find_best_command_handlers(self, command_handlers, event):
        """查找最长匹配的handler

        Args:
            command_handlers (List[Tuple[StarHandlerMetadata, CommandFilter]]): 候选的指令 handler 列表
            event (AstrMessageEvent): 消息事件对象
        Returns:
            StarHandlerMetadata | None: 找到则返回 handler 元数据对象，否则返回 None
        """

        if not event.is_at_or_wake_command:
            return None

        message_str = re.sub(r"\s+", " ", event.get_message_str().strip())
        best_match = None
        best_length = 0
        best_params = None

        # 找到所有可能的匹配
        for handler, command_filter in command_handlers:
            match_result = self._match_command(command_filter, message_str, event)
            if match_result:
                match_length, parsed_params = match_result
                if match_length > best_length:
                    best_length = match_length
                    best_match = handler
                    best_params = parsed_params

        if best_match:
            # 解析的参数
            if best_params is not None:
                event.set_extra("parsed_params", best_params)

            # 还需要执行完整的filter检查
            result = await self._check_handler_filters(best_match, event)
            if result == "activate":
                return best_match
            elif result == "permission_error":
                raise PermissionError("权限不足")

        return None

    def _match_command(self, command_filter, message_str, event):
        """匹配指令

        Args:
            command_filter (CommandFilter): 指令过滤器对象
            message_str (str): 消息字符串
            event (AstrMessageEvent): 消息事件对象
        Returns:
            Tuple[int, dict] | None: 如果匹配成功，返回 (匹配长度, 解析参数)；否则返回 None
        """
        # 检查自定义过滤器
        if not command_filter.custom_filter_ok(event, self.ctx.astrbot_config):
            return None

        candidates = [command_filter.command_name] + list(command_filter.alias)

        for candidate in candidates:
            for parent_command_name in command_filter.parent_command_names:
                if parent_command_name:
                    full_command = f"{parent_command_name} {candidate}"
                else:
                    full_command = candidate

                matched_params = None
                if message_str == full_command:
                    # 完全匹配，无参数
                    try:
                        matched_params = command_filter.validate_and_convert_params(
                            [], command_filter.handler_params
                        )
                        return (len(full_command), matched_params)
                    except ValueError:
                        continue
                elif message_str.startswith(full_command + " "):
                    # 前缀匹配，有参数
                    param_str = message_str[len(full_command) :].strip()
                    params_list = [p for p in param_str.split(" ") if p]
                    try:
                        matched_params = command_filter.validate_and_convert_params(
                            params_list, command_filter.handler_params
                        )
                        return (len(full_command), matched_params)
                    except ValueError:
                        continue

        return None

    async def _check_handler_filters(self, handler, event):
        """检查处理器的所有过滤器

        Args:
            handler (StarHandlerMetadata): handler 元数据对象
            event (AstrMessageEvent): 消息事件对象
        Returns:
            "activate": 通过所有检查，可以激活
            "skip": 跳过（权限不足但不报错，或其他过滤器不通过）
            "permission_error": 权限不足且需要报错
        """
        permission_not_pass = False
        permission_filter_raise_error = False

        for filter_obj in handler.event_filters:
            try:
                if isinstance(filter_obj, PermissionTypeFilter):
                    if not filter_obj.filter(event, self.ctx.astrbot_config):
                        permission_not_pass = True
                        permission_filter_raise_error = filter_obj.raise_error
                else:
                    if not filter_obj.filter(event, self.ctx.astrbot_config):
                        return "skip"
            except Exception as e:
                await event.send(
                    MessageEventResult().message(
                        f"插件 {star_map[handler.handler_module_path].name}: {e}"
                    )
                )
                event.stop_event()
                return "skip"

        # 处理权限检查结果
        if permission_not_pass:
            if not permission_filter_raise_error:
                return "skip"

            if self.no_permission_reply:
                await event.send(
                    MessageChain().message(
                        f"您(ID: {event.get_sender_id()})的权限不足以使用此指令。通过 /sid 获取 ID 并请管理员添加。"
                    )
                )
            logger.info(
                f"触发 {star_map[handler.handler_module_path].name} 时, 用户(ID={event.get_sender_id()}) 权限不足。"
            )
            return "permission_error"

        return "activate"

    def _detect_command_conflicts(self, command_handlers):
        """检测指令冲突

        Args:
            command_handlers (List[Tuple[StarHandlerMetadata, CommandFilter]]): 候选的指令 handler 列表
        """
        # 完整指令名 -> [(handler, plugin_name)] 映射
        command_map = defaultdict(list)

        for handler, command_filter in command_handlers:
            star_metadata = star_map.get(handler.handler_module_path)
            if star_metadata:
                plugin_name = star_metadata.name
            else:
                plugin_name = "不知道是哪个插件"

            # 所有可能的指令名
            candidates = [command_filter.command_name] + list(command_filter.alias)

            for candidate in candidates:
                for parent_command_name in command_filter.parent_command_names:
                    if parent_command_name:
                        full_command = f"{parent_command_name} {candidate}"
                    else:
                        full_command = candidate

                    command_map[full_command].append((handler, plugin_name, candidate))

        # 检查冲突
        conflicts_detected = False
        for command_name, handlers_list in command_map.items():
            if len(handlers_list) > 1:
                if not conflicts_detected:
                    logger.warning("检测到指令名冲突！")
                    conflicts_detected = True

                conflict_info = []
                for handler, plugin_name, original_command in handlers_list:
                    conflict_info.append(
                        f"插件 '{plugin_name}' 的指令 '{original_command}'"
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
        handlers_parsed_params = {}

        # 将 plugins_name 设置到 event 中
        enabled_plugins_name = self.ctx.astrbot_config.get("plugin_set", ["*"])
        if enabled_plugins_name == ["*"]:
            event.plugins_name = None
        else:
            event.plugins_name = enabled_plugins_name
        logger.debug(f"enabled_plugins_name: {enabled_plugins_name}")

        command_handlers = []
        non_command_handlers = []

        for handler in star_handlers_registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent, plugins_name=event.plugins_name
        ):
            if len(handler.event_filters) == 0:
                continue

            # 检查是否为指令
            command_filter = self._find_command_filter(handler)
            if command_filter:
                command_handlers.append((handler, command_filter))
            else:
                non_command_handlers.append(handler)

        self._detect_command_conflicts(command_handlers)

        # 指令
        command_matched = False
        try:
            best_command_handler = await self._find_best_command_handlers(
                command_handlers, event
            )
            if best_command_handler:
                activated_handlers.append(best_command_handler)
                if "parsed_params" in event.get_extra():
                    handlers_parsed_params[best_command_handler.handler_full_name] = (
                        event.get_extra("parsed_params")
                    )
                command_matched = True
                is_wake = True
                event.is_wake = True
        except PermissionError:
            event.stop_event()
            return

        event._extras.pop("parsed_params", None)

        # 非指令
        if not command_matched:
            for handler in non_command_handlers:
                result = await self._check_handler_filters(handler, event)
                if result == "activate":
                    activated_handlers.append(handler)
                    if "parsed_params" in event.get_extra():
                        handlers_parsed_params[handler.handler_full_name] = (
                            event.get_extra("parsed_params")
                        )
                    is_wake = True
                    event.is_wake = True
                elif result == "permission_error":
                    event.stop_event()
                    return

        event._extras.pop("parsed_params", None)

        # 根据会话配置过滤插件处理器
        activated_handlers = SessionPluginManager.filter_handlers_by_session(
            event, activated_handlers
        )

        event.set_extra("activated_handlers", activated_handlers)
        event.set_extra("handlers_parsed_params", handlers_parsed_params)

        if not is_wake:
            event.stop_event()
