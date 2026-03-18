from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from ..bridge_base import CapabilityRouterBridgeBase


class LLMCapabilityMixin(CapabilityRouterBridgeBase):
    async def _llm_chat(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        prompt = str(payload.get("prompt", ""))
        return {"text": f"Echo: {prompt}"}

    async def _llm_chat_raw(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        prompt = str(payload.get("prompt", ""))
        text = f"Echo: {prompt}"
        return {
            "text": text,
            "usage": {
                "input_tokens": len(prompt),
                "output_tokens": len(text),
            },
            "finish_reason": "stop",
            "tool_calls": [],
        }

    async def _llm_stream(
        self,
        _request_id: str,
        payload: dict[str, Any],
        token,
    ) -> AsyncIterator[dict[str, Any]]:
        text = f"Echo: {str(payload.get('prompt', ''))}"
        for char in text:
            token.raise_if_cancelled()
            await asyncio.sleep(0)
            yield {"text": char}

    def _register_llm_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("llm.chat", "发送对话请求，返回文本"),
            call_handler=self._llm_chat,
        )
        self.register(
            self._builtin_descriptor("llm.chat_raw", "发送对话请求，返回完整响应"),
            call_handler=self._llm_chat_raw,
        )
        self.register(
            self._builtin_descriptor(
                "llm.stream_chat",
                "流式对话",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._llm_stream,
            finalize=lambda chunks: {
                "text": "".join(item.get("text", "") for item in chunks)
            },
        )

