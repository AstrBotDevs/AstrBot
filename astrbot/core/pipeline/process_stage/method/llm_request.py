"""
本地 Agent 模式的 LLM 调用 Stage
"""

import asyncio
import copy
import json
import traceback
from typing import AsyncGenerator, Union
from astrbot.core import logger
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
)
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet, FunctionTool
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.star.session_llm_manager import SessionServiceManager
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.metrics import Metric
from ...context import PipelineContext, call_event_hook, call_handler
from ..stage import Stage
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.star_handler import star_map
from astrbot.core.astr_agent_context import AstrAgentContext

try:
    import mcp
except (ModuleNotFoundError, ImportError):
    logger.warning("警告: 缺少依赖库 'mcp'，将无法使用 MCP 服务。")


AgentContextWrapper = ContextWrapper[AstrAgentContext]
AgentRunner = ToolLoopAgentRunner[AgentContextWrapper]


class FunctionToolExecutor(BaseFunctionToolExecutor[AstrAgentContext]):
    @classmethod
    async def execute(cls, tool, run_context, **tool_args):
        """执行函数调用。

        Args:
            event (AstrMessageEvent): 事件对象, 当 origin 为 local 时必须提供。
            **kwargs: 函数调用的参数。

        Returns:
            AsyncGenerator[None | mcp.types.CallToolResult, None]
        """
        if isinstance(tool, HandoffTool):
            async for r in cls._execute_handoff(tool, run_context, **tool_args):
                yield r
            return

        if tool.origin == "local":
            async for r in cls._execute_local(tool, run_context, **tool_args):
                yield r
            return

        elif tool.origin == "mcp":
            async for r in cls._execute_mcp(tool, run_context, **tool_args):
                yield r
            return

        raise Exception(f"Unknown function origin: {tool.origin}")

    @classmethod
    async def _execute_handoff(
        cls,
        tool: HandoffTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        input_ = tool_args.get("input", "agent")
        agent_runner = AgentRunner()

        # make toolset for the agent
        tools = tool.agent.tools
        if tools:
            toolset = ToolSet()
            for t in tools:
                if isinstance(t, str):
                    _t = llm_tools.get_func(t)
                    if _t:
                        toolset.add_tool(_t)
                elif isinstance(t, FunctionTool):
                    toolset.add_tool(t)
        else:
            toolset = None

        request = ProviderRequest(
            prompt=input_,
            system_prompt=tool.description,
            image_urls=[],  # 暂时不传递原始 agent 的上下文
            contexts=[],  # 暂时不传递原始 agent 的上下文
            func_tool=toolset,
        )
        astr_agent_ctx = AstrAgentContext(
            provider=run_context.context.provider,
            first_provider_request=run_context.context.first_provider_request,
            curr_provider_request=request,
            streaming=run_context.context.streaming,
        )

        logger.debug(f"正在将任务委托给 Agent: {tool.agent.name}, input: {input_}")
        await run_context.event.send(
            MessageChain().message("✨ 正在将任务委托给 Agent: " + tool.agent.name)
        )

        await agent_runner.reset(
            provider=run_context.context.provider,
            request=request,
            run_context=AgentContextWrapper(
                context=astr_agent_ctx, event=run_context.event
            ),
            tool_executor=FunctionToolExecutor(),
            agent_hooks=tool.agent.run_hooks or BaseAgentRunHooks[AstrAgentContext](),
            streaming=run_context.context.streaming,
        )

        async for _ in run_agent(agent_runner, 15, True):
            pass

        if agent_runner.done():
            llm_response = agent_runner.get_final_llm_resp()
            logger.debug(
                f"Agent  {tool.agent.name} 任务完成, response: {llm_response.completion_text}"
            )

            result = (
                f"Agent {tool.agent.name} respond with: {llm_response.completion_text}\n\n"
                "Note: If the result is error or need user provide more information, please provide more information to the agent(you can ask user for more information first)."
            )

            text_content = mcp.types.TextContent(
                type="text",
                text=result,
            )
            yield mcp.types.CallToolResult(content=[text_content])
        else:
            yield mcp.types.TextContent(
                type="text",
                text=f"error when deligate task to {tool.agent.name}",
            )
            yield mcp.types.CallToolResult(content=[text_content])
        return

    @classmethod
    async def _execute_local(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        if not run_context.event:
            raise ValueError("Event must be provided for local function tools.")

        # 检查 tool 下有没有 run 方法
        if not tool.handler and not hasattr(tool, "run"):
            raise ValueError("Tool must have a valid handler or 'run' method.")
        awaitable = tool.handler or getattr(tool, "run")

        wrapper = call_handler(
            event=run_context.event,
            handler=awaitable,
            **tool_args,
        )
        async for resp in wrapper:
            if resp is not None:
                if isinstance(resp, mcp.types.CallToolResult):
                    yield resp
                else:
                    text_content = mcp.types.TextContent(
                        type="text",
                        text=str(resp),
                    )
                    yield mcp.types.CallToolResult(content=[text_content])
            else:
                # NOTE: Tool 在这里直接请求发送消息给用户
                # TODO: 是否需要判断 event.get_result() 是否为空?
                # 如果为空,则说明没有发送消息给用户,并且返回值为空,将返回一个特殊的 TextContent,其内容如"工具没有返回内容"
                yield None

    @classmethod
    async def _execute_mcp(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        if not tool.mcp_client:
            raise ValueError("MCP client is not available for MCP function tools.")
        res = await tool.mcp_client.session.call_tool(
            name=tool.name,
            arguments=tool_args,
        )
        if not res:
            return
        yield res


class MainAgentHooks(BaseAgentRunHooks[AgentContextWrapper]):
    async def on_agent_done(self, run_context, llm_response):
        # 执行事件钩子
        await call_event_hook(
            run_context.event, EventType.OnLLMResponseEvent, llm_response
        )


MAIN_AGENT_HOOKS = MainAgentHooks()


async def run_agent(
    agent_runner: AgentRunner, max_step: int = 30, show_tool_use: bool = True
) -> AsyncGenerator[MessageChain, None]:
    step_idx = 0
    astr_event = agent_runner.run_context.event
    while step_idx < max_step:
        step_idx += 1
        try:
            async for resp in agent_runner.step():
                if astr_event.is_stopped():
                    return
                if resp.type == "tool_call_result":
                    msg_chain = resp.data["chain"]
                    if msg_chain.type == "tool_direct_result":
                        # tool_direct_result 用于标记 llm tool 需要直接发送给用户的内容
                        resp.data["chain"].type = "tool_call_result"
                        await astr_event.send(resp.data["chain"])
                        continue
                    # 对于其他情况，暂时先不处理
                    continue
                elif resp.type == "tool_call":
                    if agent_runner.streaming:
                        # 用来标记流式响应需要分节
                        yield MessageChain(chain=[], type="break")
                    if show_tool_use or astr_event.get_platform_name() == "webchat":
                        resp.data["chain"].type = "tool_call"
                        await astr_event.send(resp.data["chain"])
                    continue

                if not agent_runner.streaming:
                    content_typ = (
                        ResultContentType.LLM_RESULT
                        if resp.type == "llm_result"
                        else ResultContentType.GENERAL_RESULT
                    )
                    astr_event.set_result(
                        MessageEventResult(
                            chain=resp.data["chain"].chain,
                            result_content_type=content_typ,
                        )
                    )
                    yield
                    astr_event.clear_result()
                else:
                    if resp.type == "streaming_delta":
                        yield resp.data["chain"]  # MessageChain
            if agent_runner.done():
                break

        except Exception as e:
            logger.error(traceback.format_exc())
            astr_event.set_result(
                MessageEventResult().message(
                    f"AstrBot 请求失败。\n错误类型: {type(e).__name__}\n错误信息: {str(e)}\n\n请在控制台查看和分享错误详情。\n"
                )
            )
            return
        asyncio.create_task(
            Metric.upload(
                llm_tick=1,
                model_name=agent_runner.provider.get_model(),
                provider_type=agent_runner.provider.meta().type,
            )
        )


class LLMRequestSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        conf = ctx.astrbot_config
        settings = conf["provider_settings"]
        self.bot_wake_prefixs: list[str] = conf["wake_prefix"]  # list
        self.provider_wake_prefix: str = settings["wake_prefix"]  # str
        self.max_context_length = settings["max_context_length"]  # int
        self.dequeue_context_length: int = min(
            max(1, settings["dequeue_context_length"]),
            self.max_context_length - 1,
        )
        self.streaming_response: bool = settings["streaming_response"]
        self.max_step: int = settings.get("max_agent_step", 10)
        self.show_tool_use: bool = settings.get("show_tool_use_status", True)

        for bwp in self.bot_wake_prefixs:
            if self.provider_wake_prefix.startswith(bwp):
                logger.info(
                    f"识别 LLM 聊天额外唤醒前缀 {self.provider_wake_prefix} 以机器人唤醒前缀 {bwp} 开头，已自动去除。"
                )
                self.provider_wake_prefix = self.provider_wake_prefix[len(bwp) :]

        self.conv_manager = ctx.plugin_manager.context.conversation_manager

    def _select_provider(self, event: AstrMessageEvent) -> Provider | None:
        """选择使用的 LLM 提供商"""
        sel_provider = event.get_extra("selected_provider")
        _ctx = self.ctx.plugin_manager.context
        if sel_provider and isinstance(sel_provider, str):
            provider = _ctx.get_provider_by_id(sel_provider)
            if not provider:
                logger.error(f"未找到指定的提供商: {sel_provider}。")
            return provider

        return _ctx.get_using_provider(umo=event.unified_msg_origin)

    async def _get_session_conv(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        conv_mgr = self.conv_manager

        # 获取对话上下文
        cid = await conv_mgr.get_curr_conversation_id(umo)
        if not cid:
            cid = await conv_mgr.new_conversation(umo, event.get_platform_id())
        conversation = await conv_mgr.get_conversation(umo, cid)
        if not conversation:
            cid = await conv_mgr.new_conversation(umo, event.get_platform_id())
            conversation = await conv_mgr.get_conversation(umo, cid)
        return conversation

    async def process(
        self, event: AstrMessageEvent, _nested: bool = False
    ) -> Union[None, AsyncGenerator[None, None]]:
        req: ProviderRequest | None = None

        if not self.ctx.astrbot_config["provider_settings"]["enable"]:
            logger.debug("未启用 LLM 能力，跳过处理。")
            return

        # 检查会话级别的LLM启停状态
        if not SessionServiceManager.should_process_llm_request(event):
            logger.debug(f"会话 {event.unified_msg_origin} 禁用了 LLM，跳过处理。")
            return

        provider = self._select_provider(event)
        if provider is None:
            return

        if event.get_extra("provider_request"):
            req = event.get_extra("provider_request")
            assert isinstance(req, ProviderRequest), (
                "provider_request 必须是 ProviderRequest 类型。"
            )

            if req.conversation:
                req.contexts = json.loads(req.conversation.history)

        else:
            req = ProviderRequest(prompt="", image_urls=[])
            if sel_model := event.get_extra("selected_model"):
                req.model = sel_model
            if self.provider_wake_prefix:
                if not event.message_str.startswith(self.provider_wake_prefix):
                    return
            req.prompt = event.message_str[len(self.provider_wake_prefix) :]
            # func_tool selection 现在已经转移到 packages/astrbot 插件中进行选择。
            # req.func_tool = self.ctx.plugin_manager.context.get_llm_tool_manager()
            for comp in event.message_obj.message:
                if isinstance(comp, Image):
                    image_path = await comp.convert_to_file_path()
                    req.image_urls.append(image_path)

            conversation = await self._get_session_conv(event)
            req.conversation = conversation
            req.contexts = json.loads(conversation.history)

            event.set_extra("provider_request", req)

        if not req.prompt and not req.image_urls:
            return

        # 执行请求 LLM 前事件钩子。
        if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
            return

        if isinstance(req.contexts, str):
            req.contexts = json.loads(req.contexts)

        # max context length
        if (
            self.max_context_length != -1  # -1 为不限制
            and len(req.contexts) // 2 > self.max_context_length
        ):
            logger.debug("上下文长度超过限制，将截断。")
            req.contexts = req.contexts[
                -(self.max_context_length - self.dequeue_context_length + 1) * 2 :
            ]
            # 找到第一个role 为 user 的索引，确保上下文格式正确
            index = next(
                (
                    i
                    for i, item in enumerate(req.contexts)
                    if item.get("role") == "user"
                ),
                None,
            )
            if index is not None and index > 0:
                req.contexts = req.contexts[index:]

        # session_id
        if not req.session_id:
            req.session_id = event.unified_msg_origin

        # fix messages
        req.contexts = self.fix_messages(req.contexts)

        # check provider modalities
        # 如果提供商不支持图像/工具使用，但请求中包含图像/工具列表，则清空。图片转述等的检测和调用发生在这之前，因此这里可以这样处理。
        if req.image_urls:
            provider_cfg = provider.provider_config.get("modalities", ["image"])
            if "image" not in provider_cfg:
                logger.debug(f"用户设置提供商 {provider} 不支持图像，清空图像列表。")
                req.image_urls = []
        if req.func_tool:
            provider_cfg = provider.provider_config.get("modalities", ["tool_use"])
            # 如果模型不支持工具使用，但请求中包含工具列表，则清空。
            if "tool_use" not in provider_cfg:
                logger.debug(f"用户设置提供商 {provider} 不支持工具使用，清空工具列表。")
                req.func_tool = None
        # 插件可用性设置
        if event.plugins_name is not None and req.func_tool:
            new_tool_set = ToolSet()
            for tool in req.func_tool.tools:
                plugin = star_map.get(tool.handler_module_path)
                if not plugin:
                    continue
                if plugin.name in event.plugins_name or plugin.reserved:
                    new_tool_set.add_tool(tool)
            req.func_tool = new_tool_set

        # run agent
        agent_runner = AgentRunner()
        logger.debug(
            f"handle provider[id: {provider.provider_config['id']}] request: {req}"
        )
        astr_agent_ctx = AstrAgentContext(
            provider=provider,
            first_provider_request=req,
            curr_provider_request=req,
            streaming=self.streaming_response,
        )
        await agent_runner.reset(
            provider=provider,
            request=req,
            run_context=AgentContextWrapper(context=astr_agent_ctx, event=event),
            tool_executor=FunctionToolExecutor(),
            agent_hooks=MAIN_AGENT_HOOKS,
            streaming=self.streaming_response,
        )

        if self.streaming_response:
            # 流式响应
            event.set_result(
                MessageEventResult()
                .set_result_content_type(ResultContentType.STREAMING_RESULT)
                .set_async_stream(
                    run_agent(agent_runner, self.max_step, self.show_tool_use)
                )
            )
            yield
            if agent_runner.done():
                if final_llm_resp := agent_runner.get_final_llm_resp():
                    if final_llm_resp.completion_text:
                        chain = (
                            MessageChain().message(final_llm_resp.completion_text).chain
                        )
                    else:
                        chain = final_llm_resp.result_chain.chain
                    event.set_result(
                        MessageEventResult(
                            chain=chain,
                            result_content_type=ResultContentType.STREAMING_FINISH,
                        )
                    )
        else:
            async for _ in run_agent(agent_runner, self.max_step, self.show_tool_use):
                yield

        await self._save_to_history(event, req, agent_runner.get_final_llm_resp())

        # 异步处理 WebChat 特殊情况
        if event.get_platform_name() == "webchat":
            asyncio.create_task(self._handle_webchat(event, req, provider))

    async def _handle_webchat(
        self, event: AstrMessageEvent, req: ProviderRequest, prov: Provider
    ):
        """处理 WebChat 平台的特殊情况，包括第一次 LLM 对话时总结对话内容生成 title"""
        conversation = await self.conv_manager.get_conversation(
            event.unified_msg_origin, req.conversation.cid
        )
        if conversation and not req.conversation.title:
            messages = json.loads(conversation.history)
            latest_pair = messages[-2:]
            if not latest_pair:
                return
            cleaned_text = "User: " + latest_pair[0].get("content", "").strip()
            logger.debug(f"WebChat 对话标题生成请求，清理后的文本: {cleaned_text}")
            llm_resp = await prov.text_chat(
                system_prompt="You are expert in summarizing user's query.",
                prompt=(
                    f"Please summarize the following query of user:\n"
                    f"{cleaned_text}\n"
                    "Only output the summary within 10 words, DO NOT INCLUDE any other text."
                    "You must use the same language as the user."
                    "If you think the dialog is too short to summarize, only output a special mark: `<None>`"
                ),
            )
            if llm_resp and llm_resp.completion_text:
                logger.debug(
                    f"WebChat 对话标题生成响应: {llm_resp.completion_text.strip()}"
                )
                title = llm_resp.completion_text.strip()
                if not title or "<None>" in title:
                    return
                await self.conv_manager.update_conversation_title(
                    unified_msg_origin=event.unified_msg_origin,
                    title=title,
                    conversation_id=req.conversation.cid,
                )

    async def _save_to_history(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        llm_response: LLMResponse | None,
    ):
        if (
            not req
            or not req.conversation
            or not llm_response
            or llm_response.role != "assistant"
        ):
            return

        if not llm_response.completion_text and not req.tool_calls_result:
            logger.debug("LLM 响应为空，不保存记录。")
            return

        # 历史上下文
        messages = copy.deepcopy(req.contexts)
        # 这一轮对话请求的用户输入
        messages.append(await req.assemble_context())
        # 这一轮对话的 LLM 响应
        if req.tool_calls_result:
            if not isinstance(req.tool_calls_result, list):
                messages.extend(req.tool_calls_result.to_openai_messages())
            elif isinstance(req.tool_calls_result, list):
                for tcr in req.tool_calls_result:
                    messages.extend(tcr.to_openai_messages())
        messages.append({"role": "assistant", "content": llm_response.completion_text})
        messages = list(filter(lambda item: "_no_save" not in item, messages))
        await self.conv_manager.update_conversation(
            event.unified_msg_origin, req.conversation.cid, history=messages
        )

    def fix_messages(self, messages: list[dict]) -> list[dict]:
        """验证并且修复上下文"""
        fixed_messages = []
        for message in messages:
            if message.get("role") == "tool":
                # tool block 前面必须要有 user 和 assistant block
                if len(fixed_messages) < 2:
                    # 这种情况可能是上下文被截断导致的
                    # 我们直接将之前的上下文都清空
                    fixed_messages = []
                else:
                    fixed_messages.append(message)
            else:
                fixed_messages.append(message)
        return fixed_messages
