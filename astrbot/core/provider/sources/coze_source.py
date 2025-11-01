import base64
import hashlib
import json
import os
from collections.abc import AsyncGenerator

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.api.provider import Provider
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse

from ..register import register_provider_adapter
from .coze_api_client import CozeAPIClient


@register_provider_adapter("coze", "Coze (扣子) 智能体适配器")
class ProviderCoze(Provider):
    def __init__(
        self,
        provider_config,
        provider_settings,
        default_persona=None,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
            default_persona,
        )
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
        self.conversation_ids: dict[str, str] = {}
        self.file_id_cache: dict[str, dict[str, str]] = {}

        # 创建 API 客户端
        self.api_client = CozeAPIClient(api_key=self.api_key, api_base=self.api_base)

    def _generate_cache_key(self, data: str, is_base64: bool = False) -> str:
        """生成统一的缓存键

        Args:
            data: 图片数据或路径
            is_base64: 是否是 base64 数据

        Returns:
            str: 缓存键

        """
        try:
            if is_base64 and data.startswith("data:image/"):
                try:
                    header, encoded = data.split(",", 1)
                    image_bytes = base64.b64decode(encoded)
                    cache_key = hashlib.md5(image_bytes).hexdigest()
                    return cache_key
                except Exception:
                    cache_key = hashlib.md5(encoded.encode("utf-8")).hexdigest()
                    return cache_key
            elif data.startswith(("http://", "https://")):
                # URL图片，使用URL作为缓存键
                cache_key = hashlib.md5(data.encode("utf-8")).hexdigest()
                return cache_key
            else:
                clean_path = (
                    data.split("_")[0]
                    if "_" in data and len(data.split("_")) >= 3
                    else data
                )

                if os.path.exists(clean_path):
                    with open(clean_path, "rb") as f:
                        file_content = f.read()
                    cache_key = hashlib.md5(file_content).hexdigest()
                    return cache_key
                cache_key = hashlib.md5(clean_path.encode("utf-8")).hexdigest()
                return cache_key

        except Exception as e:
            cache_key = hashlib.md5(data.encode("utf-8")).hexdigest()
            logger.debug(f"[Coze] 异常文件缓存键: {cache_key}, error={e}")
            return cache_key

    async def _upload_file(
        self,
        file_data: bytes,
        session_id: str | None = None,
        cache_key: str | None = None,
    ) -> str:
        """上传文件到 Coze 并返回 file_id"""
        # 使用 API 客户端上传文件
        file_id = await self.api_client.upload_file(file_data)

        # 缓存 file_id
        if session_id and cache_key:
            if session_id not in self.file_id_cache:
                self.file_id_cache[session_id] = {}
            self.file_id_cache[session_id][cache_key] = file_id
            logger.debug(f"[Coze] 图片上传成功并缓存，file_id: {file_id}")

        return file_id

    async def _download_and_upload_image(
        self,
        image_url: str,
        session_id: str | None = None,
    ) -> str:
        """下载图片并上传到 Coze，返回 file_id"""
        # 计算哈希实现缓存
        cache_key = self._generate_cache_key(image_url) if session_id else None

        if session_id and cache_key:
            if session_id not in self.file_id_cache:
                self.file_id_cache[session_id] = {}

            if cache_key in self.file_id_cache[session_id]:
                file_id = self.file_id_cache[session_id][cache_key]
                return file_id

        try:
            image_data = await self.api_client.download_image(image_url)

            file_id = await self._upload_file(image_data, session_id, cache_key)

            if session_id and cache_key:
                self.file_id_cache[session_id][cache_key] = file_id

            return file_id

        except Exception as e:
            logger.error(f"处理图片失败 {image_url}: {e!s}")
            raise Exception(f"处理图片失败: {e!s}")

    async def _process_context_images(
        self,
        content: str | list,
        session_id: str,
    ) -> str:
        """处理上下文中的图片内容，将 base64 图片上传并替换为 file_id"""
        try:
            if isinstance(content, str):
                return content

            processed_content = []
            if session_id not in self.file_id_cache:
                self.file_id_cache[session_id] = {}

            for item in content:
                if not isinstance(item, dict):
                    processed_content.append(item)
                    continue
                if item.get("type") == "text":
                    processed_content.append(item)
                elif item.get("type") == "image_url":
                    # 处理图片逻辑
                    if "file_id" in item:
                        # 已经有 file_id
                        logger.debug(f"[Coze] 图片已有file_id: {item['file_id']}")
                        processed_content.append(item)
                    else:
                        # 获取图片数据
                        image_data = ""
                        if "image_url" in item and isinstance(item["image_url"], dict):
                            image_data = item["image_url"].get("url", "")
                        elif "data" in item:
                            image_data = item.get("data", "")
                        elif "url" in item:
                            image_data = item.get("url", "")

                        if not image_data:
                            continue
                        # 计算哈希用于缓存
                        cache_key = self._generate_cache_key(
                            image_data,
                            is_base64=image_data.startswith("data:image/"),
                        )

                        # 检查缓存
                        if cache_key in self.file_id_cache[session_id]:
                            file_id = self.file_id_cache[session_id][cache_key]
                            processed_content.append(
                                {"type": "image", "file_id": file_id},
                            )
                        else:
                            # 上传图片并缓存
                            if image_data.startswith("data:image/"):
                                # base64 处理
                                _, encoded = image_data.split(",", 1)
                                image_bytes = base64.b64decode(encoded)
                                file_id = await self._upload_file(
                                    image_bytes,
                                    session_id,
                                    cache_key,
                                )
                            elif image_data.startswith(("http://", "https://")):
                                # URL 图片
                                file_id = await self._download_and_upload_image(
                                    image_data,
                                    session_id,
                                )
                                # 为URL图片也添加缓存
                                self.file_id_cache[session_id][cache_key] = file_id
                            elif os.path.exists(image_data):
                                # 本地文件
                                with open(image_data, "rb") as f:
                                    image_bytes = f.read()
                                file_id = await self._upload_file(
                                    image_bytes,
                                    session_id,
                                    cache_key,
                                )
                            else:
                                logger.warning(
                                    f"无法处理的图片格式: {image_data[:50]}...",
                                )
                                continue

                            processed_content.append(
                                {"type": "image", "file_id": file_id},
                            )

            result = json.dumps(processed_content, ensure_ascii=False)
            return result
        except Exception as e:
            logger.error(f"处理上下文图片失败: {e!s}")
            if isinstance(content, str):
                return content
            return json.dumps(content, ensure_ascii=False)

    async def text_chat(
        self,
        prompt: str,
        session_id=None,
        image_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        **kwargs,
    ) -> LLMResponse:
        """文本对话, 内部使用流式接口实现非流式

        Args:
            prompt (str): 用户提示词
            session_id (str): 会话ID
            image_urls (List[str]): 图片URL列表
            func_tool (FuncCall): 函数调用工具(不支持)
            contexts (List): 上下文列表
            system_prompt (str): 系统提示语
            tool_calls_result (ToolCallsResult | List[ToolCallsResult]): 工具调用结果(不支持)
            model (str): 模型名称(不支持)

        Returns:
            LLMResponse: LLM响应对象

        """
        accumulated_content = ""
        final_response = None

        async for llm_response in self.text_chat_stream(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            func_tool=func_tool,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
            model=model,
            **kwargs,
        ):
            if llm_response.is_chunk:
                if llm_response.completion_text:
                    accumulated_content += llm_response.completion_text
            else:
                final_response = llm_response

        if final_response:
            return final_response

        if accumulated_content:
            chain = MessageChain(chain=[Comp.Plain(accumulated_content)])
            return LLMResponse(role="assistant", result_chain=chain)
        return LLMResponse(role="assistant", completion_text="")

    async def text_chat_stream(
        self,
        prompt: str,
        session_id=None,
        image_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        """流式对话接口"""
        # 用户ID参数(参考文档, 可以自定义)
        user_id = session_id or kwargs.get("user", "default_user")

        # 获取或创建会话ID
        conversation_id = self.conversation_ids.get(user_id)

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

        contexts = self._ensure_message_to_dicts(contexts)
        if not self.auto_save_history and contexts:
            # 如果关闭了自动保存历史，传入上下文
            for ctx in contexts:
                if isinstance(ctx, dict) and "role" in ctx and "content" in ctx:
                    content = ctx["content"]
                    content_type = ctx.get("content_type", "text")

                    # 处理可能包含图片的上下文
                    if (
                        content_type == "object_string"
                        or (isinstance(content, str) and content.startswith("["))
                        or (
                            isinstance(content, list)
                            and any(
                                isinstance(item, dict)
                                and item.get("type") == "image_url"
                                for item in content
                            )
                        )
                    ):
                        processed_content = await self._process_context_images(
                            content,
                            user_id,
                        )
                        additional_messages.append(
                            {
                                "role": ctx["role"],
                                "content": processed_content,
                                "content_type": "object_string",
                            },
                        )
                    else:
                        # 纯文本
                        additional_messages.append(
                            {
                                "role": ctx["role"],
                                "content": (
                                    content
                                    if isinstance(content, str)
                                    else json.dumps(content, ensure_ascii=False)
                                ),
                                "content_type": "text",
                            },
                        )
                else:
                    logger.info(f"[Coze] 跳过格式不正确的上下文: {ctx}")

        if prompt or image_urls:
            if image_urls:
                # 多模态
                object_string_content = []
                if prompt:
                    object_string_content.append({"type": "text", "text": prompt})

                for url in image_urls:
                    try:
                        if url.startswith(("http://", "https://")):
                            # 网络图片
                            file_id = await self._download_and_upload_image(
                                url,
                                user_id,
                            )
                        else:
                            # 本地文件或 base64
                            if url.startswith("data:image/"):
                                # base64
                                _, encoded = url.split(",", 1)
                                image_data = base64.b64decode(encoded)
                                cache_key = self._generate_cache_key(
                                    url,
                                    is_base64=True,
                                )
                                file_id = await self._upload_file(
                                    image_data,
                                    user_id,
                                    cache_key,
                                )
                            # 本地文件
                            elif os.path.exists(url):
                                with open(url, "rb") as f:
                                    image_data = f.read()
                                # 用文件路径和修改时间来缓存
                                file_stat = os.stat(url)
                                cache_key = self._generate_cache_key(
                                    f"{url}_{file_stat.st_mtime}_{file_stat.st_size}",
                                    is_base64=False,
                                )
                                file_id = await self._upload_file(
                                    image_data,
                                    user_id,
                                    cache_key,
                                )
                            else:
                                logger.warning(f"图片文件不存在: {url}")
                                continue

                            object_string_content.append(
                                {
                                    "type": "image",
                                    "file_id": file_id,
                                },
                            )
                    except Exception as e:
                        logger.error(f"处理图片失败 {url}: {e!s}")
                        continue

                if object_string_content:
                    content = json.dumps(object_string_content, ensure_ascii=False)
                    additional_messages.append(
                        {
                            "role": "user",
                            "content": content,
                            "content_type": "object_string",
                        },
                    )
            # 纯文本
            elif prompt:
                additional_messages.append(
                    {
                        "role": "user",
                        "content": prompt,
                        "content_type": "text",
                    },
                )

        try:
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
                        self.conversation_ids[user_id] = data["conversation_id"]

                elif event_type == "conversation.message.delta":
                    if isinstance(data, dict):
                        content = data.get("content", "")
                        if not content and "delta" in data:
                            content = data["delta"].get("content", "")
                        if not content and "text" in data:
                            content = data.get("text", "")

                        if content:
                            message_started = True
                            accumulated_content += content
                            yield LLMResponse(
                                role="assistant",
                                completion_text=content,
                                is_chunk=True,
                            )

                elif event_type == "conversation.message.completed":
                    if isinstance(data, dict):
                        msg_type = data.get("type")
                        if msg_type == "answer" and data.get("role") == "assistant":
                            final_content = data.get("content", "")
                            if not accumulated_content and final_content:
                                chain = MessageChain(chain=[Comp.Plain(final_content)])
                                yield LLMResponse(
                                    role="assistant",
                                    result_chain=chain,
                                    is_chunk=False,
                                )

                elif event_type == "conversation.chat.completed":
                    if accumulated_content:
                        chain = MessageChain(chain=[Comp.Plain(accumulated_content)])
                        yield LLMResponse(
                            role="assistant",
                            result_chain=chain,
                            is_chunk=False,
                        )
                    break

                elif event_type == "done":
                    break

                elif event_type == "error":
                    error_msg = (
                        data.get("message", "未知错误")
                        if isinstance(data, dict)
                        else str(data)
                    )
                    logger.error(f"Coze 流式响应错误: {error_msg}")
                    yield LLMResponse(
                        role="err",
                        completion_text=f"Coze 错误: {error_msg}",
                        is_chunk=False,
                    )
                    break

            if not message_started and not accumulated_content:
                yield LLMResponse(
                    role="assistant",
                    completion_text="LLM 未响应任何内容。",
                    is_chunk=False,
                )
            elif message_started and accumulated_content:
                chain = MessageChain(chain=[Comp.Plain(accumulated_content)])
                yield LLMResponse(
                    role="assistant",
                    result_chain=chain,
                    is_chunk=False,
                )

        except Exception as e:
            logger.error(f"Coze 流式请求失败: {e!s}")
            yield LLMResponse(
                role="err",
                completion_text=f"Coze 流式请求失败: {e!s}",
                is_chunk=False,
            )

    async def forget(self, session_id: str):
        """清空指定会话的上下文"""
        user_id = session_id
        conversation_id = self.conversation_ids.get(user_id)

        if user_id in self.file_id_cache:
            self.file_id_cache.pop(user_id, None)

        if not conversation_id:
            return True

        try:
            response = await self.api_client.clear_context(conversation_id)

            if "code" in response and response["code"] == 0:
                self.conversation_ids.pop(user_id, None)
                return True
            logger.warning(f"清空 Coze 会话上下文失败: {response}")
            return False

        except Exception as e:
            logger.error(f"清空 Coze 会话失败: {e!s}")
            return False

    async def get_current_key(self):
        """获取当前API Key"""
        return self.api_key

    async def set_key(self, key: str):
        """设置新的API Key"""
        raise NotImplementedError("Coze 适配器不支持设置 API Key。")

    async def get_models(self):
        """获取可用模型列表"""
        return [f"bot_{self.bot_id}"]

    def get_model(self):
        """获取当前模型"""
        return f"bot_{self.bot_id}"

    def set_model(self, model: str):
        """设置模型（在Coze中是Bot ID）"""
        if model.startswith("bot_"):
            self.bot_id = model[4:]
        else:
            self.bot_id = model

    async def get_human_readable_context(
        self,
        session_id: str,
        page: int = 1,
        page_size: int = 10,
    ):
        """获取人类可读的上下文历史"""
        user_id = session_id
        conversation_id = self.conversation_ids.get(user_id)

        if not conversation_id:
            return []

        try:
            data = await self.api_client.get_message_list(
                conversation_id=conversation_id,
                order="desc",
                limit=page_size,
                offset=(page - 1) * page_size,
            )

            if data.get("code") != 0:
                logger.warning(f"获取 Coze 消息历史失败: {data}")
                return []

            messages = data.get("data", {}).get("messages", [])

            readable_history = []
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                msg_type = msg.get("type", "")

                if role == "user":
                    readable_history.append(f"用户: {content}")
                elif role == "assistant" and msg_type == "answer":
                    readable_history.append(f"助手: {content}")

            return readable_history

        except Exception as e:
            logger.error(f"获取 Coze 消息历史失败: {e!s}")
            return []

    async def terminate(self):
        """清理资源"""
        await self.api_client.close()
