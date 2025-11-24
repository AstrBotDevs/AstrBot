import base64
import os
import sys
import typing as T

import astrbot.core.message.components as Comp
from astrbot.core import logger, sp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import download_file

from ...hooks import BaseAgentRunHooks
from ...response import AgentResponseData
from ...run_context import ContextWrapper, TContext
from ..base import AgentResponse, AgentState, BaseAgentRunner
from .dify_api_client import DifyAPIClient

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class DifyAgentRunner(BaseAgentRunner[TContext]):
    """Dify Agent Runner"""

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

        self.api_key = provider_config.get("dify_api_key", "")
        self.api_base = provider_config.get("dify_api_base", "https://api.dify.ai/v1")
        self.api_type = provider_config.get("dify_api_type", "chat")
        self.workflow_output_key = provider_config.get(
            "dify_workflow_output_key",
            "astrbot_wf_output",
        )
        self.dify_query_input_key = provider_config.get(
            "dify_query_input_key",
            "astrbot_text_query",
        )
        self.variables: dict = provider_config.get("variables", {}) or {}
        self.timeout = provider_config.get("timeout", 60)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)

        self.api_client = DifyAPIClient(self.api_key, self.api_base)

    @override
    async def step(self):
        """
        执行 Dify Agent 的一个步骤
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
            # 执行 Dify 请求并处理结果
            async for response in self._execute_dify_request():
                yield response
        except Exception as e:
            logger.error(f"Dify 请求失败：{str(e)}")
            self._transition_state(AgentState.ERROR)
            self.final_llm_resp = LLMResponse(
                role="err", completion_text=f"Dify 请求失败：{str(e)}"
            )
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(f"Dify 请求失败：{str(e)}")
                ),
            )
        finally:
            await self.api_client.close()

    @override
    async def step_until_done(
        self, max_step: int = 30
    ) -> T.AsyncGenerator[AgentResponse, None]:
        while not self.done():
            async for resp in self.step():
                yield resp

    async def _execute_dify_request(self):
        """执行 Dify 请求的核心逻辑"""
        prompt = self.req.prompt or ""
        session_id = self.req.session_id or "unknown"
        image_urls = self.req.image_urls or []
        system_prompt = self.req.system_prompt

        conversation_id = await sp.get_async(
            scope="umo",
            scope_id=session_id,
            key="dify_conversation_id",
            default="",
        )
        result = ""

        # 处理图片上传
        files_payload = []
        for image_url in image_urls:
            # image_url is a base64 string
            try:
                image_data = base64.b64decode(image_url)
                file_response = await self.api_client.file_upload(
                    file_data=image_data,
                    user=session_id,
                    mime_type="image/png",
                    file_name="image.png",
                )
                logger.debug(f"Dify 上传图片响应：{file_response}")
                if "id" not in file_response:
                    logger.warning(
                        f"上传图片后得到未知的 Dify 响应：{file_response}，图片将忽略。"
                    )
                    continue
                files_payload.append(
                    {
                        "type": "image",
                        "transfer_method": "local_file",
                        "upload_file_id": file_response["id"],
                    }
                )
            except Exception as e:
                logger.warning(f"上传图片失败：{e}")
                continue

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
        payload_vars["system_prompt"] = system_prompt

        # 处理不同的 API 类型
        match self.api_type:
            case "chat" | "agent" | "chatflow":
                if not prompt:
                    prompt = "请描述这张图片。"

                async for chunk in self.api_client.chat_messages(
                    inputs={
                        **payload_vars,
                    },
                    query=prompt,
                    user=session_id,
                    conversation_id=conversation_id,
                    files=files_payload,
                    timeout=self.timeout,
                ):
                    logger.debug(f"dify resp chunk: {chunk}")
                    if chunk["event"] == "message" or chunk["event"] == "agent_message":
                        result += chunk["answer"]
                        if not conversation_id:
                            await sp.put_async(
                                scope="umo",
                                scope_id=session_id,
                                key="dify_conversation_id",
                                value=chunk["conversation_id"],
                            )
                            conversation_id = chunk["conversation_id"]

                        # 如果是流式响应，发送增量数据
                        if self.streaming and chunk["answer"]:
                            yield AgentResponse(
                                type="streaming_delta",
                                data=AgentResponseData(
                                    chain=MessageChain().message(chunk["answer"])
                                ),
                            )
                    elif chunk["event"] == "message_end":
                        logger.debug("Dify message end")
                        break
                    elif chunk["event"] == "error":
                        logger.error(f"Dify 出现错误：{chunk}")
                        raise Exception(
                            f"Dify 出现错误 status: {chunk['status']} message: {chunk['message']}"
                        )

            case "workflow":
                async for chunk in self.api_client.workflow_run(
                    inputs={
                        self.dify_query_input_key: prompt,
                        "astrbot_session_id": session_id,
                        **payload_vars,
                    },
                    user=session_id,
                    files=files_payload,
                    timeout=self.timeout,
                ):
                    logger.debug(f"dify workflow resp chunk: {chunk}")
                    match chunk["event"]:
                        case "workflow_started":
                            logger.info(
                                f"Dify 工作流(ID: {chunk['workflow_run_id']})开始运行。"
                            )
                        case "node_finished":
                            logger.debug(
                                f"Dify 工作流节点(ID: {chunk['data']['node_id']} Title: {chunk['data'].get('title', '')})运行结束。"
                            )
                        case "text_chunk":
                            if self.streaming and chunk["data"]["text"]:
                                yield AgentResponse(
                                    type="streaming_delta",
                                    data=AgentResponseData(
                                        chain=MessageChain().message(
                                            chunk["data"]["text"]
                                        )
                                    ),
                                )
                        case "workflow_finished":
                            logger.info(
                                f"Dify 工作流(ID: {chunk['workflow_run_id']})运行结束"
                            )
                            logger.debug(f"Dify 工作流结果：{chunk}")
                            if chunk["data"]["error"]:
                                logger.error(
                                    f"Dify 工作流出现错误：{chunk['data']['error']}"
                                )
                                raise Exception(
                                    f"Dify 工作流出现错误：{chunk['data']['error']}"
                                )
                            if self.workflow_output_key not in chunk["data"]["outputs"]:
                                raise Exception(
                                    f"Dify 工作流的输出不包含指定的键名：{self.workflow_output_key}"
                                )
                            result = chunk
            case _:
                raise Exception(f"未知的 Dify API 类型：{self.api_type}")

        if not result:
            logger.warning("Dify 请求结果为空，请查看 Debug 日志。")

        # 解析结果
        chain = await self.parse_dify_result(result)

        # 创建最终响应
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

    async def parse_dify_result(self, chunk: dict | str) -> MessageChain:
        """解析 Dify 的响应结果"""
        if isinstance(chunk, str):
            # Chat
            return MessageChain(chain=[Comp.Plain(chunk)])

        async def parse_file(item: dict):
            match item["type"]:
                case "image":
                    return Comp.Image(file=item["url"], url=item["url"])
                case "audio":
                    # 仅支持 wav
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    path = os.path.join(temp_dir, f"{item['filename']}.wav")
                    await download_file(item["url"], path)
                    return Comp.Image(file=item["url"], url=item["url"])
                case "video":
                    return Comp.Video(file=item["url"])
                case _:
                    return Comp.File(name=item["filename"], file=item["url"])

        output = chunk["data"]["outputs"][self.workflow_output_key]
        chains = []
        if isinstance(output, str):
            # 纯文本输出
            chains.append(Comp.Plain(output))
        elif isinstance(output, list):
            # 主要适配 Dify 的 HTTP 请求结点的多模态输出
            for item in output:
                # handle Array[File]
                if (
                    not isinstance(item, dict)
                    or item.get("dify_model_identity", "") != "__dify__file__"
                ):
                    chains.append(Comp.Plain(str(output)))
                    break
        else:
            chains.append(Comp.Plain(str(output)))

        # scan file
        files = chunk["data"].get("files", [])
        for item in files:
            comp = await parse_file(item)
            chains.append(comp)

        return MessageChain(chain=chains)

    @override
    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    @override
    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
