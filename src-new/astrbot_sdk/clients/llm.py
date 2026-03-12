"""大语言模型客户端模块。

提供与 LLM 交互的能力，支持普通聊天和流式聊天。

与旧版对比：
    旧版 (src/astrbot_sdk/api/star/context.py):
        Context.llm_generate(
            chat_provider_id, prompt, image_urls, tools,
            system_prompt, contexts, **kwargs
        )
        Context.tool_loop_agent(...)  # Agent 循环，自动执行工具调用

    新版:
        Context.llm.chat(prompt, system, history, model, temperature)
        Context.llm.chat_raw(prompt, **kwargs)  # 返回完整响应
        Context.llm.stream_chat(prompt, system, history)  # 流式响应

主要差异：
    1. 新版移除了 chat_provider_id 参数，由核心自动选择
    2. 新版简化了参数结构，使用 ChatMessage 模型
    3. 新版支持流式响应 (stream_chat)

TODO (相比旧版缺失的功能):
    - 缺少 tool_loop_agent() Agent 循环能力
    - 缺少 add_llm_tools() 动态工具注册
    - chat() 缺少 image_urls 多模态图片支持
    - chat() 缺少 tools 工具集支持
    - chat() 缺少 contexts 上下文消息列表
    - 缺少对 OpenAI 兼容的额外参数传递 (**kwargs 支持不完整)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from ._proxy import CapabilityProxy


class ChatMessage(BaseModel):
    """聊天消息模型。

    用于构建对话历史，传递给 LLM。

    Attributes:
        role: 消息角色，如 "user", "assistant", "system"
        content: 消息内容

    示例:
        history = [
            ChatMessage(role="user", content="你好"),
            ChatMessage(role="assistant", content="你好！有什么可以帮助你的？"),
            ChatMessage(role="user", content="今天天气怎么样？"),
        ]
    """

    role: str
    content: str


class LLMResponse(BaseModel):
    """LLM 响应模型。

    包含完整的 LLM 响应信息，用于 chat_raw() 方法返回。

    Attributes:
        text: 生成的文本内容
        usage: Token 使用统计，如 {"prompt_tokens": 10, "completion_tokens": 20}
        finish_reason: 结束原因，如 "stop", "length", "tool_calls"
        tool_calls: 工具调用列表（如果 LLM 决定调用工具）
    """

    text: str
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class LLMClient:
    """大语言模型客户端。

    提供与 LLM 交互的能力，支持普通聊天和流式聊天。

    Attributes:
        _proxy: CapabilityProxy 实例，用于远程能力调用
    """

    def __init__(self, proxy: CapabilityProxy) -> None:
        """初始化 LLM 客户端。

        Args:
            proxy: CapabilityProxy 实例
        """
        self._proxy = proxy

    async def chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        history: list[ChatMessage] | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """发送聊天请求并返回文本响应。

        这是简化的聊天接口，仅返回生成的文本内容。
        如需完整响应信息（包括 usage、tool_calls），请使用 chat_raw()。

        Args:
            prompt: 用户输入的提示文本
            system: 系统提示词，用于指导 LLM 行为
            history: 对话历史，用于保持上下文连续性
            model: 指定使用的模型名称（可选，由核心自动选择）
            temperature: 生成温度，控制随机性（0-1）

        Returns:
            LLM 生成的文本内容

        示例:
            # 简单对话
            reply = await ctx.llm.chat("你好，介绍一下自己")

            # 带历史的对话
            history = [
                ChatMessage(role="user", content="我叫小明"),
                ChatMessage(role="assistant", content="你好小明！"),
            ]
            reply = await ctx.llm.chat("你记得我的名字吗？", history=history)
        """
        output = await self._proxy.call(
            "llm.chat",
            {
                "prompt": prompt,
                "system": system,
                "history": [item.model_dump() for item in history or []],
                "model": model,
                "temperature": temperature,
            },
        )
        return str(output.get("text", ""))

    async def chat_raw(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送聊天请求并返回完整响应。

        与 chat() 不同，此方法返回完整的 LLMResponse 对象，
        包含 usage、finish_reason、tool_calls 等信息。

        Args:
            prompt: 用户输入的提示文本
            **kwargs: 额外参数，如 system, history, model, temperature 等

        Returns:
            LLMResponse 对象，包含完整响应信息

        示例:
            response = await ctx.llm.chat_raw("写一首诗", temperature=0.8)
            print(f"生成文本: {response.text}")
            print(f"Token 使用: {response.usage}")
        """
        output = await self._proxy.call(
            "llm.chat_raw",
            {
                "prompt": prompt,
                **kwargs,
            },
        )
        return LLMResponse.model_validate(output)

    async def stream_chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        history: list[ChatMessage] | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式聊天，逐块返回响应文本。

        适用于需要实时显示生成内容的场景，如聊天界面。

        Args:
            prompt: 用户输入的提示文本
            system: 系统提示词
            history: 对话历史

        Yields:
            每个生成的文本块

        示例:
            async for chunk in ctx.llm.stream_chat("讲一个故事"):
                print(chunk, end="", flush=True)
        """
        async for data in self._proxy.stream(
            "llm.stream_chat",
            {
                "prompt": prompt,
                "system": system,
                "history": [item.model_dump() for item in history or []],
            },
        ):
            yield str(data.get("text", ""))
