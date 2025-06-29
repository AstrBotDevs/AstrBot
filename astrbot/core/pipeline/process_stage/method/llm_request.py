"""
本地 Agent 模式的 LLM 调用 Stage
"""

import traceback
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
    ToolCallMessageSegment,
    AssistantMessageSegment,
    ToolCallsResult,
)
from astrbot.core.star.star_handler import star_handlers_registry, EventType
from astrbot.core.star.star import star_map
from astrbot.core.star.session_llm_manager import SessionServiceManager
from mcp.types import (
    TextContent,
    ImageContent,
    EmbeddedResource,
    TextResourceContents,
    BlobResourceContents,
)
from astrbot.core import web_chat_back_queue


class LLMRequestSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.bot_wake_prefixs = ctx.astrbot_config["wake_prefix"]  # list
        self.provider_wake_prefix = ctx.astrbot_config["provider_settings"][
            "wake_prefix"
        ]  # str
        self.max_context_length = ctx.astrbot_config["provider_settings"][
            "max_context_length"
        ]  # int
        self.dequeue_context_length = min(
            max(1, ctx.astrbot_config["provider_settings"]["dequeue_context_length"]),
            self.max_context_length - 1,
        )  # int
        self.streaming_response = ctx.astrbot_config["provider_settings"][
            "streaming_response"
        ]  # bool

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

        # 检查会话级别的LLM启停状态
        if not SessionServiceManager.should_process_llm_request(event):
            logger.debug(f"会话 {event.unified_msg_origin} 禁用了 LLM，跳过处理。")
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
                all_contexts = json.loads(req.conversation.history)
                req.contexts = self._process_tool_message_pairs(
                    all_contexts, remove_tags=True
                )

        else:
            req = ProviderRequest(prompt="", image_urls=[])
            if self.provider_wake_prefix:
                if not event.message_str.startswith(self.provider_wake_prefix):
                    return
            req.prompt = event.message_str[len(self.provider_wake_prefix) :]
            if SessionServiceManager.should_process_mcp_request(event):
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
        # 装饰 system_prompt 等功能
        # 获取当前平台ID
        platform_id = event.get_platform_id()
        handlers = star_handlers_registry.get_handlers_by_event_type(
            EventType.OnLLMRequestEvent, platform_id=platform_id
        )
        for handler in handlers:
            try:
                logger.debug(
                    f"hook(on_llm_request) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}"
                )
                await handler.handler(event, req)
            except BaseException:
                logger.error(traceback.format_exc())

            if event.is_stopped():
                logger.info(
                    f"{star_map[handler.handler_module_path].name} - {handler.handler_name} 终止了事件传播。"
                )
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

        async def requesting(req: ProviderRequest):
            try:
                need_loop = True
                while need_loop:
                    need_loop = False
                    
                    # 在每次实际请求 LLM 前检查会话级别的启停状态，这可以防止插件或函数工具调用时绕过会话级别的限制
                    if not SessionServiceManager.should_process_llm_request(event):
                        logger.debug(f"会话 {event.unified_msg_origin} 禁用了 LLM，终止 LLM 请求。")
                        return
                    
                    logger.debug(f"提供商请求 Payload: {req}")

                    final_llm_response = None

                    if self.streaming_response:
                        stream = provider.text_chat_stream(**req.__dict__)
                        async for llm_response in stream:
                            if llm_response.is_chunk:
                                if llm_response.result_chain:
                                    yield llm_response.result_chain  # MessageChain
                                else:
                                    yield MessageChain().message(
                                        llm_response.completion_text
                                    )
                            else:
                                final_llm_response = llm_response
                    else:
                        final_llm_response = await provider.text_chat(
                            **req.__dict__
                        )  # 请求 LLM

                    if not final_llm_response:
                        raise Exception("LLM response is None.")

                    # 执行 LLM 响应后的事件钩子。
                    handlers = star_handlers_registry.get_handlers_by_event_type(
                        EventType.OnLLMResponseEvent
                    )
                    for handler in handlers:
                        try:
                            logger.debug(
                                f"hook(on_llm_response) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}"
                            )
                            await handler.handler(event, final_llm_response)
                        except BaseException:
                            logger.error(traceback.format_exc())

                        if event.is_stopped():
                            logger.info(
                                f"{star_map[handler.handler_module_path].name} - {handler.handler_name} 终止了事件传播。"
                            )
                            return

                    if self.streaming_response:
                        # 流式输出的处理
                        async for result in self._handle_llm_stream_response(
                            event, req, final_llm_response
                        ):
                            if isinstance(result, ProviderRequest):
                                # 有函数工具调用并且返回了结果，我们需要再次请求 LLM
                                req = result
                                need_loop = True
                            else:
                                yield
                    else:
                        # 非流式输出的处理
                        async for result in self._handle_llm_response(
                            event, req, final_llm_response
                        ):
                            if isinstance(result, ProviderRequest):
                                # 有函数工具调用并且返回了结果，我们需要再次请求 LLM
                                req = result
                                need_loop = True
                            else:
                                yield

                asyncio.create_task(
                    Metric.upload(
                        llm_tick=1,
                        model_name=provider.get_model(),
                        provider_type=provider.meta().type,
                    )
                )

                # 保存到历史记录
                await self._save_to_history(event, req, final_llm_response)

            except BaseException as e:
                logger.error(traceback.format_exc())
                event.set_result(
                    MessageEventResult().message(
                        f"AstrBot 请求失败。\n错误类型: {type(e).__name__}\n错误信息: {str(e)}"
                    )
                )

        if not self.streaming_response:
            event.set_extra("tool_call_result", None)
            async for _ in requesting(req):
                yield
        else:
            event.set_result(
                MessageEventResult()
                .set_result_content_type(ResultContentType.STREAMING_RESULT)
                .set_async_stream(requesting(req))
            )
            # 这里使用yield来暂停当前阶段，等待流式输出完成后继续处理
            yield

            if event.get_extra("tool_call_result"):
                event.set_result(event.get_extra("tool_call_result"))
                event.set_extra("tool_call_result", None)
                yield

        # 暂时直接发出去
        if img_b64 := event.get_extra("tool_call_img_respond"):
            await event.send(MessageChain(chain=[Image.fromBase64(img_b64)]))
            event.set_extra("tool_call_img_respond", None)

        if event.get_platform_name() == "webchat":
            # 异步处理 WebChat 特殊情况
            asyncio.create_task(self._handle_webchat(event, req))

    async def _handle_webchat(self, event: AstrMessageEvent, req: ProviderRequest):
        """处理 WebChat 平台的特殊情况，包括第一次 LLM 对话时总结对话内容生成 title"""
        # 检查会话级别的LLM启停状态，防止标题生成功能绕过会话级别限制
        if not SessionServiceManager.should_process_llm_request(event):
            logger.debug(f"会话 {event.unified_msg_origin} 禁用了 LLM，跳过 WebChat 标题生成。")
            return
            
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
            # if len(latest_pair) > 1:
            #     cleaned_text += (
            #         "\nAssistant: " + latest_pair[1].get("content", "").strip()
            #     )
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

    async def _handle_llm_response(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> AsyncGenerator[Union[None, ProviderRequest], None]:
        """处理非流式 LLM 响应。

        Returns:
            AsyncGenerator[Union[None, ProviderRequest], None]: 如果返回 ProviderRequest，表示需要再次调用 LLM

        Yields:
            Iterator[Union[None, ProviderRequest]]: 将 event 交付给下一个 stage 或者返回 ProviderRequest 表示需要再次调用 LLM
        """
        if llm_response.role == "assistant":
            # text completion
            if llm_response.result_chain:
                event.set_result(
                    MessageEventResult(
                        chain=llm_response.result_chain.chain
                    ).set_result_content_type(ResultContentType.LLM_RESULT)
                )
            else:
                event.set_result(
                    MessageEventResult()
                    .message(llm_response.completion_text)
                    .set_result_content_type(ResultContentType.LLM_RESULT)
                )
        elif llm_response.role == "err":
            event.set_result(
                MessageEventResult().message(
                    f"AstrBot 请求失败。\n错误信息: {llm_response.completion_text}"
                )
            )
        elif llm_response.role == "tool":
            # 处理函数工具调用
            async for result in self._handle_function_tools(event, req, llm_response):
                yield result

    async def _handle_llm_stream_response(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> AsyncGenerator[Union[None, ProviderRequest], None]:
        """处理流式 LLM 响应。

        专门用于处理流式输出完成后的响应，与非流式响应处理分离。

        Returns:
            AsyncGenerator[Union[None, ProviderRequest], None]: 如果返回 ProviderRequest，表示需要再次调用 LLM

        Yields:
            Iterator[Union[None, ProviderRequest]]: 将 event 交付给下一个 stage 或者返回 ProviderRequest 表示需要再次调用 LLM
        """
        if llm_response.role == "assistant":
            # text completion
            if llm_response.result_chain:
                event.set_result(
                    MessageEventResult(
                        chain=llm_response.result_chain.chain
                    ).set_result_content_type(ResultContentType.STREAMING_FINISH)
                )
            else:
                event.set_result(
                    MessageEventResult()
                    .message(llm_response.completion_text)
                    .set_result_content_type(ResultContentType.STREAMING_FINISH)
                )
        elif llm_response.role == "err":
            event.set_result(
                MessageEventResult().message(
                    f"AstrBot 请求失败。\n错误信息: {llm_response.completion_text}"
                )
            )
        elif llm_response.role == "tool":
            # 处理函数工具调用
            async for result in self._handle_function_tools(event, req, llm_response):
                yield result

    async def _handle_function_tools(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> AsyncGenerator[Union[None, ProviderRequest], None]:
        """处理函数工具调用。

        Returns:
            AsyncGenerator[Union[None, ProviderRequest], None]: 如果返回 ProviderRequest，表示需要再次调用 LLM
        """
        # function calling
        tool_call_result: list[ToolCallMessageSegment] = []
        logger.info(
            f"触发 {len(llm_response.tools_call_name)} 个函数调用: {llm_response.tools_call_name}"
        )
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
                    if res:
                        # TODO 仅对ImageContent | EmbeddedResource进行了简单的Fallback
                        if isinstance(res.content[0], TextContent):
                            tool_call_result.append(
                                ToolCallMessageSegment(
                                    role="tool",
                                    tool_call_id=func_tool_id,
                                    content=res.content[0].text,
                                )
                            )
                        elif isinstance(res.content[0], ImageContent):
                            tool_call_result.append(
                                ToolCallMessageSegment(
                                    role="tool",
                                    tool_call_id=func_tool_id,
                                    content="返回了图片(已直接发送给用户)",
                                )
                            )
                            event.set_extra(
                                "tool_call_img_respond",
                                res.content[0].data,
                            )
                        elif isinstance(res.content[0], EmbeddedResource):
                            resource = res.content[0].resource
                            if isinstance(resource, TextResourceContents):
                                tool_call_result.append(
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
                                tool_call_result.append(
                                    ToolCallMessageSegment(
                                        role="tool",
                                        tool_call_id=func_tool_id,
                                        content="返回了图片(已直接发送给用户)",
                                    )
                                )
                                event.set_extra(
                                    "tool_call_img_respond",
                                    res.content[0].data,
                                )
                            else:
                                tool_call_result.append(
                                    ToolCallMessageSegment(
                                        role="tool",
                                        tool_call_id=func_tool_id,
                                        content="返回的数据类型不受支持",
                                    )
                                )
                else:
                    # 获取处理器，过滤掉平台不兼容的处理器
                    platform_id = event.get_platform_id()
                    star_md = star_map.get(func_tool.handler_module_path)
                    if (
                        star_md
                        and platform_id in star_md.supported_platforms
                        and not star_md.supported_platforms[platform_id]
                    ):
                        logger.debug(
                            f"处理器 {func_tool_name}({star_md.name}) 在当前平台不兼容或者被禁用，跳过执行"
                        )
                        # 直接跳过，不添加任何消息到tool_call_result
                        continue

                    logger.info(
                        f"调用工具函数：{func_tool_name}，参数：{func_tool_args}"
                    )
                    # 尝试调用工具函数
                    wrapper = self._call_handler(
                        self.ctx, event, func_tool.handler, **func_tool_args
                    )
                    async for resp in wrapper:
                        if resp is not None:  # 有 return 返回
                            tool_call_result.append(
                                ToolCallMessageSegment(
                                    role="tool",
                                    tool_call_id=func_tool_id,
                                    content=resp,
                                )
                            )
                        else:
                            res = event.get_result()
                            if res and res.chain:
                                event.set_extra("tool_call_result", res)
                            yield  # 有生成器返回
                event.clear_result()  # 清除上一个 handler 的结果
            except BaseException as e:
                logger.warning(traceback.format_exc())
                tool_call_result.append(
                    ToolCallMessageSegment(
                        role="tool",
                        tool_call_id=func_tool_id,
                        content=f"error: {str(e)}",
                    )
                )
        if tool_call_result:
            # 函数调用结果
            req.func_tool = None  # 暂时不支持递归工具调用
            assistant_msg_seg = AssistantMessageSegment(
                role="assistant", tool_calls=llm_response.to_openai_tool_calls()
            )
            # 在多轮 Tool 调用的情况下，这里始终保持最新的 Tool 调用结果，减少上下文长度。
            req.tool_calls_result = ToolCallsResult(
                tool_calls_info=assistant_msg_seg,
                tool_calls_result=tool_call_result,
            )
            yield req  # 再次执行 LLM 请求
        else:
            if llm_response.completion_text:
                event.set_result(
                    MessageEventResult().message(llm_response.completion_text)
                )

    async def _save_to_history(
        self, event: AstrMessageEvent, req: ProviderRequest, llm_response: LLMResponse
    ):
        if not req or not req.conversation or not llm_response:
            return

        if llm_response.role == "assistant":
            # 文本回复
            contexts = req.contexts.copy()
            contexts.append(await req.assemble_context())

            # 记录并标记函数调用结果
            if req.tool_calls_result:
                tool_calls_messages = req.tool_calls_result.to_openai_messages()

                # 添加标记
                for message in tool_calls_messages:
                    message["_tool_call_history"] = True

                processed_tool_messages = self._process_tool_message_pairs(
                    tool_calls_messages, remove_tags=False
                )

                contexts.extend(processed_tool_messages)

            contexts.append(
                {"role": "assistant", "content": llm_response.completion_text}
            )
            contexts_to_save = list(
                filter(lambda item: "_no_save" not in item, contexts)
            )
            await self.conv_manager.update_conversation(
                event.unified_msg_origin, req.conversation.cid, history=contexts_to_save
            )

    def _process_tool_message_pairs(self, messages, remove_tags=True):
        """处理工具调用消息，确保assistant和tool消息成对出现

        Args:
            messages (list): 消息列表
            remove_tags (bool): 是否移除_tool_call_history标记

        Returns:
            list: 处理后的消息列表，保证了assistant和对应tool消息的成对出现
        """
        result = []
        i = 0

        while i < len(messages):
            current_msg = messages[i]

            # 普通消息直接添加
            if "_tool_call_history" not in current_msg:
                result.append(current_msg.copy() if remove_tags else current_msg)
                i += 1
                continue

            # 工具调用消息成对处理
            if current_msg.get("role") == "assistant" and "tool_calls" in current_msg:
                assistant_msg = current_msg.copy()

                if remove_tags and "_tool_call_history" in assistant_msg:
                    del assistant_msg["_tool_call_history"]

                related_tools = []
                j = i + 1
                while (
                    j < len(messages)
                    and messages[j].get("role") == "tool"
                    and "_tool_call_history" in messages[j]
                ):
                    tool_msg = messages[j].copy()

                    if remove_tags:
                        del tool_msg["_tool_call_history"]

                    related_tools.append(tool_msg)
                    j += 1

                # 成对的时候添加到结果
                if related_tools:
                    result.append(assistant_msg)
                    result.extend(related_tools)

                i = j  # 跳过已处理
            else:
                # 单独的tool消息
                i += 1

        return result
