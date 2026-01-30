"""本地 Agent 模式的 LLM 调用 Stage"""

import asyncio
import json
import os
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.agent.message import Message, TextPart
from astrbot.core.agent.response import AgentStats
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
from astrbot.core.utils.llm_metadata import LLM_METADATAS
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.session_lock import session_lock_manager

from .....astr_agent_context import AgentContextWrapper
from .....astr_agent_hooks import MAIN_AGENT_HOOKS
from .....astr_agent_run_util import AgentRunner, run_agent, run_live_agent
from .....astr_agent_tool_exec import FunctionToolExecutor
from ....context import PipelineContext, call_event_hook
from ...stage import Stage
from ...utils import (
    CHATUI_EXTRA_PROMPT,
    EXECUTE_SHELL_TOOL,
    FILE_DOWNLOAD_TOOL,
    FILE_UPLOAD_TOOL,
    KNOWLEDGE_BASE_QUERY_TOOL,
    LIVE_MODE_SYSTEM_PROMPT,
    LLM_SAFETY_MODE_SYSTEM_PROMPT,
    PYTHON_TOOL,
    SANDBOX_MODE_PROMPT,
    TOOL_CALL_PROMPT,
    TOOL_CALL_PROMPT_SKILLS_LIKE_MODE,
    decoded_blocked,
    retrieve_knowledge_base,
)


class InternalAgentSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        conf = ctx.astrbot_config
        settings = conf["provider_settings"]
        self.streaming_response: bool = settings["streaming_response"]
        self.unsupported_streaming_strategy: str = settings[
            "unsupported_streaming_strategy"
        ]
        self.max_step: int = settings.get("max_agent_step", 30)
        self.tool_call_timeout: int = settings.get("tool_call_timeout", 60)
        self.tool_schema_mode: str = settings.get("tool_schema_mode", "full")
        if self.tool_schema_mode not in ("skills_like", "full"):
            logger.warning(
                "Unsupported tool_schema_mode: %s, fallback to skills_like",
                self.tool_schema_mode,
            )
            self.tool_schema_mode = "full"
        if isinstance(self.max_step, bool):  # workaround: #2622
            self.max_step = 30
        self.show_tool_use: bool = settings.get("show_tool_use_status", True)
        self.show_reasoning = settings.get("display_reasoning_text", False)
        self.sanitize_context_by_modalities: bool = settings.get(
            "sanitize_context_by_modalities",
            False,
        )
        self.kb_agentic_mode: bool = conf.get("kb_agentic_mode", False)

        file_extract_conf: dict = settings.get("file_extract", {})
        self.file_extract_enabled: bool = file_extract_conf.get("enable", False)
        self.file_extract_prov: str = file_extract_conf.get("provider", "moonshotai")
        self.file_extract_msh_api_key: str = file_extract_conf.get(
            "moonshotai_api_key", ""
        )

        # 上下文管理相关
        self.context_limit_reached_strategy: str = settings.get(
            "context_limit_reached_strategy", "truncate_by_turns"
        )
        self.llm_compress_instruction: str = settings.get(
            "llm_compress_instruction", ""
        )
        self.llm_compress_keep_recent: int = settings.get("llm_compress_keep_recent", 4)
        self.llm_compress_provider_id: str = settings.get(
            "llm_compress_provider_id", ""
        )
        self.max_context_length = settings["max_context_length"]  # int
        self.dequeue_context_length: int = min(
            max(1, settings["dequeue_context_length"]),
            self.max_context_length - 1,
        )
        if self.dequeue_context_length <= 0:
            self.dequeue_context_length = 1

        self.llm_safety_mode = settings.get("llm_safety_mode", True)
        self.safety_mode_strategy = settings.get(
            "safety_mode_strategy", "system_prompt"
        )

        self.sandbox_cfg = settings.get("sandbox", {})

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
        try:
            prov = _ctx.get_using_provider(umo=event.unified_msg_origin)
        except ValueError as e:
            logger.error(f"Error occurred while selecting provider: {e}")
            return None
        return prov

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

    def _modalities_fix(
        self,
        provider: Provider,
        req: ProviderRequest,
    ):
        """检查提供商的模态能力，清理请求中的不支持内容"""
        if req.image_urls:
            provider_cfg = provider.provider_config.get("modalities", ["image"])
            if "image" not in provider_cfg:
                logger.debug(
                    f"用户设置提供商 {provider} 不支持图像，将图像替换为占位符。"
                )
                # 为每个图片添加占位符到 prompt
                image_count = len(req.image_urls)
                placeholder = " ".join(["[图片]"] * image_count)
                if req.prompt:
                    req.prompt = f"{placeholder} {req.prompt}"
                else:
                    req.prompt = placeholder
                req.image_urls = []
        if req.func_tool:
            provider_cfg = provider.provider_config.get("modalities", ["tool_use"])
            # 如果模型不支持工具使用，但请求中包含工具列表，则清空。
            if "tool_use" not in provider_cfg:
                logger.debug(
                    f"用户设置提供商 {provider} 不支持工具使用，清空工具列表。",
                )
                req.func_tool = None

    def _sanitize_context_by_modalities(
        self,
        provider: Provider,
        req: ProviderRequest,
    ) -> None:
        """Sanitize `req.contexts` (including history) by current provider modalities."""
        if not self.sanitize_context_by_modalities:
            return

        if not isinstance(req.contexts, list) or not req.contexts:
            return

        modalities = provider.provider_config.get("modalities", None)
        # if modalities is not configured, do not sanitize.
        if not modalities or not isinstance(modalities, list):
            return

        supports_image = bool("image" in modalities)
        supports_tool_use = bool("tool_use" in modalities)

        if supports_image and supports_tool_use:
            return

        sanitized_contexts: list[dict] = []
        removed_image_blocks = 0
        removed_tool_messages = 0
        removed_tool_calls = 0

        for msg in req.contexts:
            if not isinstance(msg, dict):
                continue

            role = msg.get("role")
            if not role:
                continue

            new_msg: dict = msg

            # tool_use sanitize
            if not supports_tool_use:
                if role == "tool":
                    # tool response block
                    removed_tool_messages += 1
                    continue
                if role == "assistant" and "tool_calls" in new_msg:
                    # assistant message with tool calls
                    if "tool_calls" in new_msg:
                        removed_tool_calls += 1
                    new_msg.pop("tool_calls", None)
                    new_msg.pop("tool_call_id", None)

            # image sanitize
            if not supports_image:
                content = new_msg.get("content")
                if isinstance(content, list):
                    filtered_parts: list = []
                    removed_any_image = False
                    for part in content:
                        if isinstance(part, dict):
                            part_type = str(part.get("type", "")).lower()
                            if part_type in {"image_url", "image"}:
                                removed_any_image = True
                                removed_image_blocks += 1
                                continue
                        filtered_parts.append(part)

                    if removed_any_image:
                        new_msg["content"] = filtered_parts

            # drop empty assistant messages (e.g. only tool_calls without content)
            if role == "assistant":
                content = new_msg.get("content")
                has_tool_calls = bool(new_msg.get("tool_calls"))
                if not has_tool_calls:
                    if not content:
                        continue
                    if isinstance(content, str) and not content.strip():
                        continue

            sanitized_contexts.append(new_msg)

        if removed_image_blocks or removed_tool_messages or removed_tool_calls:
            logger.debug(
                "sanitize_context_by_modalities applied: "
                f"removed_image_blocks={removed_image_blocks}, "
                f"removed_tool_messages={removed_tool_messages}, "
                f"removed_tool_calls={removed_tool_calls}"
            )

        req.contexts = sanitized_contexts

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
        from astrbot.core import db_helper

        chatui_session_id = event.session_id.split("!")[-1]
        user_prompt = req.prompt

        session = await db_helper.get_platform_session_by_id(chatui_session_id)

        if (
            not user_prompt
            or not chatui_session_id
            or not session
            or session.display_name
        ):
            return

        llm_resp = await prov.text_chat(
            system_prompt=(
                "You are a conversation title generator. "
                "Generate a concise title in the same language as the user’s input, "
                "no more than 10 words, capturing only the core topic."
                "If the input is a greeting, small talk, or has no clear topic, "
                "(e.g., “hi”, “hello”, “haha”), return <None>. "
                "Output only the title itself or <None>, with no explanations."
            ),
            prompt=(
                f"Generate a concise title for the following user query:\n{user_prompt}"
            ),
        )
        if llm_resp and llm_resp.completion_text:
            title = llm_resp.completion_text.strip()
            if not title or "<None>" in title:
                return
            logger.info(
                f"Generated chatui title for session {chatui_session_id}: {title}"
            )
            await db_helper.update_platform_session(
                session_id=chatui_session_id,
                display_name=title,
            )

    async def _save_to_history(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        llm_response: LLMResponse | None,
        all_messages: list[Message],
        runner_stats: AgentStats | None,
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
        skipped_initial_system = False
        for message in all_messages:
            if message.role == "system" and not skipped_initial_system:
                skipped_initial_system = True
                continue  # skip first system message
            if message.role in ["assistant", "user"] and getattr(
                message, "_no_save", None
            ):
                # we do not save user and assistant messages that are marked as _no_save
                continue
            message_to_save.append(message.model_dump())

        # get token usage from agent runner stats
        token_usage = None
        if runner_stats:
            token_usage = runner_stats.token_usage.total

        await self.conv_manager.update_conversation(
            event.unified_msg_origin,
            req.conversation.cid,
            history=message_to_save,
            token_usage=token_usage,
        )

    def _get_compress_provider(self) -> Provider | None:
        if not self.llm_compress_provider_id:
            return None
        if self.context_limit_reached_strategy != "llm_compress":
            return None
        provider = self.ctx.plugin_manager.context.get_provider_by_id(
            self.llm_compress_provider_id,
        )
        if provider is None:
            logger.warning(
                f"未找到指定的上下文压缩模型 {self.llm_compress_provider_id}，将跳过压缩。",
            )
            return None
        if not isinstance(provider, Provider):
            logger.warning(
                f"指定的上下文压缩模型 {self.llm_compress_provider_id} 不是对话模型，将跳过压缩。"
            )
            return None
        return provider

    def _apply_llm_safety_mode(self, req: ProviderRequest) -> None:
        """Apply LLM safety mode to the provider request."""
        if self.safety_mode_strategy == "system_prompt":
            req.system_prompt = (
                f"{LLM_SAFETY_MODE_SYSTEM_PROMPT}\n\n{req.system_prompt or ''}"
            )
        else:
            logger.warning(
                f"Unsupported llm_safety_mode strategy: {self.safety_mode_strategy}.",
            )

    def _apply_sandbox_tools(self, req: ProviderRequest, session_id: str) -> None:
        """Add sandbox tools to the provider request."""
        if req.func_tool is None:
            req.func_tool = ToolSet()
        if self.sandbox_cfg.get("booter") == "shipyard":
            ep = self.sandbox_cfg.get("shipyard_endpoint", "")
            at = self.sandbox_cfg.get("shipyard_access_token", "")
            if not ep or not at:
                logger.error("Shipyard sandbox configuration is incomplete.")
                return
            os.environ["SHIPYARD_ENDPOINT"] = ep
            os.environ["SHIPYARD_ACCESS_TOKEN"] = at
        req.func_tool.add_tool(EXECUTE_SHELL_TOOL)
        req.func_tool.add_tool(PYTHON_TOOL)
        req.func_tool.add_tool(FILE_UPLOAD_TOOL)
        req.func_tool.add_tool(FILE_DOWNLOAD_TOOL)
        req.system_prompt += f"\n{SANDBOX_MODE_PROMPT}\n"

    async def process(
        self, event: AstrMessageEvent, provider_wake_prefix: str
    ) -> AsyncGenerator[None, None]:
        req: ProviderRequest | None = None

        try:
            provider = self._select_provider(event)
            if provider is None:
                logger.info("未找到任何对话模型（提供商），跳过 LLM 请求处理。")
                return
            if not isinstance(provider, Provider):
                logger.error(
                    f"选择的提供商类型无效({type(provider)})，跳过 LLM 请求处理。"
                )
                return

            streaming_response = self.streaming_response
            if (enable_streaming := event.get_extra("enable_streaming")) is not None:
                streaming_response = bool(enable_streaming)

            # 检查消息内容是否有效，避免空消息触发钩子
            has_provider_request = event.get_extra("provider_request") is not None
            has_valid_message = bool(event.message_str and event.message_str.strip())
            # 检查是否有图片或其他媒体内容
            has_media_content = any(
                isinstance(comp, Image | File) for comp in event.message_obj.message
            )

            if (
                not has_provider_request
                and not has_valid_message
                and not has_media_content
            ):
                logger.debug("skip llm request: empty message and no provider_request")
                return

            api_base = provider.provider_config.get("api_base", "")
            for host in decoded_blocked:
                if host in api_base:
                    logger.error(
                        f"Provider API base {api_base} is blocked due to security reasons. Please use another ai provider."
                    )
                    return

            logger.debug("ready to request llm provider")

            # 通知等待调用 LLM（在获取锁之前）
            await call_event_hook(event, EventType.OnWaitingLLMRequestEvent)

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

                            req.extra_user_content_parts.append(
                                TextPart(text=f"[Image Attachment: path {image_path}]")
                            )
                        elif isinstance(comp, File):
                            file_path = await comp.get_file()
                            file_name = comp.name or os.path.basename(file_path)
                            req.extra_user_content_parts.append(
                                TextPart(
                                    text=f"[File Attachment: name {file_name}, path {file_path}]"
                                )
                            )

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
                    if not event.get_group_id() and req.extra_user_content_parts:
                        req.prompt = "<attachment>"
                    else:
                        return

                # call event hook
                if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
                    return

                # apply knowledge base feature
                await self._apply_kb(event, req)

                # truncate contexts to fit max length
                # NOW moved to ContextManager inside ToolLoopAgentRunner
                # if req.contexts:
                #     req.contexts = self._truncate_contexts(req.contexts)
                #     self._fix_messages(req.contexts)

                # session_id
                if not req.session_id:
                    req.session_id = event.unified_msg_origin

                # check provider modalities, if provider does not support image/tool_use, clear them in request.
                self._modalities_fix(provider, req)

                # filter tools, only keep tools from this pipeline's selected plugins
                self._plugin_tool_fix(event, req)

                # sanitize contexts (including history) by provider modalities
                self._sanitize_context_by_modalities(provider, req)

                # apply llm safety mode
                if self.llm_safety_mode:
                    self._apply_llm_safety_mode(req)

                # apply sandbox tools
                if self.sandbox_cfg.get("enable", False):
                    self._apply_sandbox_tools(req, req.session_id)

                stream_to_general = (
                    self.unsupported_streaming_strategy == "turn_off"
                    and not event.platform_meta.support_streaming_message
                )

                # run agent
                agent_runner = AgentRunner()
                logger.debug(
                    f"handle provider[id: {provider.provider_config['id']}] request: {req}",
                )
                astr_agent_ctx = AstrAgentContext(
                    context=self.ctx.plugin_manager.context,
                    event=event,
                )

                # inject model context length limit
                if provider.provider_config.get("max_context_tokens", 0) <= 0:
                    model = provider.get_model()
                    if model_info := LLM_METADATAS.get(model):
                        provider.provider_config["max_context_tokens"] = model_info[
                            "limit"
                        ]["context"]

                # ChatUI 对话的标题生成
                if event.get_platform_name() == "webchat":
                    asyncio.create_task(self._handle_webchat(event, req, provider))

                    # 注入 ChatUI 额外 prompt
                    # 比如 follow-up questions 提示等
                    req.system_prompt += f"\n{CHATUI_EXTRA_PROMPT}\n"

                # 注入基本 prompt
                if req.func_tool and req.func_tool.tools:
                    tool_prompt = (
                        TOOL_CALL_PROMPT
                        if self.tool_schema_mode == "full"
                        else TOOL_CALL_PROMPT_SKILLS_LIKE_MODE
                    )
                    req.system_prompt += f"\n{tool_prompt}\n"

                action_type = event.get_extra("action_type")
                if action_type == "live":
                    req.system_prompt += f"\n{LIVE_MODE_SYSTEM_PROMPT}\n"

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
                    llm_compress_instruction=self.llm_compress_instruction,
                    llm_compress_keep_recent=self.llm_compress_keep_recent,
                    llm_compress_provider=self._get_compress_provider(),
                    truncate_turns=self.dequeue_context_length,
                    enforce_max_turns=self.max_context_length,
                    tool_schema_mode=self.tool_schema_mode,
                )

                # 检测 Live Mode
                if action_type == "live":
                    # Live Mode: 使用 run_live_agent
                    logger.info("[Internal Agent] 检测到 Live Mode，启用 TTS 处理")

                    # 获取 TTS Provider
                    tts_provider = (
                        self.ctx.plugin_manager.context.get_using_tts_provider(
                            event.unified_msg_origin
                        )
                    )

                    if not tts_provider:
                        logger.warning(
                            "[Live Mode] TTS Provider 未配置，将使用普通流式模式"
                        )

                    # 使用 run_live_agent，总是使用流式响应
                    event.set_result(
                        MessageEventResult()
                        .set_result_content_type(ResultContentType.STREAMING_RESULT)
                        .set_async_stream(
                            run_live_agent(
                                agent_runner,
                                tts_provider,
                                self.max_step,
                                self.show_tool_use,
                                show_reasoning=self.show_reasoning,
                            ),
                        ),
                    )
                    yield

                    # 保存历史记录
                    if not event.is_stopped() and agent_runner.done():
                        await self._save_to_history(
                            event,
                            req,
                            agent_runner.get_final_llm_resp(),
                            agent_runner.run_context.messages,
                            agent_runner.stats,
                        )

                elif streaming_response and not stream_to_general:
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

                # 检查事件是否被停止，如果被停止则不保存历史记录
                if not event.is_stopped():
                    await self._save_to_history(
                        event,
                        req,
                        agent_runner.get_final_llm_resp(),
                        agent_runner.run_context.messages,
                        agent_runner.stats,
                    )

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
