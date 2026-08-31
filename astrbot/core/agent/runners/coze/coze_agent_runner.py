import asyncio
import json
import typing as T
from typing import override

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.media_utils import MediaResolver, describe_media_ref
from astrbot.core.utils.shared_preferences import SharedPreferences

from ...hooks import BaseAgentRunHooks
from ...llm_types import LLMResponse, ProviderRequest
from ...message import is_checkpoint_message
from ...response import AgentResponseData
from ...run_context import ContextWrapper, TContext
from ..base import AgentResponse, AgentState, BaseAgentRunner
from .coze_api_client import CozeAPIClient


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
        self.preferences: SharedPreferences = kwargs["preferences"]

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

        from astrbot.core.utils.proxy_route import resolve_proxy_route

        self.api_client = CozeAPIClient(
            api_key=self.api_key,
            api_base=self.api_base,
            proxy_route=resolve_proxy_route(local_config=provider_config),
        )

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
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in on_agent_begin hook: {e}", exc_info=True)

        # 开始处理，转换到运行状态
        self._transition_state(AgentState.RUNNING)

        try:
            # 执行 Coze 请求并处理结果
            async for response in self._execute_coze_request():
                yield response
        except asyncio.CancelledError:
            raise
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

    async def _build_history_messages(self, session_id: str) -> list[dict]:
        """Convert manually supplied AstrBot history into Coze messages."""
        messages: list[dict] = []
        for ctx in self.req.contexts or []:
            if is_checkpoint_message(ctx) or not isinstance(ctx, dict):
                continue
            if "role" not in ctx or "content" not in ctx:
                continue
            content = ctx["content"]
            if not isinstance(content, list):
                messages.append(
                    {"role": ctx["role"], "content": content, "content_type": "text"}
                )
                continue
            processed_content = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    processed_content.append(item)
                elif item.get("type") == "image_url":
                    try:
                        url = item.get("image_url", {}).get("url", "")
                        if url:
                            file_id = await self._download_and_upload_image(
                                url, session_id
                            )
                            processed_content.append(
                                {"type": "file", "file_id": file_id, "file_url": url}
                            )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning("处理上下文图片失败: %s", exc)
            if processed_content:
                messages.append(
                    {
                        "role": ctx["role"],
                        "content": processed_content,
                        "content_type": "object_string",
                    }
                )
        return messages

    async def _build_additional_messages(
        self,
        session_id: str,
        conversation_id: str,
    ) -> list[dict]:
        """Build Coze history and current-input payloads for one request."""
        prompt = self.req.prompt or ""
        image_urls = self.req.image_urls or []
        additional_messages: list[dict] = []
        if self.req.system_prompt and (
            not self.auto_save_history or not conversation_id
        ):
            additional_messages.append(
                {
                    "role": "system",
                    "content": self.req.system_prompt,
                    "content_type": "text",
                }
            )

        if not self.auto_save_history:
            additional_messages.extend(await self._build_history_messages(session_id))

        if image_urls:
            content = [{"type": "text", "text": prompt}] if prompt else []
            for url in image_urls:
                try:
                    file_id = await self._download_and_upload_image(url, session_id)
                    content.append({"type": "image", "file_id": file_id})
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("处理图片失败 %s: %s", describe_media_ref(url), exc)
            if content:
                additional_messages.append(
                    {
                        "role": "user",
                        "content": json.dumps(content, ensure_ascii=False),
                        "content_type": "object_string",
                    }
                )
        elif prompt:
            additional_messages.append(
                {"role": "user", "content": prompt, "content_type": "text"}
            )
        return additional_messages

    async def _consume_coze_events(self, events, user_id: str):
        """Convert Coze's event stream into agent responses and final state."""
        accumulated_content = ""
        message_started = False
        async for chunk in events:
            event_type = chunk.get("event")
            data = chunk.get("data", {})
            if event_type == "conversation.chat.created":
                if isinstance(data, dict) and "conversation_id" in data:
                    await self.preferences.put_async(
                        scope="umo",
                        scope_id=user_id,
                        key="coze_conversation_id",
                        value=data["conversation_id"],
                    )
            elif event_type == "conversation.message.delta":
                content = data.get("content", "")
                if not content and "delta" in data:
                    content = data["delta"].get("content", "")
                if not content and "text" in data:
                    content = data.get("text", "")
                if content:
                    accumulated_content += content
                    message_started = True
                    if self.streaming:
                        yield AgentResponse(
                            type="streaming_delta",
                            data=AgentResponseData(
                                chain=MessageChain().message(content)
                            ),
                        )
            elif event_type == "conversation.message.completed":
                message_started = True
            elif event_type == "conversation.chat.completed":
                break
            elif event_type == "error":
                error_msg = data.get("msg", "未知错误")
                error_code = data.get("code", "UNKNOWN")
                logger.error("Coze 出现错误: %s - %s", error_code, error_msg)
                raise Exception(f"Coze 出现错误: {error_code} - {error_msg}")

        if not message_started and not accumulated_content:
            logger.warning("Coze 未返回任何内容")
        chain = MessageChain(chain=[Comp.Plain(accumulated_content)])
        self.final_llm_resp = LLMResponse(role="assistant", result_chain=chain)
        self._transition_state(AgentState.DONE)
        try:
            await self.agent_hooks.on_agent_done(self.run_context, self.final_llm_resp)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Error in on_agent_done hook: %s", exc, exc_info=True)
        yield AgentResponse(type="llm_result", data=AgentResponseData(chain=chain))

    async def _execute_coze_request(self):
        """Execute a Coze request after constructing its message payload."""
        session_id = self.req.session_id or "unknown"
        conversation_id = await self.preferences.get_async(
            scope="umo",
            scope_id=session_id,
            key="coze_conversation_id",
            default="",
        )
        additional_messages = await self._build_additional_messages(
            session_id, conversation_id
        )

        events = self.api_client.chat_messages(
            bot_id=self.bot_id,
            user_id=session_id,
            additional_messages=additional_messages,
            conversation_id=conversation_id,
            auto_save_history=self.auto_save_history,
            stream=True,
            timeout_seconds=self.timeout,
        )
        async for response in self._consume_coze_events(events, session_id):
            yield response

    async def _download_and_upload_image(
        self,
        image_url: str,
        session_id: str | None = None,
    ) -> str:
        """下载图片并上传到 Coze，返回 file_id"""
        import hashlib

        # 计算哈希实现缓存
        cache_key = hashlib.md5(
            image_url.encode("utf-8"), usedforsecurity=False
        ).hexdigest()

        if session_id:
            if session_id not in self.file_id_cache:
                self.file_id_cache[session_id] = {}

            if cache_key in self.file_id_cache[session_id]:
                file_id = self.file_id_cache[session_id][cache_key]
                logger.debug(f"[Coze] 使用缓存的 file_id: {file_id}")
                return file_id

        try:
            image_bytes = await MediaResolver(
                image_url,
                media_type="image",
            ).to_bytes()
            file_id = await self.api_client.upload_file(image_bytes)

            if session_id:
                self.file_id_cache[session_id][cache_key] = file_id
                logger.debug(f"[Coze] 图片上传成功并缓存，file_id: {file_id}")

            return file_id

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("处理图片失败 %s: %s", describe_media_ref(image_url), e)
            raise Exception(f"处理图片失败: {e!s}") from e

    @override
    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    @override
    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
