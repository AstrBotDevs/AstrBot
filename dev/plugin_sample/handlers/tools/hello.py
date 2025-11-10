from mcp.types import CallToolResult
from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.api.v1.components.agent.tool import FunctionTool
from astrbot.api.v1.components.agent import ContextWrapper, AstrAgentContext


@dataclass
class HelloWorldTool(FunctionTool):
    name: str = "hello_world"  # 工具名称
    description: str = "Say hello to the world."  # 工具描述
    parameters: dict = Field(
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

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> str | CallToolResult:
        # event 在 context.context.event 中可用
        greeting = kwargs.get("greeting", "Hello")
        return f"{greeting}, World!"  # 也支持 mcp.types.CallToolResult 类型
