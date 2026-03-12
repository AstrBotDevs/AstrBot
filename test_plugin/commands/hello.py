"""旧版插件兼容测试 - 使用 astrbot_sdk 旧版 API。

测试覆盖：
- CommandComponent 继承
- filter.command 装饰器
- LegacyContext 功能 (conversation_manager, send_message, db)
- AstrMessageEvent 和 MessageChain
- 消息组件 (Plain, At, Image)
"""

from astrbot_sdk.api.components.command import CommandComponent
from astrbot_sdk.api.event import AstrMessageEvent, filter
from astrbot_sdk.api.star.context import Context
from astrbot_sdk.api.message import MessageChain
from astrbot_sdk.api.message_components import Plain, At, Image
from loguru import logger


class HelloCommand(CommandComponent):
    """测试旧版 CommandComponent 兼容性。"""

    def __init__(self, context: Context):
        self.context = context

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        """基本命令测试。"""
        ret = await self.context.conversation_manager.new_conversation("hello")
        logger.info(f"New conversation created: {ret}")
        yield event.plain_result(f"Hello, Astrbot! Created conversation ID: {ret}")

    @filter.command("echo")
    async def echo(self, event: AstrMessageEvent):
        """测试消息获取。"""
        text = event.get_message_str()
        yield event.plain_result(f"Echo: {text}")

    @filter.command("chain")
    async def test_chain(self, event: AstrMessageEvent):
        """测试 MessageChain 构建和发送。"""
        # 构建消息链
        chain = (
            MessageChain()
            .message("Hello! ")
            .at("user", "12345")
            .message(" check this image: ")
            .url_image("https://example.com/test.png")
        )

        # 测试 to_payload 和 is_plain_text_only
        payload = chain.to_payload()
        is_plain = chain.is_plain_text_only()

        logger.info(f"Chain payload: {payload}, is_plain_text_only: {is_plain}")

        yield event.plain_result(f"Chain sent with {len(payload)} components")

    @filter.command("db")
    async def test_db(self, event: AstrMessageEvent):
        """测试 KV 数据库操作。"""
        # 写入数据
        await self.context.put_kv_data("test_key", {"value": "test_data"})

        # 读取数据
        data = await self.context.get_kv_data("test_key")
        logger.info(f"Got data from db: {data}")

        yield event.plain_result(f"DB test: stored and retrieved {data}")

    @filter.command("components")
    async def test_components(self, event: AstrMessageEvent):
        """测试消息组件。"""
        # 测试 Plain
        plain = Plain(text="Hello")

        # 测试 At
        at = At(user_id="123", user_name="test_user")

        # 测试 Image
        img = Image.fromURL("https://example.com/img.png")

        # 测试 to_dict
        plain_dict = plain.to_dict()
        at_dict = at.to_dict()

        logger.info(f"Plain: {plain_dict}, At: {at_dict}")

        yield event.plain_result(f"Components created: Plain, At, Image")

    @filter.regex(r"^ping.*")
    async def ping_regex(self, event: AstrMessageEvent):
        """测试正则匹配。"""
        yield event.plain_result("Pong from regex!")

    @filter.permission("admin")
    async def admin_only(self, event: AstrMessageEvent):
        """测试权限过滤 (应该被跳过，因为没有 require_admin)。"""
        yield event.plain_result("Admin command executed")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def group_only(self, event: AstrMessageEvent):
        """测试消息类型过滤。"""
        yield event.plain_result("Group message received")

    @filter.platform_adapter_type("aiocqhttp")
    async def cqhttp_only(self, event: AstrMessageEvent):
        """测试平台过滤。"""
        yield event.plain_result("CQHttp platform detected")

