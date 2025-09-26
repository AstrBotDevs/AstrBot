import aiohttp
import asyncio
import json
import os
import base64
import hashlib
from typing import AsyncGenerator, Dict
from astrbot.core.message.message_event_result import MessageChain
import astrbot.core.message.components as Comp
from astrbot.api.provider import Provider
from astrbot import logger
from astrbot.core.provider.entities import LLMResponse
from ..register import register_provider_adapter


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
            ("http://", "https://")
        ):
            raise Exception(
                "Coze API Base URL 格式不正确，必须以 http:// 或 https:// 开头。"
            )

        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)
        self.auto_save_history = provider_config.get("auto_save_history", True)
        self.conversation_ids: Dict[str, str] = {}
        self.session = None
        self.file_id_cache: Dict[str, Dict[str, str]] = {}

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
            else:
                if data.startswith(("http://", "https://")):
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
                    else:
                        cache_key = hashlib.md5(clean_path.encode("utf-8")).hexdigest()
                        return cache_key

        except Exception as e:
            cache_key = hashlib.md5(data.encode("utf-8")).hexdigest()
            logger.debug(f"[Coze] 异常文件缓存键: {cache_key}, error={e}")
            return cache_key

    async def _upload_file(
        self,
        file_data: bytes,
        file_name: str = "image.jpg",
        session_id: str = None,
        cache_key: str = None,
    ) -> str:
        """上传文件到 Coze 并返回 file_id

        Args:
            file_data (bytes): 文件的二进制数据
            file_name (str): 文件名，包含扩展名(例如 image.jpg)
            session_id (str): 会话ID，用于缓存
            cache_key (str): 缓存键
        Returns:
            str: 上传成功后返回的 file_id
        """
        # 检查缓存
        if session_id and cache_key:
            if session_id not in self.file_id_cache:
                self.file_id_cache[session_id] = {}

            if cache_key in self.file_id_cache[session_id]:
                file_id = self.file_id_cache[session_id][cache_key]
                return file_id

        session = await self._ensure_session()
        url = f"{self.api_base}/v1/files/upload"

        file_ext = file_name.lower().split(".")[-1] if "." in file_name else "jpg"
        content_type_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "webp": "image/webp",
        }
        content_type = content_type_map.get(file_ext, "image/jpeg")

        form_data = aiohttp.FormData()
        form_data.add_field(
            "file", file_data, filename=file_name, content_type=content_type
        )
        form_data.add_field("purpose", "assistant")

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}

            async with session.post(
                url,
                data=form_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status == 401:
                    raise Exception("Coze API 认证失败，请检查 API Key 是否正确")

                response_text = await response.text()
                logger.debug(
                    f"文件上传响应状态: {response.status}, 内容: {response_text}"
                )

                if response.status != 200:
                    raise Exception(
                        f"文件上传失败，状态码: {response.status}, 响应: {response_text}"
                    )

                try:
                    result = await response.json()
                except json.JSONDecodeError:
                    raise Exception(f"文件上传响应解析失败: {response_text}")

                if result.get("code") != 0:
                    raise Exception(f"文件上传失败: {result.get('msg', '未知错误')}")

                file_id = result["data"]["id"]
                # 缓存 file_id
                if session_id and cache_key:
                    self.file_id_cache[session_id][cache_key] = file_id
                    logger.debug(f"[Coze] 图片上传成功并缓存，file_id: {file_id}")

                return file_id

        except asyncio.TimeoutError:
            logger.error("文件上传超时")
            raise Exception("文件上传超时")
        except Exception as e:
            logger.error(f"文件上传失败: {str(e)}")
            raise Exception(f"文件上传失败: {str(e)}")

    async def _download_and_upload_image(
        self, image_url: str, session_id: str = None
    ) -> str:
        """下载图片并上传到 Coze，返回 file_id

        Args:
            image_url (str): 图片的URL
            session_id (str): 会话ID，用于缓存
        Returns:
            str: 上传成功后返回的 file_id
        """
        # 计算哈希实现缓存
        cache_key = self._generate_cache_key(image_url) if session_id else None

        if session_id and cache_key:
            if session_id not in self.file_id_cache:
                self.file_id_cache[session_id] = {}

            if cache_key in self.file_id_cache[session_id]:
                file_id = self.file_id_cache[session_id][cache_key]
                return file_id

        session = await self._ensure_session()

        try:
            async with session.get(image_url) as response:
                if response.status != 200:
                    raise Exception(f"下载图片失败，状态码: {response.status}")

                image_data = await response.read()

                content_type = response.headers.get("content-type", "")
                if "png" in content_type:
                    file_name = "image.png"
                elif "gif" in content_type:
                    file_name = "image.gif"
                else:
                    file_name = "image.jpg"

                file_id = await self._upload_file(
                    image_data, file_name, session_id, cache_key
                )

                if session_id and cache_key:
                    self.file_id_cache[session_id][cache_key] = file_id

                return file_id

        except Exception as e:
            logger.error(f"处理图片失败 {image_url}: {str(e)}")
            raise Exception(f"处理图片失败: {str(e)}")

    async def _process_context_images(self, content: str, session_id: str) -> str:
        """处理上下文中的图片内容，将 base64 图片上传并替换为 file_id"""

        try:
            content_obj = json.loads(content)
            if isinstance(content_obj, list):
                processed_content = []
                if session_id not in self.file_id_cache:
                    self.file_id_cache[session_id] = {}

                for item in content_obj:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            processed_content.append(item)
                        elif item.get("type") == "image_url":
                            # 处理图片逻辑
                            if "file_id" in item:
                                # 已经有 file_id
                                logger.debug(
                                    f"[Coze] 图片已有file_id: {item['file_id']}"
                                )
                                processed_content.append(item)
                            else:
                                # 获取图片数据
                                image_data = ""
                                if "image_url" in item and isinstance(
                                    item["image_url"], dict
                                ):
                                    image_data = item["image_url"].get("url", "")
                                elif "data" in item:
                                    image_data = item.get("data", "")
                                elif "url" in item:
                                    image_data = item.get("url", "")

                                if image_data:
                                    # 计算哈希用于缓存
                                    if image_data.startswith("data:image/"):
                                        cache_key = self._generate_cache_key(
                                            image_data, is_base64=True
                                        )
                                    else:
                                        cache_key = self._generate_cache_key(
                                            image_data, is_base64=False
                                        )

                                    # 检查缓存
                                    if cache_key in self.file_id_cache[session_id]:
                                        file_id = self.file_id_cache[session_id][
                                            cache_key
                                        ]
                                        processed_content.append(
                                            {"type": "image", "file_id": file_id}
                                        )
                                    else:
                                        # 上传图片并缓存
                                        if image_data.startswith("data:image/"):
                                            # base64 处理
                                            header, encoded = image_data.split(",", 1)
                                            image_bytes = base64.b64decode(encoded)
                                            file_name = "image.jpg"
                                            if "png" in header:
                                                file_name = "image.png"
                                            elif "gif" in header:
                                                file_name = "image.gif"
                                            file_id = await self._upload_file(
                                                image_bytes,
                                                file_name,
                                                session_id,
                                                cache_key,
                                            )
                                        elif image_data.startswith(
                                            ("http://", "https://")
                                        ):
                                            # URL 图片
                                            file_id = (
                                                await self._download_and_upload_image(
                                                    image_data, session_id
                                                )
                                            )
                                            # 为URL图片也添加缓存
                                            self.file_id_cache[session_id][
                                                cache_key
                                            ] = file_id
                                        elif os.path.exists(image_data):
                                            # 本地文件
                                            with open(image_data, "rb") as f:
                                                image_bytes = f.read()
                                            file_name = os.path.basename(image_data)
                                            file_id = await self._upload_file(
                                                image_bytes,
                                                file_name,
                                                session_id,
                                                cache_key,
                                            )
                                        else:
                                            logger.warning(
                                                f"无法处理的图片格式: {image_data[:50]}..."
                                            )
                                            continue

                                        processed_content.append(
                                            {"type": "image", "file_id": file_id}
                                        )
                                else:
                                    continue
                    else:
                        processed_content.append(item)

                result = json.dumps(processed_content, ensure_ascii=False)
                return result
            else:
                return content
        except json.JSONDecodeError:
            return content
        except Exception as e:
            logger.error(f"处理上下文图片失败: {str(e)}")
            return content

    async def _ensure_session(self):
        """确保HTTP session存在"""
        if self.session is None:
            connector = aiohttp.TCPConnector(
                ssl=False if self.api_base.startswith("http://") else True,
                limit=100,
                limit_per_host=30,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(
                total=self.timeout,
                connect=30,
                sock_read=self.timeout,
            )
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "text/event-stream",
            }
            self.session = aiohttp.ClientSession(
                headers=headers, timeout=timeout, connector=connector
            )
        return self.session

    async def _make_request(self, endpoint: str, payload: dict):
        """发送HTTP请求(非流式), 只用来请求非对话接口"""
        session = await self._ensure_session()
        url = f"{self.api_base}{endpoint}"

        try:
            async with session.post(url, json=payload) as response:
                response_text = await response.text()

                if response.status == 401:
                    raise Exception("Coze API 认证失败，请检查 API Key 是否正确")

                if response.status != 200:
                    raise Exception(f"Coze API 请求失败，状态码: {response.status}")

                try:
                    return json.loads(response_text)
                except json.JSONDecodeError:
                    raise Exception("Coze API 返回非JSON格式")

        except asyncio.TimeoutError:
            raise Exception(f"Coze API 请求超时 ({self.timeout}秒)")
        except aiohttp.ClientError as e:
            raise Exception(f"Coze API 请求失败: {str(e)}")

    async def _make_request_stream(self, endpoint: str, payload: dict):
        """发送HTTP请求（流式）"""
        session = await self._ensure_session()
        url = f"{self.api_base}{endpoint}"

        conversation_id = payload.pop("conversation_id", None)
        params = {}
        if conversation_id:
            params["conversation_id"] = conversation_id

        try:
            async with session.post(url, json=payload, params=params) as response:
                if response.status == 401:
                    raise Exception("Coze API 认证失败，请检查 API Key 是否正确")

                if response.status != 200:
                    raise Exception(f"Coze API 流式请求失败，状态码: {response.status}")

                # SSE
                buffer = ""
                event_type = None
                event_data = None

                async for chunk in response.content:
                    if chunk:
                        buffer += chunk.decode("utf-8", errors="ignore")
                        lines = buffer.split("\n")
                        buffer = lines[-1]

                        for line in lines[:-1]:
                            line = line.strip()

                            if not line:
                                if event_type and event_data:
                                    yield {"event": event_type, "data": event_data}
                                    event_type = None
                                    event_data = None
                            elif line.startswith("event:"):
                                event_type = line[6:].strip()
                            elif line.startswith("data:"):
                                data_str = line[5:].strip()
                                if data_str and data_str != "[DONE]":
                                    try:
                                        event_data = json.loads(data_str)
                                    except json.JSONDecodeError:
                                        event_data = {"content": data_str}

        except asyncio.TimeoutError:
            raise Exception(f"Coze API 流式请求超时 ({self.timeout}秒)")
        except Exception as e:
            raise Exception(f"Coze API 流式请求失败: {str(e)}")

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
        else:
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
                    {"role": "system", "content": system_prompt, "content_type": "text"}
                )

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
                        if isinstance(content, list):
                            content_str = json.dumps(content, ensure_ascii=False)
                        else:
                            content_str = content

                        processed_content = await self._process_context_images(
                            content_str, user_id
                        )
                        additional_messages.append(
                            {
                                "role": ctx["role"],
                                "content": processed_content,
                                "content_type": "object_string",
                            }
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
                            }
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
                                url, user_id
                            )
                        else:
                            # 本地文件或 base64
                            if url.startswith("data:image/"):
                                # base64
                                header, encoded = url.split(",", 1)
                                image_data = base64.b64decode(encoded)
                                file_name = "image.jpg"
                                if "png" in header:
                                    file_name = "image.png"
                                elif "gif" in header:
                                    file_name = "image.gif"
                                cache_key = self._generate_cache_key(
                                    url, is_base64=True
                                )
                                file_id = await self._upload_file(
                                    image_data, file_name, user_id, cache_key
                                )
                            else:
                                # 本地文件
                                if os.path.exists(url):
                                    with open(url, "rb") as f:
                                        image_data = f.read()
                                    file_name = os.path.basename(url)
                                    # 用文件路径和修改时间来缓存
                                    file_stat = os.stat(url)
                                    cache_key = self._generate_cache_key(
                                        f"{url}_{file_stat.st_mtime}_{file_stat.st_size}",
                                        is_base64=False,
                                    )
                                    file_id = await self._upload_file(
                                        image_data, file_name, user_id, cache_key
                                    )
                                else:
                                    logger.warning(f"图片文件不存在: {url}")
                                    continue

                            object_string_content.append(
                                {
                                    "type": "image",
                                    "file_id": file_id,
                                }
                            )
                    except Exception as e:
                        logger.error(f"处理图片失败 {url}: {str(e)}")
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
            else:
                # 纯文本
                if prompt:
                    additional_messages.append(
                        {
                            "role": "user",
                            "content": prompt,
                            "content_type": "text",
                        }
                    )

        payload = {
            "bot_id": self.bot_id,
            "user_id": user_id,
            "stream": True,
            "auto_save_history": self.auto_save_history,
        }

        if additional_messages:
            payload["additional_messages"] = additional_messages

        # 如果有会话 ID 就用
        if conversation_id:
            payload["conversation_id"] = conversation_id

        try:
            accumulated_content = ""
            message_started = False

            async for chunk in self._make_request_stream("/v3/chat", payload):
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
            logger.error(f"Coze 流式请求失败: {str(e)}")
            yield LLMResponse(
                role="err",
                completion_text=f"Coze 流式请求失败: {str(e)}",
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
            payload = {"conversation_id": conversation_id}
            response = await self._make_request(
                "/v3/conversation/message/clear_context", payload
            )

            if "code" in response and response["code"] == 0:
                self.conversation_ids.pop(user_id, None)
                return True
            else:
                logger.warning(f"清空Coze会话上下文失败: {response}")
                return False

        except Exception as e:
            logger.error(f"清空Coze会话失败: {str(e)}")
            return False

    async def get_current_key(self):
        """获取当前API Key"""
        return self.api_key

    async def set_key(self, key: str):
        """设置新的API Key"""
        self.api_key = key
        if self.session:
            await self.session.close()
            self.session = None

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
        self, session_id: str, page: int = 1, page_size: int = 10
    ):
        """获取人类可读的上下文历史"""
        user_id = session_id
        conversation_id = self.conversation_ids.get(user_id)

        if not conversation_id:
            return []

        try:
            session = await self._ensure_session()
            url = f"{self.api_base}/v3/conversation/message/list"
            params = {
                "conversation_id": conversation_id,
                "order": "desc",
                "limit": page_size,
                "offset": (page - 1) * page_size,
            }

            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()

            if data.get("code") != 0:
                logger.warning(f"获取Coze消息历史失败: {data}")
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
            logger.error(f"获取Coze消息历史失败: {str(e)}")
            return []

    async def terminate(self):
        """清理资源"""
        if self.session:
            await self.session.close()
            self.session = None
