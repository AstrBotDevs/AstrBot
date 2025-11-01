from dataclasses import dataclass, field
from typing import Any

from astrbot.api import FunctionTool
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class HelloWorldTool(FunctionTool):
    name: str = "hello_world"  # 工具名称
    description: str = "Say hello to the world."  # 工具描述
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "greeting": {
                    "type": "string",
                    "description": "The greeting message.",
                },
            },
            "required": ["greeting"],
        }
    )  # 工具参数定义，见 OpenAI 官网或 https://json-schema.org/understanding-json-schema/

    async def run(
        self,
        event: AstrMessageEvent,  # 必须包含此 event 参数在前面，用于获取上下文
        greeting: str,  # 工具参数，必须与 parameters 中定义的参数名一致
    ):
        await event.send(MessageChain().message("Preparing to greet the world..."))
        yield MessageEventResult().message("111")
        # return f"{greeting}, World!"  # 也支持 mcp.types.CallToolResult 类型


@dataclass
class HelloSoulterTool(FunctionTool):
    name: str = "hello_soulter"  # 工具名称
    description: str = "Say hello to the soulter."  # 工具描述
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "greeting": {
                    "type": "string",
                    "description": "The greeting message.",
                },
            },
            "required": ["greeting"],
        }
    )  # 工具参数定义，见 OpenAI 官网或 https://json-schema.org/understanding-json-schema/

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> Any:
        await context.context.event.send(
            MessageChain().message("Preparing to greet Soulter...")
        )
        yield MessageEventResult().message("111")
        # return f"{kwargs['greeting']}, Soulter!"  # 也支持 mcp.types.CallToolResult 类型
