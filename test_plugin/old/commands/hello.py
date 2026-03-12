"""旧版插件兼容测试夹具。

这个样例故意覆盖当前仍被兼容层支持的旧 API：
- CommandComponent / AstrMessageEvent / MessageChain
- filter.command / regex / permission / permission_type /
  event_message_type / platform_adapter_type
- LegacyContext 的 conversation_manager / llm_generate / tool_loop_agent /
  send_message / put|get|delete_kv_data / call_context_function
- 消息组件及其旧字段别名/工厂方法
"""

from __future__ import annotations

from astrbot_sdk import provide_capability
from astrbot_sdk.api.components.command import CommandComponent
from astrbot_sdk.api.event import AstrMessageEvent, filter
from astrbot_sdk.api.event.filter import (
    ADMIN,
    EventMessageType,
    PermissionType,
    PlatformAdapterType,
)
from astrbot_sdk.api.message import MessageChain
from astrbot_sdk.api.message_components import (
    At,
    AtAll,
    Face,
    File,
    Image,
    Node,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot_sdk.api.star.context import Context
from loguru import logger


class CompatHelper:
    __compat_component_name__ = "CompatHelper"

    async def shout(self, text: str) -> str:
        return text.upper()


class HelloCommand(CommandComponent):
    """测试旧版 CommandComponent 兼容性。"""

    def __init__(self, context: Context):
        self.context = context
        self.context._register_component(CompatHelper())

    @filter.command("hello", alias={"hi"}, priority=10, desc="问候命令")
    async def hello(self, event: AstrMessageEvent):
        """基本命令测试。"""
        ret = await self.context.conversation_manager.new_conversation("hello")
        logger.info("New conversation created: {}", ret)
        yield event.plain_result(f"Hello, Astrbot! Created conversation ID: {ret}")

    @filter.command("echo")
    async def echo(self, event: AstrMessageEvent):
        """测试消息获取和 extra 状态。"""
        text = event.get_message_str()
        event.set_extra("last_echo", text)
        extra = event.get_extra("last_echo")
        event.clear_extra()
        group = await event.get_group()
        yield event.plain_result(
            f"Echo: {text}|sender={event.get_sender_id()}|sender_name={event.get_sender_name()}|"
            f"platform={event.get_platform_name()}:{event.get_platform_id()}|"
            f"type={event.get_message_type().value}|messages={len(event.get_messages())}|"
            f"self={event.get_self_id()}|private={event.is_private_chat()}|"
            f"wake={event.is_wake_up()}|group={group is not None}|extra={extra}"
        )

    @filter.command("chain")
    async def test_chain(self, event: AstrMessageEvent):
        """测试 MessageChain 构建、发送与 react。"""
        chain = (
            MessageChain()
            .message("Hello")
            .message(" ")
            .at("user", "12345")
            .at_all()
            .message(" check this image: ")
            .url_image("https://example.com/test.png")
            .file_image("C:/tmp/test.png")
            .base64_image("base64://fixture")
            .use_t2i(True)
            .squash_plain()
        )

        await event.send(chain)
        await event.react(":thumbsup:")
        yield event.plain_result(
            f"Chain sent with {len(chain.to_payload())} components and t2i={chain.use_t2i_}"
        )

    @filter.command("db")
    async def test_db(self, event: AstrMessageEvent):
        """测试 KV 数据库操作。"""
        await self.context.put_kv_data("test_key", {"value": "test_data"})
        data = await self.context.get_kv_data("test_key")
        await self.context.delete_kv_data("test_key")
        deleted = await self.context.get_kv_data("test_key", "missing")
        logger.info("Got data from db: {}", data)
        yield event.plain_result(f"DB test: stored={data} deleted={deleted}")

    @filter.command("conversation")
    async def test_conversation(self, event: AstrMessageEvent):
        """测试会话管理器和 call_context_function。"""
        umo = f"platform:{event.get_session_id()}"
        cid = await self.context.conversation_manager.new_conversation(
            unified_msg_origin=umo,
            title="Compat Chat",
            persona_id="assistant",
        )
        await self.context.conversation_manager.add_message_pair(cid, "hello", "world")
        await self.context.conversation_manager.update_conversation(
            unified_msg_origin=umo,
            conversation_id=cid,
            title="Compat Chat Updated",
        )
        await self.context.conversation_manager.update_conversation_title(umo, "Compat")
        await self.context.conversation_manager.update_conversation_persona_id(
            umo,
            "compat-persona",
        )
        current_id = await self.context.conversation_manager.get_curr_conversation_id(
            umo
        )
        conv = await self.context.conversation_manager.get_conversation(umo, cid)
        all_conversations = await self.context.conversation_manager.get_conversations(
            umo
        )
        helper_result = await self.context.call_context_function(
            "CompatHelper.shout",
            {"text": "compat"},
        )
        await self.context.conversation_manager.switch_conversation(umo, cid)
        await self.context.conversation_manager.delete_conversation(umo, cid)
        yield event.plain_result(
            f"conversation={current_id}|messages={len((conv or {}).get('content', []))}|"
            f"all={len(all_conversations)}|helper={helper_result['data']}"
        )

    @filter.command("ai")
    async def test_ai(self, event: AstrMessageEvent):
        """测试旧版 AI compat 入口。"""
        llm_resp = await self.context.llm_generate(
            chat_provider_id="provider-demo",
            prompt="legacy hello",
            contexts=[{"role": "user", "content": "hi"}],
        )
        agent_resp = await self.context.tool_loop_agent(
            chat_provider_id="provider-demo",
            prompt="legacy hello",
            tools=[{"name": "search"}],
            max_steps=3,
        )
        yield event.plain_result(f"LLM:{llm_resp.text}|AGENT:{agent_resp.text}")

    @filter.command("sendmsg")
    async def test_send_message(self, event: AstrMessageEvent):
        """测试 LegacyContext.send_message。"""
        chain = (
            MessageChain()
            .message("compat send ")
            .at("legacy-user", "10001")
            .url_image("https://example.com/send.png")
        )
        await self.context.send_message(event.get_session_id(), chain)
        yield event.plain_result("send_message invoked")

    @filter.command("components")
    async def test_components(self, event: AstrMessageEvent):
        """测试消息组件和 chain_result/image_result。"""
        components = [
            Plain(text="Hello"),
            At(qq="123", name="legacy_user"),
            AtAll(),
            Image.fromURL("https://example.com/img.png"),
            Image.fromFileSystem("C:/tmp/local.png"),
            Record.fromFileSystem("C:/tmp/sound.wav"),
            Video.fromURL("https://example.com/video.mp4"),
            File(name="demo.txt", file="https://example.com/demo.txt"),
            Reply(id="reply-1"),
            Node(uin="10001", name="node_user", content=[Plain(text="node")]),
            Face(id=1),
        ]
        component_dicts = [component.to_dict() for component in components]
        logger.info("Components: {}", component_dicts)
        yield event.chain_result(components)
        yield event.image_result("https://example.com/components.png")

    @filter.command("state")
    async def test_event_state(self, event: AstrMessageEvent):
        """测试事件状态方法。"""
        result = event.make_result().message("state-ok")
        event.set_result(result)
        before_stop = event.is_stopped()
        event.stop_event()
        after_stop = event.is_stopped()
        event.continue_event()
        after_continue = event.is_stopped()
        event.should_call_llm(True)
        stored = event.get_result()
        event.clear_result()
        yield event.plain_result(
            f"before={before_stop}|after_stop={after_stop}|after_continue={after_continue}|"
            f"call_llm={event.call_llm}|stored={stored is not None}"
        )

    @filter.regex(r"^ping.*")
    async def ping_regex(self, event: AstrMessageEvent):
        """测试正则匹配。"""
        yield event.plain_result("Pong from regex!")

    @filter.permission(ADMIN)
    @filter.command("admin")
    async def admin_only(self, event: AstrMessageEvent):
        """测试 permission(ADMIN)。"""
        yield event.plain_result(f"Admin command executed by {event.is_admin()}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("admin_type")
    async def admin_type_only(self, event: AstrMessageEvent):
        """测试 permission_type(PermissionType.ADMIN)。"""
        yield event.plain_result(f"Admin type command executed by {event.is_admin()}")

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def group_only(self, event: AstrMessageEvent):
        """测试消息类型过滤。"""
        yield event.plain_result("Group message received")

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def cqhttp_only(self, event: AstrMessageEvent):
        """测试平台过滤。"""
        yield event.plain_result("CQHttp platform detected")

    @provide_capability(
        "compat.echo",
        description="使用 legacy Context 回显输入文本",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "echo": {"type": "string"},
                "plugin_id": {"type": "string"},
            },
            "required": ["echo", "plugin_id"],
        },
    )
    async def echo_capability(self, payload: dict):
        """测试旧版插件 capability 能走 LegacyContext。"""
        text = str(payload.get("text", ""))
        await self.context.put_kv_data("compat_capability", {"text": text})
        stored = await self.context.get_kv_data("compat_capability", {})
        return {
            "echo": str(stored.get("text", "")),
            "plugin_id": self.context.plugin_id,
        }
