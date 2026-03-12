"""大语言模型客户端模块。

提供 v4 原生的 LLM 能力调用接口。

设计边界：
    - `chat()` 是便捷文本接口，返回最终文本
    - `chat_raw()` 返回完整结构化响应
    - `stream_chat()` 返回文本增量
    - Agent 循环、动态工具注册等更高层 orchestration 不放在客户端内，
      由上层运行时或 `_legacy_api.py` 的兼容入口承接
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping, Sequence
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


ChatHistoryItem = ChatMessage | Mapping[str, Any]


def _serialize_history(
    history: Sequence[ChatHistoryItem] | None,
) -> list[dict[str, Any]]:
    if history is None:
        return []

    serialized: list[dict[str, Any]] = []
    for item in history:
        if isinstance(item, ChatMessage):
            serialized.append(item.model_dump())
            continue
        if isinstance(item, Mapping):
            serialized.append(dict(item))
            continue
        raise TypeError("history 项必须是 ChatMessage 或 mapping")
    return serialized


def _build_chat_payload(
    prompt: str,
    *,
    system: str | None = None,
    history: Sequence[ChatHistoryItem] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"prompt": prompt}
    if system is not None:
        payload["system"] = system
    if history is not None:
        payload["history"] = _serialize_history(history)
    if model is not None:
        payload["model"] = model
    if temperature is not None:
        payload["temperature"] = temperature
    if extra:
        payload.update(extra)
    return payload


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
        history: Sequence[ChatHistoryItem] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        **kwargs: Any,
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
            **kwargs: 额外透传参数，如 `image_urls`、`tools`

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
            _build_chat_payload(
                prompt,
                system=system,
                history=history,
                model=model,
                temperature=temperature,
                extra=kwargs,
            ),
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
        payload = {"prompt": prompt, **kwargs}
        if "history" in payload:
            payload["history"] = _serialize_history(payload["history"])
        output = await self._proxy.call(
            "llm.chat_raw",
            payload,
        )
        return LLMResponse.model_validate(output)

    async def stream_chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        history: Sequence[ChatHistoryItem] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """流式聊天，逐块返回响应文本。

        适用于需要实时显示生成内容的场景，如聊天界面。

        Args:
            prompt: 用户输入的提示文本
            system: 系统提示词
            history: 对话历史
            model: 指定模型
            temperature: 采样温度
            **kwargs: 额外透传参数，如 `image_urls`、`tools`

        Yields:
            每个生成的文本块

        示例:
            async for chunk in ctx.llm.stream_chat("讲一个故事"):
                print(chunk, end="", flush=True)
        """
        async for data in self._proxy.stream(
            "llm.stream_chat",
            _build_chat_payload(
                prompt,
                system=system,
                history=history,
                model=model,
                temperature=temperature,
                extra=kwargs,
            ),
        ):
            yield str(data.get("text", ""))
