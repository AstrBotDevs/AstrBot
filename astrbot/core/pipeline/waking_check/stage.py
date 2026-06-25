# 导入必要的类型和模块
from collections.abc import AsyncGenerator, Callable

from astrbot import logger
from astrbot.core.message.components import At, AtAll, Reply
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry

from ..context import PipelineContext
from ..stage import Stage, register_stage

# 不同平台的唯一会话ID构建器映射表
# 用于在多平台环境下为每个用户-群组组合创建唯一的会话标识
# 键：平台名称，值：lambda函数，接收事件对象，返回唯一会话ID字符串或None
UNIQUE_SESSION_ID_BUILDERS: dict[str, Callable[[AstrMessageEvent], str | None]] = {
    "aiocqhttp": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",  # QQ平台：发送者ID_群组ID
    "slack": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",      # Slack平台：发送者ID_群组ID
    "dingtalk": lambda e: e.get_sender_id(),                           # 钉钉平台：仅使用发送者ID
    "qq_official": lambda e: e.get_sender_id(),                        # QQ官方平台：仅使用发送者ID
    "qq_official_webhook": lambda e: e.get_sender_id(),                # QQ官方Webhook：仅使用发送者ID
    "lark": lambda e: f"{e.get_sender_id()}%{e.get_group_id()}",       # 飞书平台：发送者ID%群组ID
    "misskey": lambda e: f"{e.get_session_id()}_{e.get_sender_id()}",  # Misskey平台：会话ID_发送者ID
    "matrix": lambda e: f"{e.get_sender_id()}_{e.get_group_id() or e.get_session_id()}",  # Matrix平台：发送者ID_群组ID或会话ID
}


def build_unique_session_id(event: AstrMessageEvent) -> str | None:
    """
    根据事件所属平台构建唯一的会话ID
    
    功能：从不同平台的消息事件中提取信息，构建唯一的会话标识符
    用于实现跨平台的统一会话管理
    
    Args:
        event: Astrbot消息事件对象
        
    Returns:
        str | None: 成功构建的会话ID字符串，如果平台不支持则返回None
    """
    # 获取当前消息所属平台名称
    platform = event.get_platform_name()
    # 根据平台名称查找对应的构建器函数
    builder = UNIQUE_SESSION_ID_BUILDERS.get(platform)
    # 如果找到构建器就调用它，否则返回None
    return builder(event) if builder else None


