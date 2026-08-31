import asyncio
import re
import typing as T
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any, cast, override

import aiohttp
from dashscope import Application
from dashscope.api_entities.api_request_factory import _build_api_request
from dashscope.app.application_response import ApplicationResponse

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.proxy_route import (
    ProxyRoute,
    aiohttp_request_proxy,
    resolve_proxy_route,
)
from astrbot.core.utils.shared_preferences import SharedPreferences

from ...hooks import BaseAgentRunHooks
from ...llm_types import LLMResponse, ProviderRequest
from ...response import AgentResponseData
from ...run_context import ContextWrapper, TContext
from ..base import AgentResponse, AgentState, BaseAgentRunner

_DASHSCOPE_REQUEST_FAILURE = "阿里云百炼请求失败，请稍后重试。"


def create_dashscope_http_session(route: ProxyRoute) -> aiohttp.ClientSession:
    """Create a per-runner aiohttp session for DashScope's async transport.

    DashScope's ``HttpRequest`` accepts an external ``ClientSession`` but does
    not forward per-request ``proxy`` kwargs. The returned session uses
    ``trust_env=False`` and injects the resolved proxy URL into every request.

    Args:
        route: Resolved AstrBot proxy route.

    Returns:
        Session with ``trust_env=False`` that injects the resolved proxy URL.
    """
    session = aiohttp.ClientSession(trust_env=False)
    proxy_url = aiohttp_request_proxy(route)
    original_request = session._request

    async def _request(method, url, **kwargs):
        kwargs.setdefault("proxy", proxy_url)
        return await original_request(method, url, **kwargs)

    setattr(session, "_request", _request)
    session._astrbot_proxy_url = proxy_url
    return session


