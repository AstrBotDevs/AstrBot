import sys
import time
import traceback
import typing as T

from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    TextContent,
    TextResourceContents,
)

from astrbot import logger
from astrbot.core.agent.message import TextPart, ThinkPart
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import (
    MessageChain,
)
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
    ToolCallsResult,
)
from astrbot.core.provider.provider import Provider

from ..context.compressor import ContextCompressor
from ..context.config import ContextConfig
from ..context.manager import ContextManager
from ..context.token_counter import TokenCounter
from ..hooks import BaseAgentRunHooks
from ..message import AssistantMessageSegment, Message, ToolCallMessageSegment
from ..response import AgentResponseData, AgentStats
from ..run_context import ContextWrapper, TContext
from ..tool_executor import BaseFunctionToolExecutor
from .base import AgentResponse, AgentState, BaseAgentRunner

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class ToolLoopAgentRunner(BaseAgentRunner[TContext]):
    @override
    async def reset(
        self,
        provider: Provider,
        request: ProviderRequest,
        run_context: ContextWrapper[TContext],
        tool_executor: BaseFunctionToolExecutor[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        streaming: bool = False,
        # enforce max turns, will discard older turns when exceeded BEFORE compression
        # -1 means no limit
        enforce_max_turns: int = -1,
        # llm compressor
        llm_compress_instruction: str | None = None,
        llm_compress_keep_recent: int = 0,
        llm_compress_provider: Provider | None = None,
        # truncate by turns compressor
        truncate_turns: int = 1,
        # customize
        custom_token_counter: TokenCounter | None = None,
        custom_compressor: ContextCompressor | None = None,
        **kwargs: T.Any,
    ) -> None:
        self.req = request
        self.streaming = streaming
        self.enforce_max_turns = enforce_max_turns
        self.llm_compress_instruction = llm_compress_instruction
        self.llm_compress_keep_recent = llm_compress_keep_recent
        self.llm_compress_provider = llm_compress_provider
        self.truncate_turns = truncate_turns
        self.custom_token_counter = custom_token_counter
        self.custom_compressor = custom_compressor
        # we will do compress when:
        # 1. before requesting LLM
        # TODO: 2. after LLM output a tool call
        self.context_config = ContextConfig(
            # <=0 will never do compress
            max_context_tokens=provider.provider_config.get("max_context_tokens", 0),
            # enforce max turns before compression
            enforce_max_turns=self.enforce_max_turns,
            truncate_turns=self.truncate_turns,
            llm_compress_instruction=self.llm_compress_instruction,
            llm_compress_keep_recent=self.llm_compress_keep_recent,
            llm_compress_provider=self.llm_compress_provider,
            custom_token_counter=self.custom_token_counter,
            custom_compressor=self.custom_compressor,
        )
        self.context_manager = ContextManager(self.context_config)

        self.provider = provider
        self.final_llm_resp = None
        self._state = AgentState.IDLE
        self.tool_executor = tool_executor
        self.agent_hooks = agent_hooks
        self.run_context = run_context

        messages = []
        # append existing messages in the run context
        for msg in request.contexts:
            messages.append(Message.model_validate(msg))
        if request.prompt is not None:
            m = await request.assemble_context()
            messages.append(Message.model_validate(m))
        if request.system_prompt:
            messages.insert(
                0,
                Message(role="system", content=request.system_prompt),
            )
        self.run_context.messages = messages

        self.stats = AgentStats()
        self.stats.start_time = time.time()

    async def _iter_llm_responses(self) -> T.AsyncGenerator[LLMResponse, None]:
        """Yields chunks *and* a final LLMResponse."""
        payload = {
            "contexts": self.run_context.messages,  # list[Message]
            "func_tool": self.req.func_tool,
            "model": self.req.model,  # NOTE: in fact, this arg is None in most cases
            "session_id": self.req.session_id,
            "extra_user_content_parts": self.req.extra_user_content_parts,  # list[ContentPart]
        }

        if self.streaming:
            stream = self.provider.text_chat_stream(**payload)
            async for resp in stream:  # type: ignore
                yield resp
        else:
            yield await self.provider.text_chat(**payload)

    @override
    async def step(self):
        """Process a single step of the agent.
        This method should return the result of the step.
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
        llm_resp_result = None

        # do truncate and compress
        token_usage = self.req.conversation.token_usage if self.req.conversation else 0
        self.run_context.messages = await self.context_manager.process(
            self.run_context.messages, trusted_token_usage=token_usage
        )

        async for llm_response in self._iter_llm_responses():
            if llm_response.is_chunk:
                # update ttft
                if self.stats.time_to_first_token == 0:
                    self.stats.time_to_first_token = time.time() - self.stats.start_time

                if llm_response.result_chain:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(chain=llm_response.result_chain),
                    )
                elif llm_response.completion_text:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain().message(llm_response.completion_text),
                        ),
                    )
                elif llm_response.reasoning_content:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain(type="reasoning").message(
                                llm_response.reasoning_content,
                            ),
                        ),
                    )
                continue
            llm_resp_result = llm_response

            if not llm_response.is_chunk and llm_response.usage:
                # only count the token usage of the final response for computation purpose
                self.stats.token_usage += llm_response.usage
            break  # got final response

        if not llm_resp_result:
            return

        # 处理 LLM 响应
        llm_resp = llm_resp_result

        if llm_resp.role == "err":
            # 如果 LLM 响应错误，转换到错误状态
            self.final_llm_resp = llm_resp
            self.stats.end_time = time.time()
            self._transition_state(AgentState.ERROR)
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(
                        f"LLM 响应错误: {llm_resp.completion_text or '未知错误'}",
                    ),
                ),
            )

        if not llm_resp.tools_call_name:
            # 如果没有工具调用，转换到完成状态
            self.final_llm_resp = llm_resp
            self._transition_state(AgentState.DONE)
            self.stats.end_time = time.time()

            # record the final assistant message
            parts = []
            if llm_resp.reasoning_content or llm_resp.reasoning_signature:
                parts.append(
                    ThinkPart(
                        think=llm_resp.reasoning_content,
                        encrypted=llm_resp.reasoning_signature,
                    )
                )
            if llm_resp.completion_text:
                parts.append(TextPart(text=llm_resp.completion_text))
            self.run_context.messages.append(Message(role="assistant", content=parts))

            # call the on_agent_done hook
            try:
                await self.agent_hooks.on_agent_done(self.run_context, llm_resp)
            except Exception as e:
                logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)

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
                    chain=MessageChain().message(llm_resp.completion_text),
                ),
            )

        # 如果有工具调用，还需处理工具调用
        if llm_resp.tools_call_name:
            tool_call_result_blocks = []
            async for result in self._handle_function_tools(self.req, llm_resp):
                if isinstance(result, list):
                    tool_call_result_blocks = result
                elif isinstance(result, MessageChain):
                    if result.type is None:
                        # should not happen
                        continue
                    if result.type == "tool_direct_result":
                        ar_type = "tool_call_result"
                    else:
                        ar_type = result.type
                    yield AgentResponse(
                        type=ar_type,
                        data=AgentResponseData(chain=result),
                    )
            # 将结果添加到上下文中
            parts = []
            if llm_resp.reasoning_content or llm_resp.reasoning_signature:
                parts.append(
                    ThinkPart(
                        think=llm_resp.reasoning_content,
                        encrypted=llm_resp.reasoning_signature,
                    )
                )
            if llm_resp.completion_text:
                parts.append(TextPart(text=llm_resp.completion_text))
            tool_calls_result = ToolCallsResult(
                tool_calls_info=AssistantMessageSegment(
                    tool_calls=llm_resp.to_openai_to_calls_model(),
                    content=parts,
                ),
                tool_calls_result=tool_call_result_blocks,
            )
            # record the assistant message with tool calls
            self.run_context.messages.extend(
                tool_calls_result.to_openai_messages_model()
            )

            self.req.append_tool_calls_result(tool_calls_result)

    async def step_until_done(
        self, max_step: int
    ) -> T.AsyncGenerator[AgentResponse, None]:
        """Process steps until the agent is done."""
        step_count = 0
        while not self.done() and step_count < max_step:
            step_count += 1
            async for resp in self.step():
                yield resp

        #  如果循环结束了但是 agent 还没有完成，说明是达到了 max_step
        if not self.done():
            logger.warning(
                f"Agent reached max steps ({max_step}), forcing a final response."
            )
            # 拔掉所有工具
            if self.req:
                self.req.func_tool = None
            # 注入提示词
            self.run_context.messages.append(
                Message(
                    role="user",
                    content="工具调用次数已达到上限，请停止使用工具，并根据已经收集到的信息，对你的任务和发现进行总结，然后直接回复用户。",
                )
            )
            # 再执行最后一步
            async for resp in self.step():
                yield resp

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
            yield MessageChain(
                type="tool_call",
                chain=[
                    Json(
                        data={
                            "id": func_tool_id,
                            "name": func_tool_name,
                            "args": func_tool_args,
                            "ts": time.time(),
                        }
                    )
                ],
            )
            try:
                if not req.func_tool:
                    return
                func_tool = req.func_tool.get_func(func_tool_name)
                logger.info(f"使用工具：{func_tool_name}，参数：{func_tool_args}")

                if not func_tool:
                    logger.warning(f"未找到指定的工具: {func_tool_name}，将跳过。")
                    tool_call_result_blocks.append(
                        ToolCallMessageSegment(
                            role="tool",
                            tool_call_id=func_tool_id,
                            content=f"error: Tool {func_tool_name} not found.",
                        ),
                    )
                    continue

                valid_params = {}  # 参数过滤：只传递函数实际需要的参数

                # 获取实际的 handler 函数
                if func_tool.handler:
                    logger.debug(
                        f"工具 {func_tool_name} 期望的参数: {func_tool.parameters}",
                    )
                    if func_tool.parameters and func_tool.parameters.get("properties"):
                        expected_params = set(func_tool.parameters["properties"].keys())

                        valid_params = {
                            k: v
                            for k, v in func_tool_args.items()
                            if k in expected_params
                        }

                    # 记录被忽略的参数
                    ignored_params = set(func_tool_args.keys()) - set(
                        valid_params.keys(),
                    )
                    if ignored_params:
                        logger.warning(
                            f"工具 {func_tool_name} 忽略非期望参数: {ignored_params}",
                        )
                else:
                    # 如果没有 handler（如 MCP 工具），使用所有参数
                    valid_params = func_tool_args

                try:
                    await self.agent_hooks.on_tool_start(
                        self.run_context,
                        func_tool,
                        valid_params,
                    )
                except Exception as e:
                    logger.error(f"Error in on_tool_start hook: {e}", exc_info=True)

                executor = self.tool_executor.execute(
                    tool=func_tool,
                    run_context=self.run_context,
                    **valid_params,  # 只传递有效的参数
                )

                _final_resp: CallToolResult | None = None
                async for resp in executor:  # type: ignore
                    if isinstance(resp, CallToolResult):
                        res = resp
                        _final_resp = resp
                        if isinstance(res.content[0], TextContent):
                            tool_call_result_blocks.append(
                                ToolCallMessageSegment(
                                    role="tool",
                                    tool_call_id=func_tool_id,
                                    content=res.content[0].text,
                                ),
                            )
                        elif isinstance(res.content[0], ImageContent):
                            tool_call_result_blocks.append(
                                ToolCallMessageSegment(
                                    role="tool",
                                    tool_call_id=func_tool_id,
                                    content="The tool has successfully returned an image and sent directly to the user. You can describe it in your next response.",
                                ),
                            )
                            yield MessageChain(type="tool_direct_result").base64_image(
                                res.content[0].data,
                            )
                        elif isinstance(res.content[0], EmbeddedResource):
                            resource = res.content[0].resource
                            if isinstance(resource, TextResourceContents):
                                tool_call_result_blocks.append(
                                    ToolCallMessageSegment(
                                        role="tool",
                                        tool_call_id=func_tool_id,
                                        content=resource.text,
                                    ),
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
                                        content="The tool has successfully returned an image and sent directly to the user. You can describe it in your next response.",
                                    ),
                                )
                                yield MessageChain(
                                    type="tool_direct_result",
                                ).base64_image(resource.blob)
                            else:
                                tool_call_result_blocks.append(
                                    ToolCallMessageSegment(
                                        role="tool",
                                        tool_call_id=func_tool_id,
                                        content="The tool has returned a data type that is not supported.",
                                    ),
                                )

                    elif resp is None:
                        # Tool 直接请求发送消息给用户
                        # 这里我们将直接结束 Agent Loop
                        # 发送消息逻辑在 ToolExecutor 中处理了
                        logger.warning(
                            f"{func_tool_name} 没有返回值，或者已将结果直接发送给用户。"
                        )
                        self._transition_state(AgentState.DONE)
                        self.stats.end_time = time.time()
                        tool_call_result_blocks.append(
                            ToolCallMessageSegment(
                                role="tool",
                                tool_call_id=func_tool_id,
                                content="The tool has no return value, or has sent the result directly to the user.",
                            ),
                        )
                    else:
                        # 不应该出现其他类型
                        logger.warning(
                            f"Tool 返回了不支持的类型: {type(resp)}。",
                        )
                        tool_call_result_blocks.append(
                            ToolCallMessageSegment(
                                role="tool",
                                tool_call_id=func_tool_id,
                                content="*The tool has returned an unsupported type. Please tell the user to check the definition and implementation of this tool.*",
                            ),
                        )

                try:
                    await self.agent_hooks.on_tool_end(
                        self.run_context,
                        func_tool,
                        func_tool_args,
                        _final_resp,
                    )
                except Exception as e:
                    logger.error(f"Error in on_tool_end hook: {e}", exc_info=True)
            except Exception as e:
                logger.warning(traceback.format_exc())
                tool_call_result_blocks.append(
                    ToolCallMessageSegment(
                        role="tool",
                        tool_call_id=func_tool_id,
                        content=f"error: {e!s}",
                    ),
                )

        # yield the last tool call result
        if tool_call_result_blocks:
            last_tcr_content = str(tool_call_result_blocks[-1].content)
            yield MessageChain(
                type="tool_call_result",
                chain=[
                    Json(
                        data={
                            "id": func_tool_id,
                            "ts": time.time(),
                            "result": last_tcr_content,
                        }
                    )
                ],
            )

        # 处理函数调用响应
        if tool_call_result_blocks:
            yield tool_call_result_blocks

    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
