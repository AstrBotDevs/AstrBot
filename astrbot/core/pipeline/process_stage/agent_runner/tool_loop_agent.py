import sys
import traceback
import typing as T
from .base import BaseAgentRunner, AgentResponse
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

    @override
    async def reset(self, req: ProviderRequest, streaming: bool) -> None:
        self.req = req
        self.streaming = streaming
        self.final_llm_resp = None
        self.is_done = False

    @override
    async def step(self):
        """
        Process a single step of the agent.
        This method should return the result of the step.
        """
        if not self.req:
            raise ValueError("Request is not set. Please call reset() first.")

        # 执行 LLM 请求
        llm_resp_result = None
        if self.streaming:
            stream = self.provider.text_chat_stream(**self.req.__dict__)
            async for llm_response in stream:  # type: ignore
                assert isinstance(llm_response, LLMResponse)
                if llm_response.is_chunk:
                    if llm_response.result_chain:
                        yield AgentResponse(
                            type="streaming_delta",
                            data={
                                "chain": llm_response.result_chain.chain,
                            },
                        )
                    else:
                        yield AgentResponse(
                            type="streaming_delta",
                            data={
                                "chain": MessageChain().message(
                                    llm_response.completion_text
                                ),
                            },
                        )
                else:
                    llm_resp_result = llm_response
        else:
            llm_resp_result = await self.provider.text_chat(**self.req.__dict__)

        if not llm_resp_result:
            return

        # 执行事件钩子
        await self.pipeline_ctx.call_event_hook(
            self.event, EventType.OnLLMResponseEvent, self.final_llm_resp
        )

        # 处理 LLM 响应
        llm_resp = llm_resp_result
        logger.info(f"LLMResp: {llm_resp}")
        if llm_resp.role == "err":
            # 如果 LLM 响应错误，直接返回错误信息
            self.final_llm_resp = llm_resp
            self.is_done = True
            yield AgentResponse(
                type="err",
                data={
                    "chain": MessageChain().message(
                        f"LLM 响应错误: {llm_resp.completion_text or '未知错误'}"
                    ),
                },
            )

        if not llm_resp.tools_call_name:
            # 如果没有工具调用，结束 Agent Loop
            self.final_llm_resp = llm_resp
            self.is_done = True

        # 返回 LLM 结果
        if llm_resp.result_chain:
            yield AgentResponse(
                type="llm_result",
                data={
                    "chain": llm_resp.result_chain.chain,
                },
            )
        elif llm_resp.completion_text:
            yield AgentResponse(
                type="llm_result",
                data={
                    "chain": MessageChain().message(llm_resp.completion_text),
                },
            )

        # 如果有工具调用，还需处理工具调用
        if llm_resp.tools_call_name:
            tool_call_result_blocks = []
            async for result in self._handle_function_tools(self.req, llm_resp):
                if isinstance(result, list):
                    tool_call_result_blocks = result
                elif isinstance(result, MessageChain):
                    yield AgentResponse(
                        type="tool_call_result",
                        data={
                            "chain": result.chain,
                        },
                    )
            # 将结果添加到上下文中
            tool_calls_result = ToolCallsResult(
                tool_calls_info=AssistantMessageSegment(
                    role="assistant", tool_calls=llm_resp.to_openai_tool_calls()
                ),
                tool_calls_result=tool_call_result_blocks,
            )
            self.req.append_tool_calls_result(tool_calls_result)

        logger.info("done: %s", self.is_done)

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
                        else:
                            # Tool 直接请求发送消息给用户
                            # 这里我们将直接结束 Agent Loop。
                            self.is_done = True
                            if res := self.event.get_result():
                                if res.chain:
                                    yield MessageChain(chain=res.chain)

                self.event.clear_result()
            except BaseException as e:
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
        return self.is_done

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
