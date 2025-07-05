import sys
import traceback
import typing as T
from .base import BaseAgentRunner, AgentResponse, AgentResponseData, AgentState
from ...context import PipelineContext
from astrbot.core.provider.provider import Provider
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import (
    MessageChain,
)
from astrbot.core.provider.entities import (
    ProviderRequest,
    LLMResponse,
    ToolCallMessageSegment,
    AssistantMessageSegment,
    ToolCallsResult,
)
from mcp.types import (
    TextContent,
    ImageContent,
    EmbeddedResource,
    TextResourceContents,
    BlobResourceContents,
)
from astrbot.core.star.star_handler import EventType
from astrbot import logger

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


# TODO:
# 1. 处理平台不兼容的处理器


class ToolLoopAgent(BaseAgentRunner):
    def __init__(
        self, provider: Provider, event: AstrMessageEvent, pipeline_ctx: PipelineContext
    ) -> None:
        self.provider = provider
        self.req = None
        self.event = event
        self.pipeline_ctx = pipeline_ctx
        self._state = AgentState.IDLE
        self.final_llm_resp = None
        self.streaming = False

    @override
    async def reset(self, req: ProviderRequest, streaming: bool) -> None:
        self.req = req
        self.streaming = streaming
        self.final_llm_resp = None
        self._state = AgentState.IDLE

    def _transition_state(self, new_state: AgentState) -> None:
        """转换 Agent 状态"""
        if self._state != new_state:
            logger.debug(f"Agent state transition: {self._state} -> {new_state}")
            self._state = new_state

    async def _iter_llm_responses(self) -> T.AsyncGenerator[LLMResponse, None]:
        """Yields chunks *and* a final LLMResponse."""
        if self.streaming:
            stream = self.provider.text_chat_stream(**self.req.__dict__)
            async for resp in stream:  # type: ignore
                yield resp
        else:
            yield await self.provider.text_chat(**self.req.__dict__)

    @override
    async def step(self):
        """
        Process a single step of the agent.
        This method should return the result of the step.
        """
        if not self.req:
            raise ValueError("Request is not set. Please call reset() first.")

        # 开始处理，转换到运行状态
        self._transition_state(AgentState.RUNNING)
        llm_resp_result = None

        async for llm_response in self._iter_llm_responses():
            assert isinstance(llm_response, LLMResponse)
            if llm_response.is_chunk:
                if llm_response.result_chain:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(chain=llm_response.result_chain),
                    )
                else:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain().message(llm_response.completion_text)
                        ),
                    )
                continue
            llm_resp_result = llm_response
            break  # got final response

        if not llm_resp_result:
            return

        # 处理 LLM 响应
        llm_resp = llm_resp_result

        if llm_resp.role == "err":
            # 如果 LLM 响应错误，转换到错误状态
            self.final_llm_resp = llm_resp
            self._transition_state(AgentState.ERROR)
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(
                        f"LLM 响应错误: {llm_resp.completion_text or '未知错误'}"
                    )
                ),
            )

        if not llm_resp.tools_call_name:
            # 如果没有工具调用，转换到完成状态
            self.final_llm_resp = llm_resp
            self._transition_state(AgentState.DONE)

            # 执行事件钩子
            if await self.pipeline_ctx.call_event_hook(
                self.event, EventType.OnLLMResponseEvent, llm_resp
            ):
                return

        # 返回 LLM 结果
        if llm_resp.result_chain:
            yield AgentResponse(
                type="llm_result",
                data=AgentResponseData(chain=llm_resp.result_chain),
            )
        elif llm_resp.completion_text:
            yield AgentResponse(
                type="llm_result",
                data=AgentResponseData(
                    chain=MessageChain().message(llm_resp.completion_text)
                ),
            )

        # 如果有工具调用，还需处理工具调用
        if llm_resp.tools_call_name:
            tool_call_result_blocks = []
            for tool_call_name in llm_resp.tools_call_name:
                yield AgentResponse(
                    type="tool_call",
                    data=AgentResponseData(
                        chain=MessageChain().message(f"🔨 调用工具: {tool_call_name}")
                    ),
                )
            async for result in self._handle_function_tools(self.req, llm_resp):
                if isinstance(result, list):
                    tool_call_result_blocks = result
                elif isinstance(result, MessageChain):
                    yield AgentResponse(
                        type="tool_call_result",
                        data=AgentResponseData(chain=result),
                    )
            # 将结果添加到上下文中
            tool_calls_result = ToolCallsResult(
                tool_calls_info=AssistantMessageSegment(
                    role="assistant",
                    tool_calls=llm_resp.to_openai_tool_calls(),
                    content=llm_resp.completion_text,
                ),
                tool_calls_result=tool_call_result_blocks,
            )
            self.req.append_tool_calls_result(tool_calls_result)

    async def _handle_function_tools(
        self,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> T.AsyncGenerator[MessageChain | list[ToolCallMessageSegment], None]:
        """处理函数工具调用。"""
        tool_call_result_blocks: list[ToolCallMessageSegment] = []
        logger.info(f"Agent 使用工具: {llm_response.tools_call_name}")

        # 执行函数调用
        for func_tool_name, func_tool_args, func_tool_id in zip(
            llm_response.tools_call_name,
            llm_response.tools_call_args,
            llm_response.tools_call_ids,
        ):
            try:
                if not req.func_tool:
                    return
                func_tool = req.func_tool.get_func(func_tool_name)
                if func_tool.origin == "mcp":
                    logger.info(
                        f"从 MCP 服务 {func_tool.mcp_server_name} 调用工具函数：{func_tool.name}，参数：{func_tool_args}"
                    )
                    client = req.func_tool.mcp_client_dict[func_tool.mcp_server_name]
                    res = await client.session.call_tool(func_tool.name, func_tool_args)
                    if not res:
                        continue
                    if isinstance(res.content[0], TextContent):
                        tool_call_result_blocks.append(
                            ToolCallMessageSegment(
                                role="tool",
                                tool_call_id=func_tool_id,
                                content=res.content[0].text,
                            )
                        )
                        yield MessageChain().message(res.content[0].text)
                    elif isinstance(res.content[0], ImageContent):
                        tool_call_result_blocks.append(
                            ToolCallMessageSegment(
                                role="tool",
                                tool_call_id=func_tool_id,
                                content="返回了图片(已直接发送给用户)",
                            )
                        )
                        yield MessageChain().base64_image(res.content[0].data)
                    elif isinstance(res.content[0], EmbeddedResource):
                        resource = res.content[0].resource
                        if isinstance(resource, TextResourceContents):
                            tool_call_result_blocks.append(
                                ToolCallMessageSegment(
                                    role="tool",
                                    tool_call_id=func_tool_id,
                                    content=resource.text,
                                )
                            )
                            yield MessageChain().message(resource.text)
                        elif (
                            isinstance(resource, BlobResourceContents)
                            and resource.mimeType
                            and resource.mimeType.startswith("image/")
                        ):
                            tool_call_result_blocks.append(
                                ToolCallMessageSegment(
                                    role="tool",
                                    tool_call_id=func_tool_id,
                                    content="返回了图片(已直接发送给用户)",
                                )
                            )
                            yield MessageChain().base64_image(res.content[0].data)
                        else:
                            tool_call_result_blocks.append(
                                ToolCallMessageSegment(
                                    role="tool",
                                    tool_call_id=func_tool_id,
                                    content="返回的数据类型不受支持",
                                )
                            )
                            yield MessageChain().message("返回的数据类型不受支持。")
                else:
                    logger.info(f"使用工具：{func_tool_name}，参数：{func_tool_args}")
                    # 尝试调用工具函数
                    wrapper = self.pipeline_ctx.call_handler(
                        self.event, func_tool.handler, **func_tool_args
                    )
                    async for resp in wrapper:
                        if resp is not None:
                            # Tool 返回结果
                            tool_call_result_blocks.append(
                                ToolCallMessageSegment(
                                    role="tool",
                                    tool_call_id=func_tool_id,
                                    content=resp,
                                )
                            )
                            yield MessageChain().message(resp)
                        else:
                            # Tool 直接请求发送消息给用户
                            # 这里我们将直接结束 Agent Loop。
                            self._transition_state(AgentState.DONE)
                            if res := self.event.get_result():
                                if res.chain:
                                    yield MessageChain(chain=res.chain)

                self.event.clear_result()
            except Exception as e:
                logger.warning(traceback.format_exc())
                tool_call_result_blocks.append(
                    ToolCallMessageSegment(
                        role="tool",
                        tool_call_id=func_tool_id,
                        content=f"error: {str(e)}",
                    )
                )

        # 处理函数调用响应
        if tool_call_result_blocks:
            yield tool_call_result_blocks

    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
