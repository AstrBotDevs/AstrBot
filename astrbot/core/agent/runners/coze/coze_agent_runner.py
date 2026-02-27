import base64
import json
import sys
import typing as T

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core import sp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
)

from ...hooks import BaseAgentRunHooks
from ...response import AgentResponseData
from ...run_context import ContextWrapper, TContext
from ..base import AgentResponse, AgentState, BaseAgentRunner
from .coze_api_client import CozeAPIClient

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class CozeAgentRunner(BaseAgentRunner[TContext]):
    """Coze Agent Runner"""

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

        self.api_key = provider_config.get("coze_api_key", "")
        if not self.api_key:
            raise Exception("Coze API Key 不能为空。")
        self.bot_id = provider_config.get("bot_id", "")
        if not self.bot_id:
            raise Exception("Coze Bot ID 不能为空。")
        self.api_base: str = provider_config.get("coze_api_base", "https://api.coze.cn")

        if not isinstance(self.api_base, str) or not self.api_base.startswith(
            ("http://", "https://"),
        ):
            raise Exception(
                "Coze API Base URL 格式不正确，必须以 http:// 或 https:// 开头。",
            )

        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)
        self.auto_save_history = provider_config.get("auto_save_history", True)

        # 创建 API 客户端
        self.api_client = CozeAPIClient(api_key=self.api_key, api_base=self.api_base)

        # 会话相关缓存
        self.file_id_cache: dict[str, dict[str, str]] = {}

    @override
    async def step(self):
        """
        执行 Coze Agent 的一个步骤
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
            # 执行 Coze 请求并处理结果
            async for response in self._execute_coze_request():
                yield response
        except Exception as e:
            logger.error(f"Coze 请求失败：{str(e)}")
            self._transition_state(AgentState.ERROR)
            self.final_llm_resp = LLMResponse(
                role="err", completion_text=f"Coze 请求失败：{str(e)}"
            )
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(f"Coze 请求失败：{str(e)}")
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

    async def _execute_coze_request(self):
        """执行 Coze 请求的核心逻辑"""
        prompt = self.req.prompt or ""
        session_id = self.req.session_id or "unknown"
        image_urls = self.req.image_urls or []
        contexts = self.req.contexts or []
        system_prompt = self.req.system_prompt

        # 用户ID参数
        user_id = session_id

        # 获取或创建会话ID
        conversation_id = await sp.get_async(
            scope="umo",
            scope_id=user_id,
            key="coze_conversation_id",
            default="",
        )

        # 构建消息
        additional_messages = []

        if system_prompt:
            if not self.auto_save_history or not conversation_id:
                additional_messages.append(
                    {
                        "role": "system",
                        "content": system_prompt,
                        "content_type": "text",
                    },
                )

        # 处理历史上下文
        if not self.auto_save_history and contexts:
            for ctx in contexts:
                if isinstance(ctx, dict) and "role" in ctx and "content" in ctx:
                    # 处理上下文中的图片
                    content = ctx["content"]
                    if isinstance(content, list):
                        # 多模态内容，需要处理图片
                        processed_content = []
                        for item in content:
                            if isinstance(item, dict):
                                if item.get("type") == "text":
                                    processed_content.append(item)
                                elif item.get("type") == "image_url":
                                    # 处理图片上传
                                    try:
                                        image_data = item.get("image_url", {})
                                        url = image_data.get("url", "")
                                        if url:
                                            file_id = (
                                                await self._download_and_upload_image(
                                                    url, session_id
                                                )
                                            )
                                            processed_content.append(
                                                {
                                                    "type": "file",
                                                    "file_id": file_id,
                                                    "file_url": url,
                                                }
                                            )
                                    except Exception as e:
                                        logger.warning(f"处理上下文图片失败: {e}")
                                        continue

                        if processed_content:
                            additional_messages.append(
                                {
                                    "role": ctx["role"],
                                    "content": processed_content,
                                    "content_type": "object_string",
                                }
                            )
                    else:
                        # 纯文本内容
                        additional_messages.append(
                            {
                                "role": ctx["role"],
                                "content": content,
                                "content_type": "text",
                            }
                        )

        # 构建当前消息
        if prompt or image_urls:
            if image_urls:
                # 多模态
                object_string_content = []
                if prompt:
                    object_string_content.append({"type": "text", "text": prompt})

                for url in image_urls:
                    # the url is a base64 string
                    try:
                        image_data = base64.b64decode(url)
                        file_id = await self.api_client.upload_file(image_data)
                        object_string_content.append(
                            {
                                "type": "image",
                                "file_id": file_id,
                            }
                        )
                    except Exception as e:
                        logger.warning(f"处理图片失败 {url}: {e}")
                        continue

                if object_string_content:
                    content = json.dumps(object_string_content, ensure_ascii=False)
                    additional_messages.append(
                        {
                            "role": "user",
                            "content": content,
                            "content_type": "object_string",
                        }
                    )
            elif prompt:
                # 纯文本
                additional_messages.append(
                    {
                        "role": "user",
                        "content": prompt,
                        "content_type": "text",
                    },
                )

        # 执行 Coze API 请求
        accumulated_content = ""
        message_started = False

        async for chunk in self.api_client.chat_messages(
            bot_id=self.bot_id,
            user_id=user_id,
            additional_messages=additional_messages,
            conversation_id=conversation_id,
            auto_save_history=self.auto_save_history,
            stream=True,
            timeout=self.timeout,
        ):
            event_type = chunk.get("event")
            data = chunk.get("data", {})

            if event_type == "conversation.chat.created":
                if isinstance(data, dict) and "conversation_id" in data:
                    await sp.put_async(
                        scope="umo",
                        scope_id=user_id,
                        key="coze_conversation_id",
                        value=data["conversation_id"],
                    )

            if event_type == "conversation.message.delta":
                # 增量消息
                content = data.get("content", "")
                if not content and "delta" in data:
                    content = data["delta"].get("content", "")
                if not content and "text" in data:
                    content = data.get("text", "")

                if content:
                    accumulated_content += content
                    message_started = True

                    # 如果是流式响应，发送增量数据
                    if self.streaming:
                        yield AgentResponse(
                            type="streaming_delta",
                            data=AgentResponseData(
                                chain=MessageChain().message(content)
                            ),
                        )

            elif event_type == "conversation.message.completed":
                # 消息完成
                logger.debug("Coze message completed")
                message_started = True

            elif event_type == "conversation.chat.completed":
                # 对话完成
                logger.debug("Coze chat completed")
                break

            elif event_type == "error":
                # 错误处理
                error_msg = data.get("msg", "未知错误")
                error_code = data.get("code", "UNKNOWN")
                logger.error(f"Coze 出现错误: {error_code} - {error_msg}")
                raise Exception(f"Coze 出现错误: {error_code} - {error_msg}")

        if not message_started and not accumulated_content:
            logger.warning("Coze 未返回任何内容")
            accumulated_content = ""

        # 创建最终响应
        chain = MessageChain(chain=[Comp.Plain(accumulated_content)])
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

    async def _download_and_upload_image(
        self,
        image_url: str,
        session_id: str | None = None,
    ) -> str:
        """下载图片并上传到 Coze，返回 file_id"""
        import hashlib

        # 计算哈希实现缓存
        cache_key = hashlib.md5(image_url.encode("utf-8")).hexdigest()

        if session_id:
            if session_id not in self.file_id_cache:
                self.file_id_cache[session_id] = {}

            if cache_key in self.file_id_cache[session_id]:
                file_id = self.file_id_cache[session_id][cache_key]
                logger.debug(f"[Coze] 使用缓存的 file_id: {file_id}")
                return file_id

        try:
            image_data = await self.api_client.download_image(image_url)
            file_id = await self.api_client.upload_file(image_data)

            if session_id:
                self.file_id_cache[session_id][cache_key] = file_id
                logger.debug(f"[Coze] 图片上传成功并缓存，file_id: {file_id}")

            return file_id

        except Exception as e:
            logger.error(f"处理图片失败 {image_url}: {e!s}")
            raise Exception(f"处理图片失败: {e!s}")

    @override
    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    @override
    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
