"""
astrbot.api.platform
该模块包括了 AstrBot 有关不同平台适配器的相关导入
"""

from astrbot.core.platform import (
    AstrMessageEvent,  # AstrBot 事件, 其实应当出现在事件 api 下, 此处保留向后兼容
    AstrBotMessage,  # AstrBot 消息, 其实应当出现在事件 api 下, 因为它是事件的一部分, 此处保留向后兼容
    MessageMember,  # AstrBot 消息成员, 其实应当出现在事件 api 下, 此处保留向后兼容
    MessageType,  # AstrBot 消息类型, 其实应当出现在事件 api 下, 此处保留向后兼容
    Platform,
    PlatformMetadata,
    Group,  # 一个群聊
)

# 注册平台使用的装饰器
from astrbot.core.platform.register import register_platform_adapter

# 消息组件, 其实应当出现在事件 api 下, 因为消息是事件的一部分, 此处保留向后兼容
from astrbot.core.message.components import (
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

__all__ = [
    "AstrMessageEvent",
    "Platform",
    "AstrBotMessage",
    "MessageMember",
    "MessageType",
    "PlatformMetadata",
    "register_platform_adapter",
    "Group",
]
