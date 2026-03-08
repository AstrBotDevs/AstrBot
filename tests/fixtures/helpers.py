"""测试辅助函数和工具类。

提供统一的测试辅助工具，减少测试代码重复。
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
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


# ============================================================
# 测试插件辅助函数
# ============================================================


@dataclass
class MockPluginConfig:
    """测试插件配置。

    用于创建和管理测试用的模拟插件。

    Attributes:
        name: 插件名称
        author: 作者
        description: 描述
        version: 版本
        repo: 仓库 URL
        main_code: main.py 的代码内容
        requirements: 依赖列表
        has_readme: 是否创建 README.md
        readme_content: README.md 内容
    """

    name: str = "test_plugin"
    author: str = "Test Author"
    description: str = "A test plugin for unit testing"
    version: str = "1.0.0"
    repo: str = "https://github.com/test/test_plugin"
    main_code: str = ""
    requirements: list[str] = field(default_factory=list)
    has_readme: bool = True
    readme_content: str = "# Test Plugin\n\nThis is a test plugin."


# 默认的插件主代码模板
DEFAULT_PLUGIN_MAIN_TEMPLATE = '''
from astrbot.api import star

class Main(star.Star):
    """测试插件主类。"""

    def __init__(self, context):
        super().__init__(context)
        self.name = "{plugin_name}"

    async def initialize(self):
        """初始化插件。"""
        pass

    async def terminate(self):
        """终止插件。"""
        pass
'''


class MockPluginBuilder:
    """测试插件构建器。

    用于创建、管理和清理测试用的模拟插件。支持任意插件的模拟创建。

    Example:
        # 创建一个简单的测试插件
        builder = MockPluginBuilder(plugin_store_path)
        plugin_dir = builder.create("my_test_plugin")

        # 创建自定义配置的插件
        config = MockPluginConfig(
            name="custom_plugin",
            version="2.0.0",
            main_code="print('hello')",
        )
        plugin_dir = builder.create(config)

        # 清理插件
        builder.cleanup("my_test_plugin")
    """

    def __init__(self, plugin_store_path: str | Path):
        """初始化构建器。

        Args:
            plugin_store_path: 插件存储路径 (通常是 data/plugins)
        """
        self.plugin_store_path = Path(plugin_store_path)
        self._created_plugins: set[str] = set()

    def create(
        self,
        plugin_config: str | MockPluginConfig | None = None,
        **kwargs,
    ) -> Path:
        """创建模拟插件。

        Args:
            plugin_config: 插件名称字符串、MockPluginConfig 对象或 None
            **kwargs: 如果 plugin_config 是字符串或 None，这些参数用于构建 MockPluginConfig

        Returns:
            Path: 创建的插件目录路径
        """
        # 处理不同类型的输入
        if plugin_config is None:
            config = MockPluginConfig(**kwargs)
        elif isinstance(plugin_config, str):
            config = MockPluginConfig(name=plugin_config, **kwargs)
        elif isinstance(plugin_config, MockPluginConfig):
            config = plugin_config
        else:
            raise TypeError(f"Invalid plugin_config type: {type(plugin_config)}")

        # 创建插件目录
        plugin_dir = self.plugin_store_path / config.name
        plugin_dir.mkdir(parents=True, exist_ok=True)

        # 创建 metadata.yaml
        metadata_content = "\n".join(
            [
                f"name: {config.name}",
                f"author: {config.author}",
                f"desc: {config.description}",
                f"version: {config.version}",
                f"repo: {config.repo}",
            ]
        )
        (plugin_dir / "metadata.yaml").write_text(
            metadata_content + "\n", encoding="utf-8"
        )

        # 创建 main.py
        main_code = config.main_code or DEFAULT_PLUGIN_MAIN_TEMPLATE.format(
            plugin_name=config.name
        )
        (plugin_dir / "main.py").write_text(main_code, encoding="utf-8")

        # 创建 requirements.txt（如果有依赖）
        if config.requirements:
            (plugin_dir / "requirements.txt").write_text(
                "\n".join(config.requirements) + "\n", encoding="utf-8"
            )

        # 创建 README.md（如果需要）
        if config.has_readme:
            (plugin_dir / "README.md").write_text(
                config.readme_content, encoding="utf-8"
            )

        # 记录创建的插件
        self._created_plugins.add(config.name)

        return plugin_dir

    def cleanup(self, plugin_name: str | None = None) -> None:
        """清理插件。

        Args:
            plugin_name: 要清理的插件名称，如果为 None 则清理所有由本构建器创建的插件
        """
        if plugin_name:
            plugins_to_clean = {plugin_name}
        else:
            plugins_to_clean = self._created_plugins.copy()

        for name in plugins_to_clean:
            plugin_dir = self.plugin_store_path / name
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)
            self._created_plugins.discard(name)

    def cleanup_all(self) -> None:
        """清理所有由本构建器创建的插件。"""
        self.cleanup(None)

    def get_plugin_path(self, plugin_name: str) -> Path:
        """获取插件路径。

        Args:
            plugin_name: 插件名称

        Returns:
            Path: 插件目录路径
        """
        return self.plugin_store_path / plugin_name

    @property
    def created_plugins(self) -> set[str]:
        """获取已创建的插件名称集合。"""
        return self._created_plugins.copy()


def create_mock_updater_install(
    plugin_builder: MockPluginBuilder,
    repo_to_plugin: dict[str, str] | None = None,
) -> Callable:
    """创建模拟的 updater.install 方法。

    Args:
        plugin_builder: MockPluginBuilder 实例
        repo_to_plugin: 仓库 URL 到插件名称的映射，格式: {"https://github.com/user/repo": "plugin_name"}

    Returns:
        Callable: 异步函数，可用于 monkeypatch.setattr
    """

    async def mock_install(repo_url: str, proxy: str = "") -> str:
        """Mock updater.install 方法。"""
        # 查找插件名称
        plugin_name = None
        if repo_to_plugin:
            plugin_name = repo_to_plugin.get(repo_url)

        # 如果没有映射，尝试从 URL 提取插件名
        if not plugin_name:
            # 从 https://github.com/user/plugin_name 提取 plugin_name
            parts = repo_url.rstrip("/").split("/")
            plugin_name = parts[-1] if parts else "unknown_plugin"

        # 创建插件目录
        config = MockPluginConfig(name=plugin_name, repo=repo_url)
        plugin_dir = plugin_builder.create(config)
        return str(plugin_dir)

    return mock_install


def create_mock_updater_update(
    plugin_builder: MockPluginBuilder,
    update_callback: Callable | None = None,
) -> Callable:
    """创建模拟的 updater.update 方法。

    Args:
        plugin_builder: MockPluginBuilder 实例
        update_callback: 更新回调函数，接收 plugin 参数

    Returns:
        Callable: 异步函数，可用于 monkeypatch.setattr
    """

    async def mock_update(plugin, proxy: str = "") -> None:
        """Mock updater.update 方法。"""
        plugin_dir = plugin_builder.get_plugin_path(plugin.name)

        # 创建更新标记文件
        (plugin_dir / ".updated").write_text("ok", encoding="utf-8")

        # 调用回调
        if update_callback:
            update_callback(plugin)

    return mock_update
