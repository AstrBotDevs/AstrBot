"""测试辅助函数和工具类。

提供统一的测试辅助工具，减少测试代码重复。
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from astrbot.core.message.components import BaseMessageComponent


class NoopAwaitable:
    """可等待的空操作对象。

    用于 mock 需要返回 awaitable 对象的方法。
    """

    def __await__(self):
        if False:
            yield
        return None


# ============================================================
# 平台配置工厂
# ============================================================


def make_platform_config(platform_type: str, **kwargs) -> dict:
    """平台配置工厂函数。

    Args:
        platform_type: 平台类型 (telegram, discord, aiocqhttp 等)
        **kwargs: 覆盖默认配置的字段

    Returns:
        dict: 平台配置字典
    """
    configs = {
        "telegram": {
            "id": "test_telegram",
            "telegram_token": "test_token_123",
            "telegram_api_base_url": "https://api.telegram.org/bot",
            "telegram_file_base_url": "https://api.telegram.org/file/bot",
            "telegram_command_register": True,
            "telegram_command_auto_refresh": True,
            "telegram_command_register_interval": 300,
            "telegram_media_group_timeout": 2.5,
            "telegram_media_group_max_wait": 10.0,
            "start_message": "Welcome to AstrBot!",
        },
        "discord": {
            "id": "test_discord",
            "discord_token": "test_token_123",
            "discord_proxy": None,
            "discord_command_register": True,
            "discord_guild_id_for_debug": None,
            "discord_activity_name": "Playing AstrBot",
        },
        "aiocqhttp": {
            "id": "test_aiocqhttp",
            "ws_reverse_host": "0.0.0.0",
            "ws_reverse_port": 6199,
            "ws_reverse_token": "test_token",
        },
        "webchat": {
            "id": "test_webchat",
        },
        "wecom": {
            "id": "test_wecom",
            "wecom_corpid": "test_corpid",
            "wecom_secret": "test_secret",
        },
    }
    config = configs.get(platform_type, {"id": f"test_{platform_type}"}).copy()
    config.update(kwargs)
    return config


# ============================================================
# Telegram 辅助函数
# ============================================================


def create_mock_update(
    message_text: str | None = "Hello World",
    chat_type: str = "private",
    chat_id: int = 123456789,
    user_id: int = 987654321,
    username: str = "test_user",
    message_id: int = 1,
    media_group_id: str | None = None,
    photo: list | None = None,
    video: MagicMock | None = None,
    document: MagicMock | None = None,
    voice: MagicMock | None = None,
    sticker: MagicMock | None = None,
    reply_to_message: MagicMock | None = None,
    caption: str | None = None,
    entities: list | None = None,
    caption_entities: list | None = None,
    message_thread_id: int | None = None,
    is_topic_message: bool = False,
):
    """创建模拟的 Telegram Update 对象。

    Args:
        message_text: 消息文本
        chat_type: 聊天类型
        chat_id: 聊天 ID
        user_id: 用户 ID
        username: 用户名
        message_id: 消息 ID
        media_group_id: 媒体组 ID
        photo: 图片列表
        video: 视频对象
        document: 文档对象
        voice: 语音对象
        sticker: 贴纸对象
        reply_to_message: 回复的消息
        caption: 说明文字
        entities: 实体列表
        caption_entities: 说明实体列表
        message_thread_id: 消息线程 ID
        is_topic_message: 是否为主题消息

    Returns:
        MagicMock: 模拟的 Update 对象
    """
    update = MagicMock()
    update.update_id = 1

    # Create message mock
    message = MagicMock()
    message.message_id = message_id
    message.chat = MagicMock()
    message.chat.id = chat_id
    message.chat.type = chat_type
    message.message_thread_id = message_thread_id
    message.is_topic_message = is_topic_message

    # Create user mock
    from_user = MagicMock()
    from_user.id = user_id
    from_user.username = username
    message.from_user = from_user

    # Set message content
    message.text = message_text
    message.media_group_id = media_group_id
    message.photo = photo
    message.video = video
    message.document = document
    message.voice = voice
    message.sticker = sticker
    message.reply_to_message = reply_to_message
    message.caption = caption
    message.entities = entities
    message.caption_entities = caption_entities

    update.message = message
    update.effective_chat = message.chat

    return update


def create_mock_file(file_path: str = "https://api.telegram.org/file/test.jpg"):
    """创建模拟的 Telegram File 对象。

    Args:
        file_path: 文件路径

    Returns:
        MagicMock: 模拟的 File 对象
    """
    file = MagicMock()
    file.file_path = file_path
    file.get_file = AsyncMock(return_value=file)
    return file


# ============================================================
# Discord 辅助函数
# ============================================================


def create_mock_discord_attachment(
    filename: str = "test.txt",
    url: str = "https://cdn.discordapp.com/test.txt",
    content_type: str | None = None,
    size: int = 1024,
):
    """创建模拟的 Discord Attachment 对象。

    Args:
        filename: 文件名
        url: 文件 URL
        content_type: 内容类型
        size: 文件大小

    Returns:
        MagicMock: 模拟的 Attachment 对象
    """
    attachment = MagicMock()
    attachment.filename = filename
    attachment.url = url
    attachment.content_type = content_type
    attachment.size = size
    return attachment


def create_mock_discord_user(
    user_id: int = 123456789,
    name: str = "TestUser",
    display_name: str = "Test User",
    bot: bool = False,
):
    """创建模拟的 Discord User 对象。

    Args:
        user_id: 用户 ID
        name: 用户名
        display_name: 显示名
        bot: 是否为机器人

    Returns:
        MagicMock: 模拟的 User 对象
    """
    user = MagicMock()
    user.id = user_id
    user.name = name
    user.display_name = display_name
    user.bot = bot
    user.mention = f"<@{user_id}>"
    return user


def create_mock_discord_channel(
    channel_id: int = 111222333,
    channel_type: str = "text",
    name: str = "general",
    guild_id: int | None = 444555666,
):
    """创建模拟的 Discord Channel 对象。

    Args:
        channel_id: 频道 ID
        channel_type: 频道类型
        name: 频道名
        guild_id: 服务器 ID

    Returns:
        MagicMock: 模拟的 Channel 对象
    """
    channel = MagicMock()
    channel.id = channel_id
    channel.name = name
    channel.type = channel_type

    if guild_id:
        channel.guild = MagicMock()
        channel.guild.id = guild_id
    else:
        channel.guild = None

    return channel


# ============================================================
# 消息组件辅助函数
# ============================================================


def create_mock_message_component(
    component_type: str,
    **kwargs: Any,
) -> BaseMessageComponent:
    """创建模拟的消息组件。

    Args:
        component_type: 组件类型 (plain, image, at, reply, file)
        **kwargs: 组件参数

    Returns:
        BaseMessageComponent: 消息组件实例
    """
    from astrbot.core.message import components as Comp

    component_map = {
        "plain": Comp.Plain,
        "image": Comp.Image,
        "at": Comp.At,
        "reply": Comp.Reply,
        "file": Comp.File,
    }

    component_class = component_map.get(component_type.lower())
    if not component_class:
        raise ValueError(f"Unknown component type: {component_type}")

    return component_class(**kwargs)


def create_mock_llm_response(
    completion_text: str = "Hello! How can I help you?",
    role: str = "assistant",
    tools_call_name: list[str] | None = None,
    tools_call_args: list[dict] | None = None,
    tools_call_ids: list[str] | None = None,
):
    """创建模拟的 LLM 响应。

    Args:
        completion_text: 完成文本
        role: 角色
        tools_call_name: 工具调用名称列表
        tools_call_args: 工具调用参数列表
        tools_call_ids: 工具调用 ID 列表

    Returns:
        LLMResponse: 模拟的 LLM 响应
    """
    from astrbot.core.provider.entities import LLMResponse, TokenUsage

    return LLMResponse(
        role=role,
        completion_text=completion_text,
        tools_call_name=tools_call_name or [],
        tools_call_args=tools_call_args or [],
        tools_call_ids=tools_call_ids or [],
        usage=TokenUsage(input_other=10, output=5),
    )
