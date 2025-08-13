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
from astrbot.core.star.session_llm_manager import SessionServiceManager
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.metrics import Metric
from ...context import PipelineContext
from ..agent_runner.tool_loop_agent import ToolLoopAgent
from ..stage import Stage


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
        if await self.ctx.call_event_hook(event, EventType.OnLLMRequestEvent, req):
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
        # 如果提供商不支持图像，但请求中包含图像，则清空图像列表。图片转述的检测和调用发生在这之前，因此这里可以这样处理。
        if req.image_urls:
            provider_cfg = provider.provider_config.get("modalities", ["text", "image"])
            if "image" not in provider_cfg:
                req.image_urls = []

        # Call Agent
        tool_loop_agent = ToolLoopAgent(
            provider=provider,
            event=event,
            pipeline_ctx=self.ctx,
        )
        logger.debug(
            f"handle provider[id: {provider.provider_config['id']}] request: {req}"
        )
        await tool_loop_agent.reset(req=req, streaming=self.streaming_response)

        async def requesting():
            step_idx = 0
            while step_idx < self.max_step:
                step_idx += 1
                try:
                    async for resp in tool_loop_agent.step():
                        if event.is_stopped():
                            return
                        if resp.type == "tool_call_result":
                            msg_chain = resp.data["chain"]
                            if msg_chain.type == "tool_direct_result":
                                # tool_direct_result 用于标记 llm tool 需要直接发送给用户的内容
                                resp.data["chain"].type = "tool_call_result"
                                await event.send(resp.data["chain"])
                                continue
                            # 对于其他情况，暂时先不处理
                            continue
                        elif resp.type == "tool_call":
                            if self.streaming_response:
                                # 用来标记流式响应需要分节
                                yield MessageChain(chain=[], type="break")
                            if (
                                self.show_tool_use
                                or event.get_platform_name() == "webchat"
                            ):
                                resp.data["chain"].type = "tool_call"
                                await event.send(resp.data["chain"])
                            continue

                        if not self.streaming_response:
                            content_typ = (
                                ResultContentType.LLM_RESULT
                                if resp.type == "llm_result"
                                else ResultContentType.GENERAL_RESULT
                            )
                            event.set_result(
                                MessageEventResult(
                                    chain=resp.data["chain"].chain,
                                    result_content_type=content_typ,
                                )
                            )
                            yield
                            event.clear_result()
                        else:
                            if resp.type == "streaming_delta":
                                yield resp.data["chain"]  # MessageChain
                    if tool_loop_agent.done():
                        break

                except Exception as e:
                    logger.error(traceback.format_exc())
                    event.set_result(
                        MessageEventResult().message(
                            f"AstrBot 请求失败。\n错误类型: {type(e).__name__}\n错误信息: {str(e)}\n\n请在控制台查看和分享错误详情。\n"
                        )
                    )
                    return
                asyncio.create_task(
                    Metric.upload(
                        llm_tick=1,
                        model_name=provider.get_model(),
                        provider_type=provider.meta().type,
                    )
                )

        if self.streaming_response:
            # 流式响应
            event.set_result(
                MessageEventResult()
                .set_result_content_type(ResultContentType.STREAMING_RESULT)
                .set_async_stream(requesting())
            )
            yield
            if tool_loop_agent.done():
                if final_llm_resp := tool_loop_agent.get_final_llm_resp():
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
            async for _ in requesting():
                yield
        await self._save_to_history(event, req, tool_loop_agent.get_final_llm_resp())

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
