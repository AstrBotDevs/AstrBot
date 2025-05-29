from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, List

from astrbot.api.provider import Personality, Provider
from astrbot.core.db import BaseDatabase
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, ToolCallsResult
from astrbot.core.provider.func_tool_manager import FuncCall
from astrbot.core import logger
from ..register import register_provider_adapter

try:
    from google.agents import Agent
except Exception:  # pragma: no cover - optional dependency
    Agent = None  # type: ignore


@register_provider_adapter(
    "google_agent_sdk", "Google Agent SDK 提供商适配器"
)
class ProviderGoogleAgentSDK(Provider):
    """Provider adapter using Google Agent SDK.

    This is a lightweight integration that forwards prompts to a Google Agent.
    If the optional dependency is missing, initialization fails.
    """

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        db_helper: BaseDatabase,
        persistant_history: bool = True,
        default_persona: Personality | None = None,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
            persistant_history,
            db_helper,
            default_persona,
        )

        if Agent is None:
            raise ImportError(
                "google-agents SDK is required for google_agent_sdk provider"
            )

        self.api_key: str | None = None
        keys = provider_config.get("key", [])
        if keys:
            self.api_key = keys[0]
        self.set_model(provider_config.get("model_config", {}).get("model", ""))
        # Actual Agent initialization; parameters may vary based on SDK version.
        # TODO: pass additional configuration such as tools when needed.
        self.agent = Agent(api_key=self.api_key, model=self.get_model())

    def get_current_key(self) -> str:
        return self.api_key or ""

    def set_key(self, key: str) -> None:
        self.api_key = key
        # The Agent instance might need reconfiguration with new key.
        try:
            self.agent.api_key = key  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - best effort
            pass

    def get_models(self) -> List[str]:  # pragma: no cover - simple return
        return [self.get_model()]

    async def text_chat(
        self,
        prompt: str,
        session_id: str | None = None,
        image_urls: List[str] | None = None,
        func_tool: FuncCall | None = None,
        contexts: List[dict] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Return chat completion via Google Agent SDK."""
        if image_urls:
            logger.warning("google_agent_sdk provider does not support images yet")
        history = contexts or []
        if system_prompt:
            history = [{"role": "system", "content": system_prompt}, *history]
        # TODO: handle func_tool and tool_calls_result via ADK Tool API
        try:
            response = await self.agent.chat(prompt, history=history)  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover - runtime errors
            raise Exception(f"Google Agent SDK error: {e}") from e
        llm_response = LLMResponse("assistant")
        llm_response.result_chain = MessageChain().message(str(response))
        llm_response.raw_completion = response
        return llm_response

    async def text_chat_stream(
        self,
        prompt: str,
        session_id: str | None = None,
        image_urls: List[str] | None = None,
        func_tool: FuncCall | None = None,
        contexts: List[dict] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[LLMResponse, None]:
        """Stream chat completions via Google Agent SDK."""
        llm_response = await self.text_chat(
            prompt,
            session_id=session_id,
            image_urls=image_urls,
            func_tool=func_tool,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
            **kwargs,
        )
        yield llm_response
