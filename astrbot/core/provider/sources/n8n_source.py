from collections.abc import AsyncGenerator

import astrbot.core.message.components as Comp
from astrbot.core import logger, sp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.n8n_api_client import N8nAPIClient

from .. import Provider
from ..entities import LLMResponse
from ..register import register_provider_adapter


@register_provider_adapter("n8n", "n8n 工作流适配器。")
class ProviderN8n(Provider):
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
        self.webhook_url = provider_config.get("n8n_webhook_url", "")
        if not self.webhook_url:
            raise Exception("n8n Webhook URL 不能为空。")

        self.auth_header = provider_config.get("n8n_auth_header", "")
        self.auth_value = provider_config.get("n8n_auth_value", "")
        self.http_method = provider_config.get("n8n_http_method", "POST").upper()
        if self.http_method not in ["GET", "POST"]:
            raise Exception("n8n HTTP 方法必须是 GET 或 POST。")

        self.model_name = "n8n"
        self.output_key = provider_config.get("n8n_output_key", "output")
        self.input_key = provider_config.get("n8n_input_key", "input")
        self.session_id_key = provider_config.get("n8n_session_id_key", "sessionId")
        self.image_urls_key = provider_config.get("n8n_image_urls_key", "imageUrls")

        self.streaming = provider_config.get("n8n_streaming", False)
        if isinstance(self.streaming, str):
            self.streaming = self.streaming.lower() in ["true", "1", "yes"]

        self.variables: dict = provider_config.get("variables", {})
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)

        self.api_client = N8nAPIClient(
            webhook_url=self.webhook_url,
            auth_header=self.auth_header if self.auth_header else None,
            auth_value=self.auth_value if self.auth_value else None,
        )

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
        if image_urls is None:
            image_urls = []

        session_id = session_id or kwargs.get("user") or "unknown"

        # Build the payload
        payload = self.variables.copy()

        # Add session variables
        session_var = await sp.session_get(session_id, "session_variables", default={})
        payload.update(session_var)

        # Add the main input
        payload[self.input_key] = prompt

        # Add session ID
        payload[self.session_id_key] = session_id

        # Add system prompt if provided
        if system_prompt:
            payload["system_prompt"] = system_prompt

        # Add image URLs if provided
        if image_urls:
            payload[self.image_urls_key] = image_urls

        try:
            if self.streaming:
                # Use streaming execution
                result_text = ""
                async for chunk in self.api_client.execute_workflow(
                    data=payload,
                    method=self.http_method,
                    streaming=True,
                    timeout=self.timeout,
                ):
                    logger.debug(f"n8n streaming chunk: {chunk}")
                    if isinstance(chunk, dict):
                        # Try to extract text from various possible keys
                        text = (
                            chunk.get("output", "")
                            or chunk.get("text", "")
                            or chunk.get("data", "")
                        )
                        if text:
                            result_text += str(text)
                    else:
                        result_text += str(chunk)

                result = {"output": result_text}
            else:
                # Non-streaming execution
                result = await self.api_client.execute_workflow(
                    data=payload,
                    method=self.http_method,
                    streaming=False,
                    timeout=self.timeout,
                )
                logger.debug(f"n8n response: {result}")

        except Exception as e:
            logger.error(f"n8n 请求失败：{e!s}")
            return LLMResponse(role="err", completion_text=f"n8n 请求失败：{e!s}")

        if not result:
            logger.warning("n8n 请求结果为空，请查看 Debug 日志。")
            return LLMResponse(role="assistant", completion_text="")

        chain = await self.parse_n8n_result(result)
        return LLMResponse(role="assistant", result_chain=chain)

    async def text_chat_stream(
        self,
        prompt,
        session_id=None,
        image_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        if not self.streaming:
            # Simulate streaming by calling text_chat
            llm_response = await self.text_chat(
                prompt=prompt,
                session_id=session_id,
                image_urls=image_urls,
                func_tool=func_tool,
                contexts=contexts,
                system_prompt=system_prompt,
                tool_calls_result=tool_calls_result,
                model=model,
                **kwargs,
            )
            llm_response.is_chunk = True
            yield llm_response
            llm_response.is_chunk = False
            yield llm_response
        else:
            # True streaming
            if image_urls is None:
                image_urls = []

            session_id = session_id or kwargs.get("user") or "unknown"

            # Build the payload
            payload = self.variables.copy()
            session_var = await sp.session_get(
                session_id,
                "session_variables",
                default={},
            )
            payload.update(session_var)
            payload[self.input_key] = prompt
            payload[self.session_id_key] = session_id

            if system_prompt:
                payload["system_prompt"] = system_prompt
            if image_urls:
                payload[self.image_urls_key] = image_urls

            try:
                accumulated_text = ""
                async for chunk in self.api_client.execute_workflow(
                    data=payload,
                    method=self.http_method,
                    streaming=True,
                    timeout=self.timeout,
                ):
                    logger.debug(f"n8n streaming chunk: {chunk}")
                    if isinstance(chunk, dict):
                        text = (
                            chunk.get("output", "")
                            or chunk.get("text", "")
                            or chunk.get("data", "")
                        )
                        if text:
                            accumulated_text += str(text)
                            yield LLMResponse(
                                role="assistant",
                                completion_text=str(text),
                                is_chunk=True,
                            )
                    else:
                        accumulated_text += str(chunk)
                        yield LLMResponse(
                            role="assistant",
                            completion_text=str(chunk),
                            is_chunk=True,
                        )

                # Send final response
                if accumulated_text:
                    chain = MessageChain(chain=[Comp.Plain(accumulated_text)])
                    yield LLMResponse(
                        role="assistant",
                        result_chain=chain,
                        is_chunk=False,
                    )

            except Exception as e:
                logger.error(f"n8n 流式请求失败：{e!s}")
                yield LLMResponse(
                    role="err",
                    completion_text=f"n8n 流式请求失败：{e!s}",
                    is_chunk=False,
                )

    async def parse_n8n_result(self, result: dict | str) -> MessageChain:
        """Parse n8n workflow result into MessageChain"""
        if isinstance(result, str):
            return MessageChain(chain=[Comp.Plain(result)])

        # Extract output from result
        output = result.get(self.output_key)
        if output is None:
            # Try common alternative keys
            output = (
                result.get("data")
                or result.get("result")
                or result.get("response")
                or result.get("text")
            )

        if output is None:
            # If still no output, use the entire result
            output = result

        chains = []

        if isinstance(output, str):
            # Simple text output
            chains.append(Comp.Plain(output))
        elif isinstance(output, list):
            # Handle array output
            for item in output:
                if isinstance(item, dict):
                    # Check if it's a file/media object
                    if "type" in item:
                        comp = await self._parse_media_item(item)
                        if comp:
                            chains.append(comp)
                        else:
                            chains.append(Comp.Plain(str(item)))
                    else:
                        chains.append(Comp.Plain(str(item)))
                else:
                    chains.append(Comp.Plain(str(item)))
        elif isinstance(output, dict):
            # Handle object output
            # Check if it's a media object
            if "type" in output:
                comp = await self._parse_media_item(output)
                if comp:
                    chains.append(comp)
                else:
                    chains.append(Comp.Plain(str(output)))
            else:
                chains.append(Comp.Plain(str(output)))
        else:
            chains.append(Comp.Plain(str(output)))

        if not chains:
            chains.append(Comp.Plain(""))

        return MessageChain(chain=chains)

    async def _parse_media_item(self, item: dict):
        """Parse media item from n8n response"""
        item_type = item.get("type", "").lower()
        url = item.get("url") or item.get("file_url") or item.get("path")

        if not url:
            return None

        match item_type:
            case "image":
                return Comp.Image(file=url, url=url)
            case "audio":
                # Download audio file if needed
                return Comp.File(name=item.get("name", "audio"), file=url)
            case "video":
                return Comp.Video(file=url)
            case "file":
                return Comp.File(name=item.get("name", "file"), file=url)
            case _:
                return None

    async def forget(self, session_id):
        """Clear session context (n8n is stateless, so this is a no-op)"""
        return True

    async def get_current_key(self):
        """Get current API key/auth value"""
        return self.auth_value or ""

    async def set_key(self, key):
        """Set API key/auth value"""
        raise Exception("n8n 适配器不支持设置 API Key。")

    async def get_models(self):
        """Get available models"""
        return [self.get_model()]

    async def get_human_readable_context(self, session_id, page, page_size):
        """Get human-readable context (not supported for n8n)"""
        raise Exception("暂不支持获得 n8n 的历史消息记录。")

    async def terminate(self):
        """Clean up resources"""
        await self.api_client.close()
