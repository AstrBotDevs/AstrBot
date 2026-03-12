from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from ._proxy import CapabilityProxy


class ChatMessage(BaseModel):
    role: str
    content: str


class LLMResponse(BaseModel):
    text: str
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class LLMClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
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
        async for data in self._proxy.stream(
            "llm.stream_chat",
            {
                "prompt": prompt,
                "system": system,
                "history": [item.model_dump() for item in history or []],
            },
        ):
            yield str(data.get("text", ""))
