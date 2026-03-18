from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.runtime.capability_router import StreamExecution

from ..bridge_base import _get_runtime_tool_types
from ._host import CapabilityMixinHost

if TYPE_CHECKING:
    from astrbot.core.agent.tool import ToolSet
    from astrbot.core.provider.entities import LLMResponse


class LLMCapabilityMixin(CapabilityMixinHost):
    def _register_llm_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("llm.chat", "Send chat request"),
            call_handler=self._llm_chat,
        )
        self.register(
            self._builtin_descriptor(
                "llm.chat_raw",
                "Send chat request and return raw response",
            ),
            call_handler=self._llm_chat_raw,
        )
        self.register(
            self._builtin_descriptor(
                "llm.stream_chat",
                "Stream chat response",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._llm_stream_chat,
        )

    async def _llm_chat(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        response = await self._call_llm(payload, request_id=request_id)
        return {"text": response.completion_text}

    async def _llm_chat_raw(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        response = await self._call_llm(payload, request_id=request_id)
        usage = None
        if response.usage is not None:
            usage = {
                "input_tokens": response.usage.input,
                "output_tokens": response.usage.output,
                "total_tokens": response.usage.total,
            }
        return {
            "text": response.completion_text,
            "usage": usage,
            "finish_reason": "tool_calls" if response.tools_call_ids else "stop",
            "tool_calls": response.to_openai_tool_calls(),
            "role": response.role,
            "reasoning_content": response.reasoning_content or None,
            "reasoning_signature": response.reasoning_signature,
        }

    async def _llm_stream_chat(
        self,
        request_id: str,
        payload: dict[str, Any],
        token,
    ) -> StreamExecution:
        provider, request_kwargs = self._resolve_llm_request(
            payload,
            request_id=request_id,
        )

        async def fallback_iterator() -> AsyncIterator[dict[str, Any]]:
            response = await provider.text_chat(**request_kwargs)
            for char in response.completion_text:
                token.raise_if_cancelled()
                await asyncio.sleep(0)
                yield {"text": char}

        async def iterator() -> AsyncIterator[dict[str, Any]]:
            try:
                stream = provider.text_chat_stream(**request_kwargs)
                yielded_text = False
                async for response in stream:
                    token.raise_if_cancelled()
                    text = response.completion_text
                    if response.is_chunk:
                        if text:
                            yielded_text = True
                            yield {"text": text}
                        continue
                    if text:
                        if yielded_text:
                            yield {"_final_text": text}
                        else:
                            yielded_text = True
                            yield {"text": text, "_final_text": text}
                    else:
                        yield {"_final_text": text}
            except NotImplementedError:
                async for item in fallback_iterator():
                    yield item

        def finalize(chunks: list[dict[str, Any]]) -> dict[str, Any]:
            final_text = None
            for item in reversed(chunks):
                if "_final_text" in item:
                    final_text = str(item.get("_final_text", ""))
                    break
            if final_text is None:
                final_text = "".join(str(item.get("text", "")) for item in chunks)
            return {"text": final_text}

        return StreamExecution(
            iterator=iterator(),
            finalize=finalize,
        )

    async def _call_llm(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> LLMResponse:
        provider, request_kwargs = self._resolve_llm_request(
            payload,
            request_id=request_id,
        )
        return await provider.text_chat(**request_kwargs)

    def _resolve_llm_request(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> tuple[Any, dict[str, Any]]:
        request_context = self._plugin_bridge.resolve_request_session(request_id)
        provider_id = payload.get("provider_id")
        if provider_id:
            provider = self._star_context.get_provider_by_id(str(provider_id))
        else:
            provider = self._star_context.get_using_provider(
                request_context.event.unified_msg_origin
                if request_context is not None
                else None,
            )
        if provider is None:
            raise AstrBotError.internal_error(
                "No active chat provider is available",
                hint="Please configure a chat provider in AstrBot first",
            )
        return provider, self._normalize_llm_payload(payload)

    @staticmethod
    def _normalize_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
        contexts_payload = payload.get("contexts")
        if contexts_payload is None:
            contexts_payload = payload.get("history")
        contexts = (
            [dict(item) for item in contexts_payload]
            if isinstance(contexts_payload, list)
            else None
        )
        image_urls = payload.get("image_urls")
        tool_calls_result = payload.get("tool_calls_result")
        tools_payload = payload.get("tools")
        request_kwargs: dict[str, Any] = {
            "prompt": str(payload.get("prompt", "")),
            "image_urls": (
                [str(item) for item in image_urls]
                if isinstance(image_urls, list)
                else None
            ),
            "func_tool": (
                LLMCapabilityMixin._build_toolset(tools_payload)
                if isinstance(tools_payload, list)
                else None
            ),
            "contexts": contexts,
            "tool_calls_result": (
                [dict(item) for item in tool_calls_result]
                if isinstance(tool_calls_result, list)
                else None
            ),
            "system_prompt": str(payload.get("system", "")),
            "model": (str(payload["model"]) if payload.get("model") else None),
            "temperature": payload.get("temperature"),
        }
        return request_kwargs

    @staticmethod
    def _build_toolset(tools_payload: list[Any]) -> ToolSet:
        function_tool_cls, tool_set_cls = _get_runtime_tool_types()
        tool_set = tool_set_cls()
        for item in tools_payload:
            if not isinstance(item, dict):
                raise AstrBotError.invalid_input("llm tools items must be objects")
            if str(item.get("type", "function")) != "function":
                raise AstrBotError.invalid_input(
                    "Only function tools are supported in AstrBot SDK MVP"
                )
            function_payload = item.get("function")
            if not isinstance(function_payload, dict):
                raise AstrBotError.invalid_input(
                    "llm tools items must contain a function object"
                )
            name = str(function_payload.get("name", "")).strip()
            if not name:
                raise AstrBotError.invalid_input(
                    "llm function tool name must not be empty"
                )
            description = str(function_payload.get("description", "") or "")
            parameters = function_payload.get("parameters")
            if not isinstance(parameters, dict):
                parameters = {"type": "object", "properties": {}}
            tool_set.add_tool(
                function_tool_cls(
                    name=name,
                    description=description,
                    parameters=parameters,
                    handler=None,
                )
            )
        return tool_set
