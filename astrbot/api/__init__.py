"""
astrbot.api
该模块提供最常用最核心的一些接口
"""

# astrbot.api
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot import logger
from astrbot.core import html_renderer
from astrbot.core import sp

# 原: astrbot.api.message_components (已弃用)
# 现: astrbot.api.event.message.MessageComponents
from .message_components import (
    ComponentType,  # 枚举所有消息类型名
    BaseMessageComponent,  # 消息类型基类, 如果你需要适配新的消息类型, 可以选择继承此类
    # 常用消息组件
    Plain,  # 纯文本消息
    Face,  # QQ表情
    Record,  # 语音
    Video,  # 视频
    At,  # @
    AtAll,  # @全体成员
    Node,  # 转发节点
    Nodes,  # 多个转发节点
    Poke,  # QQ 戳一戳
    Image,  # 图片
    Reply,  # 回复消息
    Forward,  # 转发消息
    File,  # 文件
    # 其他消息组件
    Music,  # 音乐分享
    Json,  # Json 消息
    TTS,  # TTS
    Unknown,  # 未知类型
    # 特定平台消息组件
    ## QQ
    Dice,  # 骰子
    Contact,  # 推荐好友/群
    RPS,  # 猜拳魔法表情
    ## 微信
    WechatEmoji,  # 微信表情
    # 仅接收
    Share,  # 链接分享
    Shake,  # 私聊窗口抖动
)

# astrbot.api.event
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    MessageChain,
    CommandResult,
    EventResultType,
    ResultContentType,
)

# astrbot.api.platform
from astrbot.core.platform import (
    AstrBotMessage,  # AstrBot 消息, 其实应当出现在事件 api 下, 因为它是事件的一部分, 此处保留向后兼容
    MessageMember,  # AstrBot 消息成员, 其实应当出现在事件 api 下, 此处保留向后兼容
    MessageType,  # AstrBot 消息类型, 其实应当出现在事件 api 下, 此处保留向后兼容
    Platform,
    PlatformMetadata,
    Group,  # 一个群聊
)
from astrbot.core.platform.register import register_platform_adapter

# astrbot.api.provider
from astrbot.core.provider import Provider, STTProvider, Personality
from astrbot.core.provider.entities import (
    ProviderRequest,
    ProviderType,
    ProviderMetaData,
    LLMResponse,
)

# astrbot.api.star
from astrbot.core.star.register import (
    register_star as register,  # 注册插件（Star）
)
from astrbot.core.star import Context, Star, StarTools
from astrbot.core.star.config import load_config, put_config, update_config  # 已弃用

# 原: astrbot.api.event.filter (已弃用)
# 现: astrbot.api.star.register
from astrbot.core.star.register import (
    register_command as command,  # 注册命令
    register_command_group as command_group,  # 注册命令组
    register_event_message_type as event_message_type,  # 注册监听器: 事件消息类型
    register_regex as regex,  # 注册监听器: 正则表达式
    register_platform_adapter_type as platform_adapter_type,  # 注册监听器: 平台适配器类型
    register_permission_type as permission_type,  # 注册监听器: 权限类型
    register_custom_filter as custom_filter,  # 注册监听器: 自定义过滤器
    register_on_astrbot_loaded as on_astrbot_loaded,  # 注册触发器: AstrBot 加载完成时
    register_on_llm_request as on_llm_request,  # 注册触发器: LLM 请求时
    register_on_llm_response as on_llm_response,  # 注册触发器: LLM 响应时
    register_on_decorating_result as on_decorating_result,  # 注册触发器: 装饰结果时
    register_after_message_sent as after_message_sent,  # 注册触发器: 消息发送后
    register_llm_tool as llm_tool,  # 注册 LLM 工具
    register_agent as agent, # 注册 agent
)

# 监听器所用到的过滤器和类型
from astrbot.core.star.filter.event_message_type import (
    EventMessageTypeFilter,
    EventMessageType,
)
from astrbot.core.star.filter.platform_adapter_type import (
    PlatformAdapterTypeFilter,
    PlatformAdapterType,
)
from astrbot.core.star.filter.permission import PermissionTypeFilter, PermissionType
from astrbot.core.star.filter.custom_filter import CustomFilter

# agent
from astrbot.core.agent.tool import ToolSet, FunctionTool
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor

__all__ = [
    "AstrBotConfig",
    "logger",
    "html_renderer",
    "llm_tool",
    "sp",
    "ComponentType",
    "BaseMessageComponent",
    "Plain",
    "Face",
    "Record",
    "Video",
    "At",
    "AtAll",
    "Node",
    "Nodes",
    "Poke",
    "Image",
    "Reply",
    "Forward",
    "File",
    "Music",
    "Json",
    "TTS",
    "Unknown",
    "Dice",
    "Contact",
    "RPS",
    "WechatEmoji",
    "Share",
    "Shake",
    "AstrMessageEvent",
    "MessageEventResult",
    "MessageChain",
    "CommandResult",
    "EventResultType",
    "ResultContentType",
    "AstrBotMessage",
    "MessageMember",
    "MessageType",
    "Platform",
    "PlatformMetadata",
    "Group",
    "register_platform_adapter",
    "Provider",
    "STTProvider",
    "Personality",
    "ProviderRequest",
    "ProviderType",
    "ProviderMetaData",
    "LLMResponse",
    "register",
    "Context",
    "Star",
    "StarTools",
    "load_config",
    "put_config",
    "update_config",
    "command",
    "command_group",
    "event_message_type",
    "regex",
    "platform_adapter_type",
    "permission_type",
    "custom_filter",
    "on_astrbot_loaded",
    "on_llm_request",
    "on_llm_response",
    "on_decorating_result",
    "after_message_sent",
    "EventMessageTypeFilter",
    "EventMessageType",
    "PlatformAdapterTypeFilter",
    "PlatformAdapterType",
    "PermissionTypeFilter",
    "PermissionType",
    "CustomFilter",
    "agent",
    "ToolSet",
    "FunctionTool",
    "BaseFunctionToolExecutor",
]
