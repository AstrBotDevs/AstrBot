"""
astrbot.api.event.message.message_components
该模块提供一个事件中的消息的构成组件, 一个事件拥有一个消息链, 消息链是一个列表, 其中的元素就是这些消息组件
"""

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
