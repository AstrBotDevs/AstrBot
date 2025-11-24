import asyncio
import functools
import queue
import re
import sys
import threading
import typing as T

from dashscope import Application
from dashscope.app.application_response import ApplicationResponse

import astrbot.core.message.components as Comp
from astrbot.core import logger, sp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
)

from ...hooks import BaseAgentRunHooks
from ...response import AgentResponseData
from ...run_context import ContextWrapper, TContext
from ..base import AgentResponse, AgentState, BaseAgentRunner

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class DashscopeAgentRunner(BaseAgentRunner[TContext]):
    """Dashscope Agent Runner"""

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

        self.api_key = provider_config.get("dashscope_api_key", "")
        if not self.api_key:
            raise Exception("阿里云百炼 API Key 不能为空。")
        self.app_id = provider_config.get("dashscope_app_id", "")
        if not self.app_id:
            raise Exception("阿里云百炼 APP ID 不能为空。")
        self.dashscope_app_type = provider_config.get("dashscope_app_type", "")
        if not self.dashscope_app_type:
            raise Exception("阿里云百炼 APP 类型不能为空。")

        self.variables: dict = provider_config.get("variables", {}) or {}
        self.rag_options: dict = provider_config.get("rag_options", {})
        self.output_reference = self.rag_options.get("output_reference", False)
        self.rag_options = self.rag_options.copy()
        self.rag_options.pop("output_reference", None)

        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)

    def has_rag_options(self):
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
            except Exception as e:
                logger.error(f"Error in on_agent_begin hook: {e}", exc_info=True)

        # 开始处理，转换到运行状态
        self._transition_state(AgentState.RUNNING)

        try:
            # 执行 Dashscope 请求并处理结果
            async for response in self._execute_dashscope_request():
                yield response
        except Exception as e:
            logger.error(f"阿里云百炼请求失败：{str(e)}")
            self._transition_state(AgentState.ERROR)
            self.final_llm_resp = LLMResponse(
                role="err", completion_text=f"阿里云百炼请求失败：{str(e)}"
            )
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(f"阿里云百炼请求失败：{str(e)}")
                ),
            )

    @override
    async def step_until_done(
        self, max_step: int = 30
    ) -> T.AsyncGenerator[AgentResponse, None]:
        while not self.done():
            async for resp in self.step():
                yield resp

    def _consume_sync_generator(
        self, response: T.Any, response_queue: queue.Queue
    ) -> None:
        """在线程中消费同步generator,将结果放入队列

        Args:
            response: 同步generator对象
            response_queue: 用于传递数据的队列

        """
        try:
            if self.streaming:
                for chunk in response:
                    response_queue.put(("data", chunk))
            else:
                response_queue.put(("data", response))
        except Exception as e:
            response_queue.put(("error", e))
        finally:
            response_queue.put(("done", None))

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
        logger.debug(f"dashscope stream chunk: {chunk}")

        if chunk.status_code != 200:
            logger.error(
                f"阿里云百炼请求失败: request_id={chunk.request_id}, code={chunk.status_code}, message={chunk.message}, 请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code",
            )
            self._transition_state(AgentState.ERROR)
            error_msg = (
                f"阿里云百炼请求失败: message={chunk.message} code={chunk.status_code}"
            )
            self.final_llm_resp = LLMResponse(
                role="err",
                result_chain=MessageChain().message(error_msg),
            )
            return (
                output_text,
                None,
                AgentResponse(
                    type="err",
                    data=AgentResponseData(chain=MessageChain().message(error_msg)),
                ),
            )

        chunk_text = chunk.output.get("text", "") or ""
        # RAG 引用脚标格式化
        chunk_text = re.sub(r"<ref>\[(\d+)\]</ref>", r"[\1]", chunk_text)

        response = None
        if chunk_text:
            output_text += chunk_text
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
        conversation_id = await sp.get_async(
            scope="umo",
            scope_id=session_id,
            key="dashscope_conversation_id",
            default="",
        )
        # 获得会话变量
        payload_vars = self.variables.copy()
        session_var = await sp.get_async(
            scope="umo",
            scope_id=session_id,
            key="session_variables",
            default={},
        )
        payload_vars.update(session_var)

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
            }
            if self.rag_options:
                payload["rag_options"] = self.rag_options
            return payload

    async def _handle_streaming_response(
        self, response: T.Any, session_id: str
    ) -> T.AsyncGenerator[AgentResponse, None]:
        """处理流式响应

        Args:
            response: Dashscope 流式响应 generator

        Yields:
            AgentResponse 对象

        """
        response_queue = queue.Queue()
        consumer_thread = threading.Thread(
            target=self._consume_sync_generator,
            args=(response, response_queue),
            daemon=True,
        )
        consumer_thread.start()

        output_text = ""
        doc_references = None

        while True:
            try:
                item_type, item_data = await asyncio.get_event_loop().run_in_executor(
                    None, response_queue.get, True, 1
                )
            except queue.Empty:
                continue

            if item_type == "done":
                break
            elif item_type == "error":
                raise item_data
            elif item_type == "data":
                chunk = item_data
                assert isinstance(chunk, ApplicationResponse)

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

                if chunk.output.session_id:
                    await sp.put_async(
                        scope="umo",
                        scope_id=session_id,
                        key="dashscope_conversation_id",
                        value=chunk.output.session_id,
                    )

        # 添加 RAG 引用
        if self.output_reference and doc_references:
            ref_text = self._format_doc_references(doc_references)
            output_text += ref_text

            if self.streaming:
                yield AgentResponse(
                    type="streaming_delta",
                    data=AgentResponseData(chain=MessageChain().message(ref_text)),
                )

        # 创建最终响应
        chain = MessageChain(chain=[Comp.Plain(output_text)])
        self.final_llm_resp = LLMResponse(role="assistant", result_chain=chain)
        self._transition_state(AgentState.DONE)

        try:
            await self.agent_hooks.on_agent_done(self.run_context, self.final_llm_resp)
        except Exception as e:
            logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)

        # 返回最终结果
        yield AgentResponse(
            type="llm_result",
            data=AgentResponseData(chain=chain),
        )

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

        # 发起请求
        partial = functools.partial(Application.call, **payload)
        response = await asyncio.get_event_loop().run_in_executor(None, partial)

        async for resp in self._handle_streaming_response(response, session_id):
            yield resp

    @override
    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    @override
    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
