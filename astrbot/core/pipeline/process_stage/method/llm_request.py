"""
本地 Agent 模式的 LLM 调用 Stage
"""

import traceback
import copy
import asyncio
import json
from typing import Union, AsyncGenerator
from ...context import PipelineContext
from ..stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
    MessageChain,
)
from astrbot.core.message.components import Image
from astrbot.core import logger
from astrbot.core.utils.metrics import Metric
from astrbot.core.provider.entities import (
    ProviderRequest,
    LLMResponse,
)
from astrbot.core.star.star_handler import EventType
from astrbot.core import web_chat_back_queue
from ..agent_runner.tool_loop_agent import ToolLoopAgent


class LLMRequestSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        conf = ctx.astrbot_config
        self.bot_wake_prefixs: list[str] = conf["wake_prefix"]  # list
        self.provider_wake_prefix: str = conf["provider_settings"]["wake_prefix"]  # str
        self.max_context_length = conf["provider_settings"]["max_context_length"]  # int
        self.dequeue_context_length: int = min(
            max(1, conf["provider_settings"]["dequeue_context_length"]),
            self.max_context_length - 1,
        )
        self.streaming_response: bool = conf["provider_settings"]["streaming_response"]
        self.max_step: int = conf["provider_settings"].get("max_agent_step", 10)

        for bwp in self.bot_wake_prefixs:
            if self.provider_wake_prefix.startswith(bwp):
                logger.info(
                    f"识别 LLM 聊天额外唤醒前缀 {self.provider_wake_prefix} 以机器人唤醒前缀 {bwp} 开头，已自动去除。"
                )
                self.provider_wake_prefix = self.provider_wake_prefix[len(bwp) :]

        self.conv_manager = ctx.plugin_manager.context.conversation_manager

    async def process(
        self, event: AstrMessageEvent, _nested: bool = False
    ) -> Union[None, AsyncGenerator[None, None]]:
        req: ProviderRequest = None

        if not self.ctx.astrbot_config["provider_settings"]["enable"]:
            logger.debug("未启用 LLM 能力，跳过处理。")
            return
        umo = event.unified_msg_origin
        provider = self.ctx.plugin_manager.context.get_using_provider(umo=umo)
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
            if self.provider_wake_prefix:
                if not event.message_str.startswith(self.provider_wake_prefix):
                    return
            req.prompt = event.message_str[len(self.provider_wake_prefix) :]
            req.func_tool = self.ctx.plugin_manager.context.get_llm_tool_manager()
            for comp in event.message_obj.message:
                if isinstance(comp, Image):
                    image_path = await comp.convert_to_file_path()
                    req.image_urls.append(image_path)

            # 获取对话上下文
            conversation_id = await self.conv_manager.get_curr_conversation_id(
                event.unified_msg_origin
            )
            if not conversation_id:
                conversation_id = await self.conv_manager.new_conversation(
                    event.unified_msg_origin
                )
            conversation = await self.conv_manager.get_conversation(
                event.unified_msg_origin, conversation_id
            )
            if not conversation:
                conversation_id = await self.conv_manager.new_conversation(
                    event.unified_msg_origin
                )
                conversation = await self.conv_manager.get_conversation(
                    event.unified_msg_origin, conversation_id
                )
            req.conversation = conversation
            req.contexts = json.loads(conversation.history)

            event.set_extra("provider_request", req)

        if not req.prompt and not req.image_urls:
            return

        # 执行请求 LLM 前事件钩子。
        await self.ctx.call_event_hook(event, EventType.OnLLMRequestEvent, req)

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

        # Call Agent
        tool_loop_agent = ToolLoopAgent(
            provider=provider,
            event=event,
            pipeline_ctx=self.ctx,
        )
        await tool_loop_agent.reset(req=req, streaming=self.streaming_response)

        async def requesting():
            step_idx = 0
            while step_idx < self.max_step:
                step_idx += 1
                try:
                    async for resp in tool_loop_agent.step():
                        if not self.streaming_response:
                            content_typ = (
                                ResultContentType.LLM_RESULT
                                if resp.type == "llm_resp"
                                else ResultContentType.GENERAL_RESULT
                            )
                            event.set_result(
                                MessageEventResult(
                                    chain=resp.data["chain"],
                                    result_content_type=content_typ,
                                )
                            )
                            yield
                            event.clear_result()
                        else:
                            yield resp.data["chain"]
                    if tool_loop_agent.done():
                        break
                except Exception as e:
                    logger.error(traceback.format_exc())
                    event.set_result(
                        MessageEventResult().message(
                            f"AstrBot 请求失败。\n错误类型: {type(e).__name__}\n错误信息: {str(e)}"
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

        # 异步处理 WebChat 特殊情况
        if event.get_platform_name() == "webchat":
            asyncio.create_task(self._handle_webchat(event, req))

        await self._save_to_history(event, req, tool_loop_agent.get_final_llm_resp())

    async def _handle_webchat(self, event: AstrMessageEvent, req: ProviderRequest):
        """处理 WebChat 平台的特殊情况，包括第一次 LLM 对话时总结对话内容生成 title"""
        conversation = await self.conv_manager.get_conversation(
            event.unified_msg_origin, req.conversation.cid
        )
        if conversation and not req.conversation.title:
            messages = json.loads(conversation.history)
            latest_pair = messages[-2:]
            if not latest_pair:
                return
            provider = self.ctx.plugin_manager.context.get_using_provider()
            cleaned_text = "User: " + latest_pair[0].get("content", "").strip()
            logger.debug(f"WebChat 对话标题生成请求，清理后的文本: {cleaned_text}")
            llm_resp = await provider.text_chat(
                system_prompt="You are expert in summarizing user's query.",
                prompt=(
                    f"Please summarize the following query of user:\n"
                    f"{cleaned_text}\n"
                    "Only output the summary within 10 words, DO NOT INCLUDE any other text."
                    "You must use the same language as the user."
                    "If you think the dialog is too short to summarize, only output a special mark: `None`"
                ),
            )
            if llm_resp and llm_resp.completion_text:
                logger.debug(
                    f"WebChat 对话标题生成响应: {llm_resp.completion_text.strip()}"
                )
                title = llm_resp.completion_text.strip()
                if not title or "None" == title:
                    return
                await self.conv_manager.update_conversation_title(
                    event.unified_msg_origin, title=title
                )
                # 由于 WebChat 平台特殊性，其有两个对话，因此我们要更新两个对话的标题
                # webchat adapter 中，session_id 的格式是 f"webchat!{username}!{cid}"
                # TODO: 优化 WebChat 适配器的对话管理
                if event.session_id:
                    username, cid = event.session_id.split("!")[1:3]
                    db_helper = self.ctx.plugin_manager.context._db
                    db_helper.update_conversation_title(
                        user_id=username,
                        cid=cid,
                        title=title,
                    )
                    web_chat_back_queue.put_nowait(
                        {
                            "type": "update_title",
                            "cid": cid,
                            "data": title,
                        }
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
        logger.debug(f"messages persisted: {messages}")