@register_stage  # 注册为管道阶段，使其能被管道自动调用
class WakingCheckStage(Stage):
    """
    消息管道唤醒检查阶段
    
    功能：判断机器人是否应该被唤醒并响应消息，是消息处理管道的早期阶段
    检查是否需要唤醒。唤醒机器人有如下几点条件：

    1. 机器人被 @ 了（群聊中被@）
    2. 机器人的消息被提到了（使用回复功能）
    3. 以 wake_prefix 前缀开头，并且消息没有以 At 消息段开头
    4. 插件（Star）的 handler filter 通过（插件自定义的过滤条件）
    5. 私聊情况下，位于 admins_id 列表中的管理员的消息（在白名单阶段中）
    
    该阶段负责：唯一会话设置、机器人自身消息过滤、唤醒判断、权限检查、插件处理器激活
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        """
        初始化唤醒检查阶段，从配置中加载各种设置参数
        
        功能：在管道启动时进行一次性的初始化配置加载
        从上下文配置中读取各种与唤醒相关的设置项
        
        Args:
            ctx (PipelineContext): 消息管道上下文对象, 包括全局配置和插件管理器
        """
        # 保存上下文对象的引用
        self.ctx = ctx
        # 获取无权限回复设置：当用户无权限时是否发送提示消息
        self.no_permission_reply = self.ctx.astrbot_config["platform_settings"].get(
            "no_permission_reply",
            True,
        )
        # 获取私聊消息是否需要唤醒前缀的设置
        # 如果为True，则私聊也需要使用唤醒前缀才能触发机器人
        self.friend_message_needs_wake_prefix = self.ctx.astrbot_config[
            "platform_settings"
        ].get("friend_message_needs_wake_prefix", False)
        # 获取是否忽略机器人自己发送的消息的设置
        # 防止机器人响应自己发出的消息造成死循环
        self.ignore_bot_self_message = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_bot_self_message",
            False,
        )
        # 获取是否忽略@全体成员消息的设置
        self.ignore_at_all = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_at_all",
            False,
        )
        # 获取是否禁用内置命令的设置
        self.disable_builtin_commands = self.ctx.astrbot_config.get(
            "disable_builtin_commands", False
        )
        # 获取平台设置的完整配置
        platform_settings = self.ctx.astrbot_config.get("platform_settings", {})
        # 获取是否启用唯一会话的设置
        self.unique_session = platform_settings.get("unique_session", False)

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        """
        处理消息事件的核心方法：执行唤醒检查流程
        
        功能：实现完整的唤醒检查逻辑，包括：
        1. 设置唯一会话ID
        2. 过滤机器人自身消息
        3. 设置发送者身份（管理员/普通用户）
        4. 检查是否需要唤醒（@、回复、前缀、私聊等）
        5. 检查插件处理器过滤条件
        6. 管理激活的处理器列表
        
        Args:
            event: Astrbot消息事件对象
            
        Returns:
            None | AsyncGenerator[None, None]: 如果消息被停止则返回None
        """
        # ===== 第一步：唯一会话处理 =====
        # 应用唯一会话设置：如果启用了唯一会话且是群组消息
        if self.unique_session and event.message_obj.type == MessageType.GROUP_MESSAGE:
            # 为当前事件构建唯一会话ID
            sid = build_unique_session_id(event)
            if sid:
                # 设置事件的会话ID，实现会话隔离
                event.session_id = sid

        # ===== 第二步：过滤机器人自身消息 =====
        # 检查是否需要忽略机器人自己发送的消息
        if (
            self.ignore_bot_self_message  # 配置了忽略自身消息
            and event.get_self_id() == event.get_sender_id()  # 发送者ID等于机器人自身ID
        ):
            # 停止事件处理，防止机器人响应自己的消息
            event.stop_event()
            return

        # ===== 第三步：设置发送者身份 =====
        # 去除消息字符串首尾空白字符
        event.message_str = event.message_str.strip()
        # 检查发送者是否在管理员列表中
        for admin_id in self.ctx.astrbot_config["admins_id"]:
            # 将发送者ID与管理员ID进行字符串比较
            if str(event.get_sender_id()) == admin_id:
                # 设置为管理员角色
                event.role = "admin"
                break

        # ===== 第四步：检查唤醒条件 =====
        # 获取唤醒前缀列表，例如：['/', '!', '#' 等]
        wake_prefixes = self.ctx.astrbot_config["wake_prefix"]
        # 获取消息中的所有消息段（可以包含文本、@、图片等）
        messages = event.get_messages()
        # 唤醒标志位，初始为False
        is_wake = False
        # 遍历所有唤醒前缀进行匹配
        for wake_prefix in wake_prefixes:
            # 检查消息是否以某个唤醒前缀开头
            if event.message_str.startswith(wake_prefix):
                # 特殊处理：群聊中@某人但不是@机器人或@全体成员的情况
                if (
                    not event.is_private_chat()  # 不是私聊
                    and isinstance(messages[0], At)  # 第一个消息段是@消息
                    and str(messages[0].qq) != str(event.get_self_id())  # @的不是机器人自己
                    and str(messages[0].qq) != "all"  # @的不是全体成员
                ):
                    # 如果是群聊，且第一个消息段是 At 消息，但不是 At 机器人或 At 全体成员，则不唤醒
                    # 跳出循环，不设置唤醒
                    break
                # 标记为已唤醒
                is_wake = True
                # 设置事件的唤醒相关标志
                event.is_at_or_wake_command = True
                event.is_wake = True
                # 移除消息中的唤醒前缀，提取实际命令内容
                event.message_str = event.message_str[len(wake_prefix):].strip()
                break
        
        # 如果没有通过前缀唤醒，检查其他唤醒方式
        if not is_wake:
            # 检查消息段中是否有@消息、@全体成员消息或引用了机器人的消息
            for message in messages:
                # 条件1：被@了且@的是机器人
                if (
                    isinstance(message, At)
                    and (str(message.qq) == str(event.get_self_id()))
                ):
                    is_wake = True
                    event.is_wake = True
                    wake_prefix = ""  # 清空前缀
                    event.is_at_or_wake_command = True
                    break
                # 条件2：有人@全体成员且没有配置忽略
                elif (isinstance(message, AtAll) and not self.ignore_at_all):
                    is_wake = True
                    event.is_wake = True
                    wake_prefix = ""  # 清空前缀
                    event.is_at_or_wake_command = True
                    break
                # 条件3：有人回复了机器人的消息
                elif (
                    isinstance(message, Reply)
                    and str(message.sender_id) == str(event.get_self_id())
                ):
                    is_wake = True
                    event.is_wake = True
                    wake_prefix = ""  # 清空前缀
                    event.is_at_or_wake_command = True
                    break
            
            # 条件4：如果是私聊且配置中私聊不需要唤醒前缀
            if event.is_private_chat() and not self.friend_message_needs_wake_prefix:
                is_wake = True
                event.is_wake = True
                event.is_at_or_wake_command = True
                wake_prefix = ""  # 清空前缀

        # ===== 第五步：检查插件的处理器过滤条件 =====
        # 存储被激活的处理器列表
        activated_handlers = []
        # 存储已经解析了参数的处理器（注册了指令的 handler）
        handlers_parsed_params = {}

        # 设置事件的插件名称列表
        # 从配置中获取已启用的插件名称
        enabled_plugins_name = self.ctx.astrbot_config.get("plugin_set", ["*"]) # ["*"]获取插件设置
        if enabled_plugins_name == ["*"]:
            # 如果是通配符 "*"，则表示所有插件都启用
            event.plugins_name = None
        else:
            # 否则指定具体的启用插件列表
            event.plugins_name = enabled_plugins_name
        # 记录调试信息
        logger.debug(f"enabled_plugins_name: {enabled_plugins_name}")

        # 遍历所有注册的适配器消息事件处理器
        for handler in star_handlers_registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent,  # 指定事件类型
            plugins_name=event.plugins_name,  # 按插件名称过滤
        ):
            # 检查是否需要禁用内置命令处理器
            if (
                self.disable_builtin_commands  # 配置了禁用内置命令
                and handler.handler_module_path
                == "astrbot.builtin_stars.builtin_commands.main"  # 是内置命令模块
            ):
                # 跳过该处理器
                continue

            # 过滤条件需要满足 AND 逻辑关系（所有条件都必须通过）
            passed = True
            permission_not_pass = False  # 权限未通过的标志
            permission_filter_raise_error = False  # 权限过滤器是否抛出错误的标志
            
            # 如果处理器没有事件过滤器，则跳过
            if len(handler.event_filters) == 0:
                continue

            # 遍历处理器的所有事件过滤器
            for filter in handler.event_filters:
                try:
                    # 检查是否是权限类型过滤器
                    if isinstance(filter, PermissionTypeFilter):
                        # 调用权限过滤器的filter方法
                        if not filter.filter(event, self.ctx.astrbot_config):
                            # 权限未通过
                            permission_not_pass = True
                            # 记录权限过滤器是否需要抛出错误
                            permission_filter_raise_error = filter.raise_error
                    # 其他类型的过滤器
                    elif not filter.filter(event, self.ctx.astrbot_config):
                        # 过滤未通过
                        passed = False
                        break  # 跳出循环，不再检查其他过滤器
                except Exception as e:
                    # 过滤器执行异常，发送错误消息给用户
                    await event.send(
                        MessageEventResult().message(
                            f"插件 {star_map[handler.handler_module_path].name}: {e}",
                        ),
                    )
                    # 停止事件处理
                    event.stop_event()
                    passed = False
                    break
            
            # 如果所有过滤条件都通过了
            if passed:
                # 如果存在权限未通过的情况
                if permission_not_pass:
                    # 如果权限过滤器不需要抛出错误
                    if not permission_filter_raise_error:
                        # 跳过该处理器，继续处理下一个
                        continue
                    # 如果配置了无权限回复
                    if self.no_permission_reply:
                        # 发送无权限提示消息
                        await event.send(
                            MessageChain().message(
                                f"您(ID: {event.get_sender_id()})的权限不足以使用此指令。通过 /sid 获取 ID 并请管理员添加。",
                            ),
                        )
                    # 记录权限不足的日志
                    logger.info(
                        f"触发 {star_map[handler.handler_module_path].name} 时, 用户(ID={event.get_sender_id()}) 权限不足。",
                    )
                    # 停止事件处理
                    event.stop_event()
                    return

                # 标记为已唤醒
                is_wake = True
                event.is_wake = True

                # 检查是否是命令组处理器（包含CommandGroupFilter过滤器）
                is_group_cmd_handler = any(
                    isinstance(f, CommandGroupFilter) for f in handler.event_filters
                )
                # 如果不是命令组处理器，添加到激活列表
                if not is_group_cmd_handler:
                    activated_handlers.append(handler)
                    # 如果有解析的参数，保存到参数字典中
                    if "parsed_params" in event.get_extra(default={}):
                        handlers_parsed_params[handler.handler_full_name] = (
                            event.get_extra("parsed_params")
                        )

            # 清除事件的解析参数，避免影响下一个处理器的判断
            event._extras.pop("parsed_params", None)

        # ===== 第六步：根据会话配置过滤插件处理器 =====
        # 根据会话设置进一步过滤已激活的处理器
        activated_handlers = await SessionPluginManager.filter_handlers_by_session(
            event,
            activated_handlers,
        )

        # ===== 第七步：保存结果到事件对象 =====
        # 将激活的处理器列表和解析的参数保存到事件的额外数据中
        # 供后续管道阶段使用
        event.set_extra("activated_handlers", activated_handlers)
        event.set_extra("handlers_parsed_params", handlers_parsed_params)

        # 如果最终没有唤醒，停止事件处理
        if not is_wake:
            event.stop_event()