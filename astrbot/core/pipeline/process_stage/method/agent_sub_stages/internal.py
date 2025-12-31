"""本地 Agent 模式的 LLM 调用 Stage"""

import asyncio
import copy
import json
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.agent.message import Message
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.conversation_mgr import Conversation
from astrbot.core.message.components import File, Image, Reply
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
from astrbot.core.star.star_handler import EventType, star_map
from astrbot.core.utils.file_extract import extract_file_moonshotai
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.session_lock import session_lock_manager

from .....astr_agent_context import AgentContextWrapper
from .....astr_agent_hooks import MAIN_AGENT_HOOKS
from .....astr_agent_run_util import AgentRunner, run_agent
from .....astr_agent_tool_exec import FunctionToolExecutor
from ....context import PipelineContext, call_event_hook
from ...stage import Stage
from ...utils import KNOWLEDGE_BASE_QUERY_TOOL, retrieve_knowledge_base


class InternalAgentSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        conf = ctx.astrbot_config
        settings = conf["provider_settings"]
        self.max_context_length = settings["max_context_length"]  # int
        self.dequeue_context_length: int = min(
            max(1, settings["dequeue_context_length"]),
            self.max_context_length - 1,
        )
        self.streaming_response: bool = settings["streaming_response"]
        self.unsupported_streaming_strategy: str = settings[
            "unsupported_streaming_strategy"
        ]
        self.max_step: int = settings.get("max_agent_step", 30)
        self.tool_call_timeout: int = settings.get("tool_call_timeout", 60)
        if isinstance(self.max_step, bool):  # workaround: #2622
            self.max_step = 30
        self.show_tool_use: bool = settings.get("show_tool_use_status", True)
        self.show_reasoning = settings.get("display_reasoning_text", False)
        self.kb_agentic_mode: bool = conf.get("kb_agentic_mode", False)

        file_extract_conf: dict = settings.get("file_extract", {})
        self.file_extract_enabled: bool = file_extract_conf.get("enable", False)
        self.file_extract_prov: str = file_extract_conf.get("provider", "moonshotai")
        self.file_extract_msh_api_key: str = file_extract_conf.get(
            "moonshotai_api_key", ""
        )

        self.conv_manager = ctx.plugin_manager.context.conversation_manager

    def _select_provider(self, event: AstrMessageEvent):
        """选择使用的 LLM 提供商"""
        sel_provider = event.get_extra("selected_provider")
        _ctx = self.ctx.plugin_manager.context
        if sel_provider and isinstance(sel_provider, str):
            provider = _ctx.get_provider_by_id(sel_provider)
            if not provider:
                logger.error(f"未找到指定的提供商: {sel_provider}。")
            return provider

        return _ctx.get_using_provider(umo=event.unified_msg_origin)

    async def _get_session_conv(self, event: AstrMessageEvent) -> Conversation:
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
        if not conversation:
            raise RuntimeError("无法创建新的对话。")
        return conversation

    async def _apply_kb(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ):
        """Apply knowledge base context to the provider request"""
        if not self.kb_agentic_mode:
            if req.prompt is None:
                return
            try:
                kb_result = await retrieve_knowledge_base(
                    query=req.prompt,
                    umo=event.unified_msg_origin,
                    context=self.ctx.plugin_manager.context,
                )
                if not kb_result:
                    return
                if req.system_prompt is not None:
                    req.system_prompt += (
                        f"\n\n[Related Knowledge Base Results]:\n{kb_result}"
                    )
            except Exception as e:
                logger.error(f"Error occurred while retrieving knowledge base: {e}")
        else:
            if req.func_tool is None:
                req.func_tool = ToolSet()
            req.func_tool.add_tool(KNOWLEDGE_BASE_QUERY_TOOL)

    async def _apply_file_extract(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ):
        """Apply file extract to the provider request"""
        file_paths = []
        file_names = []
        for comp in event.message_obj.message:
            if isinstance(comp, File):
                file_paths.append(await comp.get_file())
                file_names.append(comp.name)
            elif isinstance(comp, Reply) and comp.chain:
                for reply_comp in comp.chain:
                    if isinstance(reply_comp, File):
                        file_paths.append(await reply_comp.get_file())
                        file_names.append(reply_comp.name)
        if not file_paths:
            return
        if not req.prompt:
            req.prompt = "总结一下文件里面讲了什么？"
        if self.file_extract_prov == "moonshotai":
            if not self.file_extract_msh_api_key:
                logger.error("Moonshot AI API key for file extract is not set")
                return
            file_contents = await asyncio.gather(
                *[
                    extract_file_moonshotai(file_path, self.file_extract_msh_api_key)
                    for file_path in file_paths
                ]
            )
        else:
            logger.error(f"Unsupported file extract provider: {self.file_extract_prov}")
            return

        # add file extract results to contexts
        for file_content, file_name in zip(file_contents, file_names):
            req.contexts.append(
                {
                    "role": "system",
                    "content": f"File Extract Results of user uploaded files:\n{file_content}\nFile Name: {file_name or 'Unknown'}",
                },
            )

    def _truncate_contexts(
        self,
        contexts: list[dict],
    ) -> list[dict]:
        """截断上下文列表，确保不超过最大长度"""
        if self.max_context_length == -1:
            return contexts

        if len(contexts) // 2 <= self.max_context_length:
            return contexts

        truncated_contexts = contexts[
            -(self.max_context_length - self.dequeue_context_length + 1) * 2 :
        ]
        # 找到第一个role 为 user 的索引，确保上下文格式正确
        index = next(
            (
                i
                for i, item in enumerate(truncated_contexts)
                if item.get("role") == "user"
            ),
            None,
        )
        if index is not None and index > 0:
            truncated_contexts = truncated_contexts[index:]

        return truncated_contexts

    def _modalities_fix(
        self,
        provider: Provider,
        req: ProviderRequest,
    ):
        """检查提供商的模态能力，清理请求中的不支持内容"""
        if req.image_urls:
            provider_cfg = provider.provider_config.get("modalities", ["image"])
            if "image" not in provider_cfg:
                logger.debug(f"用户设置提供商 {provider} 不支持图像，清空图像列表。")
                req.image_urls = []
        if req.func_tool:
            provider_cfg = provider.provider_config.get("modalities", ["tool_use"])
            # 如果模型不支持工具使用，但请求中包含工具列表，则清空。
            if "tool_use" not in provider_cfg:
                logger.debug(
                    f"用户设置提供商 {provider} 不支持工具使用，清空工具列表。",
                )
                req.func_tool = None

    def _plugin_tool_fix(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ):
        """根据事件中的插件设置，过滤请求中的工具列表"""
        if event.plugins_name is not None and req.func_tool:
            new_tool_set = ToolSet()
            for tool in req.func_tool.tools:
                mp = tool.handler_module_path
                if not mp:
                    continue
                plugin = star_map.get(mp)
                if not plugin:
                    continue
                if plugin.name in event.plugins_name or plugin.reserved:
                    new_tool_set.add_tool(tool)
            req.func_tool = new_tool_set

    async def _handle_webchat(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        prov: Provider,
    ):
        """处理 WebChat 平台的特殊情况，包括第一次 LLM 对话时总结对话内容生成 title"""
        if not req.conversation:
            return
        conversation = await self.conv_manager.get_conversation(
            event.unified_msg_origin,
            req.conversation.cid,
        )
        if conversation and not req.conversation.title:
            messages = json.loads(conversation.history)
            latest_pair = messages[-2:]
            if not latest_pair:
                return
            content = latest_pair[0].get("content", "")
            if isinstance(content, list):
                # 多模态
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "image":
                            text_parts.append("[图片]")
                    elif isinstance(item, str):
                        text_parts.append(item)
                cleaned_text = "User: " + " ".join(text_parts).strip()
            elif isinstance(content, str):
                cleaned_text = "User: " + content.strip()
            else:
                return
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
        all_messages: list[Message],
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

        # using agent context messages to save to history
        message_to_save = []
        for message in all_messages:
            if message.role == "system":
                # we do not save system messages to history
                continue
            if message.role in ["assistant", "user"] and getattr(
                message, "_no_save", None
            ):
                # we do not save user and assistant messages that are marked as _no_save
                continue
            message_to_save.append(message.model_dump())

        await self.conv_manager.update_conversation(
            event.unified_msg_origin,
            req.conversation.cid,
            history=message_to_save,
        )

    def _fix_messages(self, messages: list[dict]) -> list[dict]:
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

    async def process(
        self, event: AstrMessageEvent, provider_wake_prefix: str
    ) -> AsyncGenerator[None, None]:
        req: ProviderRequest | None = None

        try:
            provider = self._select_provider(event)
            if provider is None:
                return
            if not isinstance(provider, Provider):
                logger.error(
                    f"选择的提供商类型无效({type(provider)})，跳过 LLM 请求处理。"
                )
                return

            streaming_response = self.streaming_response
            if (enable_streaming := event.get_extra("enable_streaming")) is not None:
                streaming_response = bool(enable_streaming)

            logger.debug("ready to request llm provider")
            async with session_lock_manager.acquire_lock(event.unified_msg_origin):
                logger.debug("acquired session lock for llm request")
                if event.get_extra("provider_request"):
                    req = event.get_extra("provider_request")
                    assert isinstance(req, ProviderRequest), (
                        "provider_request 必须是 ProviderRequest 类型。"
                    )

                    if req.conversation:
                        req.contexts = json.loads(req.conversation.history)

                else:
                    req = ProviderRequest()
                    req.prompt = ""
                    req.image_urls = []
                    if sel_model := event.get_extra("selected_model"):
                        req.model = sel_model
                    if provider_wake_prefix and not event.message_str.startswith(
                        provider_wake_prefix
                    ):
                        return

                    req.prompt = event.message_str[len(provider_wake_prefix) :]
                    # func_tool selection 现在已经转移到 astrbot/builtin_stars/astrbot 插件中进行选择。
                    # req.func_tool = self.ctx.plugin_manager.context.get_llm_tool_manager()
                    for comp in event.message_obj.message:
                        if isinstance(comp, Image):
                            image_path = await comp.convert_to_file_path()
                            req.image_urls.append(image_path)

                    conversation = await self._get_session_conv(event)
                    req.conversation = conversation
                    req.contexts = json.loads(conversation.history)

                    event.set_extra("provider_request", req)

                # fix contexts json str
                if isinstance(req.contexts, str):
                    req.contexts = json.loads(req.contexts)

                # apply file extract
                if self.file_extract_enabled:
                    try:
                        await self._apply_file_extract(event, req)
                    except Exception as e:
                        logger.error(f"Error occurred while applying file extract: {e}")

                if not req.prompt and not req.image_urls:
                    return

                # call event hook
                if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
                    return

                # apply knowledge base feature
                await self._apply_kb(event, req)

                # truncate contexts to fit max length
                if req.contexts:
                    req.contexts = self._truncate_contexts(req.contexts)
                    self._fix_messages(req.contexts)

                # session_id
                if not req.session_id:
                    req.session_id = event.unified_msg_origin

                # check provider modalities, if provider does not support image/tool_use, clear them in request.
                self._modalities_fix(provider, req)

                # filter tools, only keep tools from this pipeline's selected plugins
                self._plugin_tool_fix(event, req)

                stream_to_general = (
                    self.unsupported_streaming_strategy == "turn_off"
                    and not event.platform_meta.support_streaming_message
                )
                # 备份 req.contexts
                backup_contexts = copy.deepcopy(req.contexts)

                # run agent
                agent_runner = AgentRunner()
                logger.debug(
                    f"handle provider[id: {provider.provider_config['id']}] request: {req}",
                )
                astr_agent_ctx = AstrAgentContext(
                    context=self.ctx.plugin_manager.context,
                    event=event,
                )
                await agent_runner.reset(
                    provider=provider,
                    request=req,
                    run_context=AgentContextWrapper(
                        context=astr_agent_ctx,
                        tool_call_timeout=self.tool_call_timeout,
                    ),
                    tool_executor=FunctionToolExecutor(),
                    agent_hooks=MAIN_AGENT_HOOKS,
                    streaming=streaming_response,
                )

                if streaming_response and not stream_to_general:
                    # 流式响应
                    event.set_result(
                        MessageEventResult()
                        .set_result_content_type(ResultContentType.STREAMING_RESULT)
                        .set_async_stream(
                            run_agent(
                                agent_runner,
                                self.max_step,
                                self.show_tool_use,
                                show_reasoning=self.show_reasoning,
                            ),
                        ),
                    )
                    yield
                    if agent_runner.done():
                        if final_llm_resp := agent_runner.get_final_llm_resp():
                            if final_llm_resp.completion_text:
                                chain = (
                                    MessageChain()
                                    .message(final_llm_resp.completion_text)
                                    .chain
                                )
                            elif final_llm_resp.result_chain:
                                chain = final_llm_resp.result_chain.chain
                            else:
                                chain = MessageChain().chain
                            event.set_result(
                                MessageEventResult(
                                    chain=chain,
                                    result_content_type=ResultContentType.STREAMING_FINISH,
                                ),
                            )
                else:
                    async for _ in run_agent(
                        agent_runner,
                        self.max_step,
                        self.show_tool_use,
                        stream_to_general,
                        show_reasoning=self.show_reasoning,
                    ):
                        yield

                # 恢复备份的 contexts
                req.contexts = backup_contexts

                await self._save_to_history(
                    event,
                    req,
                    agent_runner.get_final_llm_resp(),
                    agent_runner.run_context.messages,
                )

            # 异步处理 WebChat 特殊情况
            if event.get_platform_name() == "webchat":
                asyncio.create_task(self._handle_webchat(event, req, provider))

            asyncio.create_task(
                Metric.upload(
                    llm_tick=1,
                    model_name=agent_runner.provider.get_model(),
                    provider_type=agent_runner.provider.meta().type,
                ),
            )

        except Exception as e:
            logger.error(f"Error occurred while processing agent: {e}")
            await event.send(
                MessageChain().message(
                    f"Error occurred while processing agent request: {e}"
                )
            )
