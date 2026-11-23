"""Common lifecycle for runners that delegate a turn to an external service."""

from astrbot import logger
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.response import AgentResponse, AgentResponseData
from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.agent.runners.base import AgentState, BaseAgentRunner
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, ProviderRequest


class RemoteAgentRunner(BaseAgentRunner[TContext]):
    req: ProviderRequest
    streaming: bool
    final_llm_resp: LLMResponse | None
    agent_hooks: BaseAgentRunHooks[TContext]
    run_context: ContextWrapper[TContext]

    def _reset_request(
        self,
        request: ProviderRequest,
        run_context: ContextWrapper[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        streaming: bool,
    ) -> None:
        self.req = request
        self.streaming = streaming
        self.final_llm_resp = None
        self._state = AgentState.IDLE
        self.agent_hooks = agent_hooks
        self.run_context = run_context

    async def _begin_agent_run(self) -> None:
        if not self.req:
            raise ValueError("Request is not set. Please call reset() first.")
        if self._state == AgentState.IDLE:
            try:
                await self.agent_hooks.on_agent_begin(self.run_context)
            except Exception as e:
                logger.error(f"Error in on_agent_begin hook: {e}", exc_info=True)
        self._transition_state(AgentState.RUNNING)

    def _request_inputs(self) -> tuple[str, str, list[str], list[dict], str]:
        return (
            self.req.prompt or "",
            self.req.session_id or "unknown",
            self.req.image_urls or [],
            self.req.contexts or [],
            self.req.system_prompt,
        )

    async def _notify_agent_done_hook(
        self, *, done_response: LLMResponse | None = None
    ) -> None:
        if not self.final_llm_resp:
            return
        if self.final_llm_resp.role == "assistant":
            try:
                await self.agent_hooks.on_llm_response(
                    self.run_context, self.final_llm_resp
                )
            except Exception as e:
                logger.error(f"Error in on_llm_response hook: {e}", exc_info=True)
        try:
            await self.agent_hooks.on_agent_done(
                self.run_context,
                done_response if done_response is not None else self.final_llm_resp,
            )
        except Exception as e:
            logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)

    async def _finish_with_result(
        self, chain: MessageChain, role: str = "assistant"
    ) -> AgentResponse:
        self.final_llm_resp = LLMResponse(role=role, result_chain=chain)
        self._transition_state(AgentState.DONE)
        await self._notify_agent_done_hook()
        return AgentResponse(type="llm_result", data=AgentResponseData(chain=chain))