class DashscopeAgentRunner(BaseAgentRunner[TContext]):
    """Dashscope Agent Runner.

    Outbound HTTP uses DashScope's aiohttp transport with a per-runner
    session. ``proxy_mode`` / ``proxy_url`` are resolved by
    ``resolve_proxy_route`` and injected into that session. Process-wide
    ``HTTP_PROXY`` is never mutated.
    """

    @override
    async def reset(
        self,
        request: ProviderRequest,
        run_context: ContextWrapper[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        provider_config: dict,
        **kwargs: T.Any,
    ) -> None:
        self.req = request
        self.streaming = kwargs.get("streaming", False)
        self.final_llm_resp = None
        self._state = AgentState.IDLE
        self.agent_hooks = agent_hooks
        self.run_context = run_context
        self.preferences: SharedPreferences = kwargs["preferences"]

        self.api_key = provider_config.get("dashscope_api_key", "")
        if not self.api_key:
            raise ValueError("阿里云百炼 API Key 不能为空。")
        self.app_id = provider_config.get("dashscope_app_id", "")
        if not self.app_id:
            raise ValueError("阿里云百炼 APP ID 不能为空。")
        self.dashscope_app_type = provider_config.get("dashscope_app_type", "")
        if not self.dashscope_app_type:
            raise ValueError("阿里云百炼 APP 类型不能为空。")

        variables = provider_config.get("variables", {})
        if variables is None:
            variables = {}
        if not isinstance(variables, dict):
            raise ValueError("阿里云百炼 variables 必须为对象。")
        self.variables = variables.copy()

        rag_options = provider_config.get("rag_options", {})
        if rag_options is None:
            rag_options = {}
        if not isinstance(rag_options, dict):
            raise ValueError("阿里云百炼 rag_options 必须为对象。")
        self.rag_options = rag_options.copy()
        self.output_reference = self.rag_options.get("output_reference", False)
        self.rag_options.pop("output_reference", None)

        raw_timeout = provider_config.get("timeout", 120)
        if isinstance(raw_timeout, bool):
            raise ValueError("阿里云百炼 timeout 必须为正整数。")
        if isinstance(raw_timeout, int):
            self.timeout = raw_timeout
        elif isinstance(raw_timeout, str):
            try:
                self.timeout = int(raw_timeout)
            except ValueError as exc:
                raise ValueError("阿里云百炼 timeout 必须为正整数。") from exc
        else:
            raise ValueError("阿里云百炼 timeout 必须为正整数。")
        if self.timeout <= 0:
            raise ValueError("阿里云百炼 timeout 必须为正整数。")

        self._proxy_route = resolve_proxy_route(local_config=provider_config)
        await self.close()

    async def close(self) -> None:
        """Close the per-runner DashScope HTTP session."""
        previous = getattr(self, "_http_session", None)
        self._http_session = None
        if previous is not None and not previous.closed:
            await previous.close()

    def _ensure_http_session(self) -> aiohttp.ClientSession:
        session = getattr(self, "_http_session", None)
        if session is None or session.closed:
            self._http_session = create_dashscope_http_session(self._proxy_route)
        assert self._http_session is not None
        return self._http_session

    def has_rag_options(self) -> bool:
        """判断是否有 RAG 选项

        Returns:
            bool: 是否有 RAG 选项

        """
        if self.rag_options and (
            len(self.rag_options.get("pipeline_ids", [])) > 0
            or len(self.rag_options.get("file_ids", [])) > 0
        ):
            return True
        return False

    @override
    async def step(self):
        """
        执行 Dashscope Agent 的一个步骤
        """
        if not self.req:
            raise ValueError("Request is not set. Please call reset() first.")

        if self._state == AgentState.IDLE:
            try:
                await self.agent_hooks.on_agent_begin(self.run_context)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Dashscope on_agent_begin hook failed: %s",
                    safe_error("", exc),
                )

        # 开始处理，转换到运行状态
        self._transition_state(AgentState.RUNNING)

        try:
            # 执行 Dashscope 请求并处理结果
            async for response in self._execute_dashscope_request():
                yield response
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Dashscope request failed: %s", safe_error("", exc))
            yield self._failure_response()

    def _failure_response(self) -> AgentResponse:
        """Record and return the stable public Dashscope failure response."""
        chain = MessageChain().message(_DASHSCOPE_REQUEST_FAILURE)
        self._transition_state(AgentState.ERROR)
        self.final_llm_resp = LLMResponse(
            role="err",
            completion_text=_DASHSCOPE_REQUEST_FAILURE,
            result_chain=chain,
        )
        return AgentResponse(type="err", data=AgentResponseData(chain=chain))

    async def _process_stream_chunk(
        self, chunk: ApplicationResponse, output_text: str
    ) -> tuple[str, list | None, AgentResponse | None]:
        """处理流式响应的单个chunk

        Args:
            chunk: Dashscope响应chunk
            output_text: 当前累积的输出文本

        Returns:
            (更新后的output_text, doc_references, AgentResponse或None)

        """
        logger.debug("Dashscope stream chunk: %s", safe_error("", str(chunk)))

        if chunk.status_code != 200:
            logger.error(
                "Dashscope request failed: request_id=%s, code=%s, message=%s",
                safe_error("", str(chunk.request_id)),
                chunk.status_code,
                safe_error("", chunk.message),
            )
            return output_text, None, self._failure_response()

        chunk_text = chunk.output.get("text", "") or ""
        # RAG 引用脚标格式化
        chunk_text = re.sub(r"<ref>\[(\d+)\]</ref>", r"[\1]", chunk_text)

        response = None
        if chunk_text:
            output_text += chunk_text
            if self.streaming:
                response = AgentResponse(
                    type="streaming_delta",
                    data=AgentResponseData(chain=MessageChain().message(chunk_text)),
                )

        # 获取文档引用
        doc_references = chunk.output.get("doc_references", None)

        return output_text, doc_references, response

    def _format_doc_references(self, doc_references: list) -> str:
        """格式化文档引用为文本

        Args:
            doc_references: 文档引用列表

        Returns:
            格式化后的引用文本

        """
        ref_parts = []
        for ref in doc_references:
            ref_title = (
                ref.get("title", "") if ref.get("title") else ref.get("doc_name", "")
            )
            ref_parts.append(f"{ref['index_id']}. {ref_title}\n")
        ref_str = "".join(ref_parts)
        return f"\n\n回答来源:\n{ref_str}"

    async def _build_request_payload(
        self, prompt: str, session_id: str, contexts: list, system_prompt: str
    ) -> dict:
        """构建请求payload

        Args:
            prompt: 用户输入
            session_id: 会话ID
            contexts: 上下文列表
            system_prompt: 系统提示词

        Returns:
            请求payload字典

        """
        conversation_id = await self.preferences.get_async(
            scope="umo",
            scope_id=session_id,
            key="dashscope_conversation_id",
            default="",
        )
        # 获得会话变量
        payload_vars = self.variables.copy()
        session_var = await self.preferences.get_async(
            scope="umo",
            scope_id=session_id,
            key="session_variables",
            default={},
        )
        if isinstance(session_var, dict):
            payload_vars.update(session_var)
        elif session_var:
            logger.warning("Dashscope session variables are malformed; ignoring.")

        if (
            self.dashscope_app_type in ["agent", "dialog-workflow"]
            and not self.has_rag_options()
        ):
            # 支持多轮对话的
            p = {
                "app_id": self.app_id,
                "api_key": self.api_key,
                "prompt": prompt,
                "biz_params": payload_vars or None,
                "stream": self.streaming,
                "incremental_output": True,
                "request_timeout": self.timeout,
            }
            if conversation_id:
                p["session_id"] = conversation_id
            return p
        else:
            # 不支持多轮对话的
            payload = {
                "app_id": self.app_id,
                "prompt": prompt,
                "api_key": self.api_key,
                "biz_params": payload_vars or None,
                "stream": self.streaming,
                "incremental_output": True,
                "request_timeout": self.timeout,
            }
            if self.rag_options:
                payload["rag_options"] = self.rag_options
            return payload

    async def _iter_application_responses(
        self, payload: dict
    ) -> T.AsyncGenerator[ApplicationResponse]:
        """Yield application responses through Dashscope's asynchronous transport.

        `Application.call` is synchronous, while its request implementation also
        exposes an aiohttp-based transport. Building the equivalent request here
        keeps a cancellation or timeout in the owning event loop instead of
        orphaning an executor worker or a synchronous stream-consumer thread.

        Args:
            payload: The Dashscope application call payload.

        Yields:
            Parsed Dashscope application responses.
        """
        request_kwargs = payload.copy()
        app_id = request_kwargs.pop("app_id")
        api_key = request_kwargs.pop("api_key")
        prompt = request_kwargs.pop("prompt")
        workspace = request_kwargs.pop("workspace", None)
        application_api = cast(Any, Application)
        api_key, app_id = application_api._validate_params(api_key, app_id)

        if workspace:
            headers = request_kwargs.pop("headers", {})
            headers["X-DashScope-WorkSpace"] = workspace
            request_kwargs["headers"] = headers

        request_input, parameters = application_api._build_input_parameters(
            prompt,
            None,
            None,
            **request_kwargs,
        )
        request = _build_api_request(
            model="",
            input=request_input,
            task_group=application_api.task_group,
            task=app_id,
            function=application_api.function,
            workspace=workspace,
            api_key=api_key,
            is_service=False,
            session=self._ensure_http_session(),
            **parameters,
        )

        if self.streaming:
            response_stream = await request.aio_call()
            if not isinstance(response_stream, AsyncGenerator):
                raise TypeError(
                    "Dashscope stream request returned a non-stream response."
                )
            try:
                async for raw_response in response_stream:
                    if isinstance(raw_response, ApplicationResponse):
                        yield raw_response
                    else:
                        yield ApplicationResponse.from_api_response(raw_response)
            finally:
                await response_stream.aclose()
            return

        raw_response = await request.aio_call()
        if isinstance(raw_response, AsyncIterator):
            raise TypeError("Dashscope non-stream request returned a response stream.")
        if isinstance(raw_response, ApplicationResponse):
            yield raw_response
        else:
            yield ApplicationResponse.from_api_response(raw_response)

    async def _handle_streaming_response(
        self,
        response_stream: T.AsyncGenerator[ApplicationResponse],
        session_id: str,
    ) -> T.AsyncGenerator[AgentResponse]:
        """Convert asynchronous Dashscope responses to AstrBot agent responses.

        Args:
            response_stream: Asynchronous Dashscope response stream.
            session_id: AstrBot session identifier used for conversation storage.

        Yields:
            Agent responses in the configured streaming mode.
        """
        output_text = ""
        doc_references = None

        try:
            async for chunk in response_stream:
                (
                    output_text,
                    chunk_doc_refs,
                    response,
                ) = await self._process_stream_chunk(chunk, output_text)

                if response:
                    if response.type == "err":
                        yield response
                        return
                    yield response

                if chunk_doc_refs:
                    doc_references = chunk_doc_refs

                chunk_session_id = getattr(chunk.output, "session_id", None)
                if chunk_session_id:
                    await self.preferences.put_async(
                        scope="umo",
                        scope_id=session_id,
                        key="dashscope_conversation_id",
                        value=chunk_session_id,
                    )

            if self.output_reference and doc_references:
                ref_text = self._format_doc_references(doc_references)
                output_text += ref_text

                if self.streaming:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(chain=MessageChain().message(ref_text)),
                    )

            chain = MessageChain(chain=[Comp.Plain(output_text)])
            self.final_llm_resp = LLMResponse(role="assistant", result_chain=chain)
            self._transition_state(AgentState.DONE)

            try:
                await self.agent_hooks.on_agent_done(
                    self.run_context, self.final_llm_resp
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Dashscope on_agent_done hook failed: %s",
                    safe_error("", exc),
                )

            yield AgentResponse(
                type="llm_result",
                data=AgentResponseData(chain=chain),
            )
        finally:
            await response_stream.aclose()

    async def _execute_dashscope_request(self):
        """执行 Dashscope 请求的核心逻辑"""
        prompt = self.req.prompt or ""
        session_id = self.req.session_id or "unknown"
        image_urls = self.req.image_urls or []
        contexts = self.req.contexts or []
        system_prompt = self.req.system_prompt

        # 检查图片输入
        if image_urls:
            logger.warning("阿里云百炼暂不支持图片输入，将自动忽略图片内容。")

        # 构建请求payload
        payload = await self._build_request_payload(
            prompt, session_id, contexts, system_prompt
        )

        if not self.streaming:
            payload["incremental_output"] = False

        # The SDK-level request timeout limits socket operations. The outer
        # deadline also bounds a continuously active stream and promptly closes
        # the aiohttp generator on cancellation.
        async with asyncio.timeout(self.timeout):
            async for resp in self._handle_streaming_response(
                self._iter_application_responses(payload),
                session_id,
            ):
                yield resp

    @override
    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    @override
    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
