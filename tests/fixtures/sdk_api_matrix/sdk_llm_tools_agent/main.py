"""Dedicated new-SDK plugin covering tools, discovery, LLM, TTS/STT, and agent."""

from __future__ import annotations

import inspect
import json
from typing import Annotated

from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.llm import (
    AgentRequest,
    AgentResponse,
    AgentStep,
    ChatChunk,
    ChatResponse,
    EmbeddingResponse,
    ProviderInfo,
    ProviderKind,
    Transcript,
)
from astrbot_sdk.tools import (
    Tool,
    ToolCallContext,
    ToolDefinition,
    ToolParam,
    ToolRef,
    is_tool_context_param,
    tool_params_schema,
)


class LtaRuntimeTool(Tool):
    """Self-contained Tool subclass registered via `update_runtime_tools`."""

    name = "lta_runtime"
    description = "Repeat note in uppercase"
    params = (ToolParam(name="note", type="string", description="Note", required=True),)

    async def call(self, call: ToolCallContext, note: str) -> str:
        """Return formatted note while exercising ToolCallContext."""
        _ = call
        return f"LTA:{note.upper()}"


class SdkLlmToolsAgentPlugin(Plugin):
    """Exercise ToolService, Tool helpers, LLMService, speech, and run_agent."""

    @on.tool(name="lta_add", description="Add two integers", resumable=True)
    async def lta_add(
        self,
        call: ToolCallContext,
        a: Annotated[int, "First operand"],
        b: Annotated[int, "Second operand"],
    ) -> str:
        """Add two integers within a ToolCallContext."""
        _ = call
        return str(a + b)

    @on.streaming_tool(name="lta_stream", description="Streaming-input echo tool")
    async def lta_stream(
        self,
        call: ToolCallContext,
        text: Annotated[str, "Input text"],
    ) -> str:
        """Echo streaming tool input."""
        _ = call
        return f"lta-stream:{text}"

    @on.tool_discovery
    async def discover(self) -> list[ToolDefinition]:
        """Expose a discovered dynamic tool definition."""

        async def _disc(call: ToolCallContext, tag: str = "d") -> str:
            _ = call
            return f"disc:{tag}"

        self.ctx._register_dynamic_tool("tool:lta_discovered", _disc)
        return [
            ToolDefinition(
                name="lta_discovered",
                description="Discovered dynamic tool",
            )
        ]

    @on.command("lta run", description="Run tools, LLM, embed, TTS/STT, and agent")
    async def lta_run(self, event: MessageEvent):
        """Exercise ToolService and every method/DTO of LLMService."""

        async def _temp_tool(call: ToolCallContext, item: str = "x") -> str:
            _ = call
            return f"tmp:{item}"

        sig_params = list(inspect.signature(_temp_tool).parameters.values())
        assert is_tool_context_param(sig_params[0]) is True
        derived_schema = tool_params_schema(_temp_tool)
        assert [p.name for p in derived_schema] == ["item"]

        temp_ref: ToolRef = await self.ctx.tools.register(_temp_tool)
        await self.ctx.tools.unregister(temp_ref)
        runtime_refs = await self.ctx.tools.update_runtime_tools([LtaRuntimeTool()])

        chat_provs: list[ProviderInfo] = await self.ctx.llm.list_providers(
            ProviderKind.CHAT
        )
        cur_chat = await self.ctx.llm.current_provider(ProviderKind.CHAT)
        gen: ChatResponse = await self.ctx.llm.generate(
            "lta-chat",
            system_prompt="brief",
        )
        chunks: list[ChatChunk] = [
            chunk async for chunk in self.ctx.llm.stream("lta-stream")
        ]
        emb: EmbeddingResponse = await self.ctx.llm.embed(("one", "two"))
        audio_ref = await self.ctx.llm.synthesize("lta-tts")
        transcript: Transcript = await self.ctx.llm.transcribe(audio_ref)
        agent_res: AgentResponse = await self.ctx.llm.run_agent(
            AgentRequest(
                input="compute lta_add(3, 5)",
                tools=("lta_add", "lta_runtime"),
            )
        )
        step_ok = all(isinstance(s, AgentStep) for s in agent_res.steps)
        yield event.reply(
            json.dumps(
                {
                    "runtime_tools": [r.name for r in runtime_refs],
                    "provs": len(chat_provs),
                    "cur_id": cur_chat.id if cur_chat else None,
                    "gen": gen.content,
                    "stream": "".join(c.delta for c in chunks),
                    "embed_dims": len(emb.embeddings),
                    "transcript": transcript.text,
                    "agent_text": agent_res.text,
                    "step_ok": step_ok,
                },
                sort_keys=True,
            )
        )
