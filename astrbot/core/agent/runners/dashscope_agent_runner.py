import asyncio
import functools
import re
import sys
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

from ..hooks import BaseAgentRunHooks
from ..response import AgentResponseData
from ..run_context import ContextWrapper, TContext
from .base import AgentResponse, AgentState, BaseAgentRunner

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

    async def _remove_image_from_context(self, contexts: list) -> list:
        """移除上下文中的图片内容"""
        result = []
        for ctx in contexts:
            if isinstance(ctx, dict):
                content = ctx.get("content", "")
                if isinstance(content, list):
                    # 只保留文本内容
                    text_parts = [
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    ]
                    if text_parts:
                        new_ctx = ctx.copy()
                        new_ctx["content"] = " ".join(text_parts)
                        result.append(new_ctx)
                else:
                    result.append(ctx)
            else:
                result.append(ctx)
        return result

    async def _execute_dashscope_request(self):
        """执行 Dashscope 请求的核心逻辑"""
        prompt = self.req.prompt or ""
        session_id = self.req.session_id or "unknown"
        image_urls = self.req.image_urls or []
        contexts = self.req.contexts or []
        system_prompt = self.req.system_prompt

        # 获得会话变量
        payload_vars = self.variables.copy()
        # 动态变量
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
            new_record = {"role": "user", "content": prompt}
            if image_urls:
                logger.warning("阿里云百炼暂不支持图片输入，将自动忽略图片内容。")
            contexts_no_img = await self._remove_image_from_context(contexts)
            context_query = [*contexts_no_img, new_record]
            if system_prompt:
                context_query.insert(0, {"role": "system", "content": system_prompt})
            for part in context_query:
                if "_no_save" in part:
                    del part["_no_save"]
            # 调用阿里云百炼 API
            payload = {
                "app_id": self.app_id,
                "api_key": self.api_key,
                "messages": context_query,
                "biz_params": payload_vars or None,
            }
            partial = functools.partial(
                Application.call,
                **payload,
            )
            response = await asyncio.get_event_loop().run_in_executor(None, partial)
        else:
            # 不支持多轮对话的
            # 调用阿里云百炼 API
            payload = {
                "app_id": self.app_id,
                "prompt": prompt,
                "api_key": self.api_key,
                "biz_params": payload_vars or None,
            }
            if self.rag_options:
                payload["rag_options"] = self.rag_options
            partial = functools.partial(
                Application.call,
                **payload,
            )
            response = await asyncio.get_event_loop().run_in_executor(None, partial)

        assert isinstance(response, ApplicationResponse)

        logger.debug(f"dashscope resp: {response}")

        if response.status_code != 200:
            logger.error(
                f"阿里云百炼请求失败: request_id={response.request_id}, code={response.status_code}, message={response.message}, 请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code",
            )
            self._transition_state(AgentState.ERROR)
            self.final_llm_resp = LLMResponse(
                role="err",
                result_chain=MessageChain().message(
                    f"阿里云百炼请求失败: message={response.message} code={response.status_code}",
                ),
            )
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(
                        f"阿里云百炼请求失败: message={response.message} code={response.status_code}"
                    )
                ),
            )
            return

        output_text = response.output.get("text", "") or ""
        # RAG 引用脚标格式化
        output_text = re.sub(r"<ref>\[(\d+)\]</ref>", r"[\1]", output_text)
        if self.output_reference and response.output.get("doc_references", None):
            ref_parts = []
            for ref in response.output.get("doc_references", []) or []:
                ref_title = (
                    ref.get("title", "")
                    if ref.get("title")
                    else ref.get("doc_name", "")
                )
                ref_parts.append(f"{ref['index_id']}. {ref_title}\n")
            ref_str = "".join(ref_parts)
            output_text += f"\n\n回答来源:\n{ref_str}"

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

    @override
    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    @override
    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
