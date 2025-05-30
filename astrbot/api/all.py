"""
astrbot.api.all
该模块提供AstrBot全部的api接口, 如果不清楚从哪里导入, 可以从这个模块导入
⚠️ 标记为已弃用, 不会更新, 请使用 astrbot.api 导入
"""

# astrbot.api
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot import logger
from astrbot.core import html_renderer
from astrbot.core import sp
from astrbot.core.star.register import register_llm_tool as llm_tool

# astrbot.api.message_components
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
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    MessageChain,
    CommandResult,
    EventResultType,
    ResultContentType,
)
from astrbot.core.platform import AstrMessageEvent

# star register
from astrbot.core.star.register import (
    register_command as command,
    register_command_group as command_group,
    register_event_message_type as event_message_type,
    register_regex as regex,
    register_platform_adapter_type as platform_adapter_type,
)
from astrbot.core.star.filter.event_message_type import (
    EventMessageTypeFilter,
    EventMessageType,
)
from astrbot.core.star.filter.platform_adapter_type import (
    PlatformAdapterTypeFilter,
    PlatformAdapterType,
)
from astrbot.core.star.register import (
    register_star as register,  # 注册插件（Star）
)
from astrbot.core.star import Context, Star
from astrbot.core.star.config import *


# provider
from astrbot.core.provider import Provider, Personality, ProviderMetaData

# platform
from astrbot.core.platform import (
    AstrMessageEvent,
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)

from astrbot.core.platform.register import register_platform_adapter
