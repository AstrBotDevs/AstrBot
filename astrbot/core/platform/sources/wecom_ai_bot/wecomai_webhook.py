"""企业微信智能机器人 webhook 推送客户端。"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Video
from astrbot.core.utils.media_utils import convert_audio_format


class WecomAIBotWebhookError(RuntimeError):
    """企业微信 webhook 推送异常。"""


class WecomAIBotWebhookClient:
    """企业微信智能机器人 webhook 消息推送客户端。"""

    def __init__(self, webhook_url: str, timeout_seconds: int = 15) -> None:
        self.webhook_url = webhook_url.strip()
        self.timeout_seconds = timeout_seconds
        if not self.webhook_url:
            raise WecomAIBotWebhookError("消息推送 webhook URL 不能为空")
        self._webhook_key = self._extract_webhook_key()

    def _extract_webhook_key(self) -> str:
        parsed = urlparse(self.webhook_url)
        key = parse_qs(parsed.query).get("key", [""])[0].strip()
        if not key:
            raise WecomAIBotWebhookError("消息推送 webhook URL 缺少 key 参数")
        return key

    def _build_upload_url(self, media_type: Literal["file", "voice"]) -> str:
        query = urlencode({"key": self._webhook_key, "type": media_type})
        return f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?{query}"

    @staticmethod
    def _split_markdown_v2_content(content: str, max_bytes: int = 4096) -> list[str]:
        if not content:
            return []
        chunks: list[str] = []
        buffer: list[str] = []
        current_size = 0
        for char in content:
            char_size = len(char.encode("utf-8"))
            if current_size + char_size > max_bytes and buffer:
                chunks.append("".join(buffer))
                buffer = [char]
                current_size = char_size
            else:
                buffer.append(char)
                current_size += char_size
        if buffer:
            chunks.append("".join(buffer))
        return chunks

    async def send_payload(self, payload: dict[str, Any]) -> None:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.webhook_url, json=payload) as response:
                text = await response.text()
                if response.status != 200:
                    raise WecomAIBotWebhookError(
                        f"Webhook 请求失败: HTTP {response.status}, {text}"
                    )
                result = await response.json(content_type=None)
                if result.get("errcode") != 0:
                    raise WecomAIBotWebhookError(
                        f"Webhook 返回错误: {result.get('errcode')} {result.get('errmsg')}"
                    )
        logger.debug("企业微信消息推送成功: %s", payload.get("msgtype", "unknown"))

    async def send_markdown_v2(self, content: str) -> None:
        for chunk in self._split_markdown_v2_content(content):
            await self.send_payload(
                {
                    "msgtype": "markdown_v2",
                    "markdown_v2": {"content": chunk},
                }
            )

    async def send_image_base64(self, image_base64: str) -> None:
        image_bytes = base64.b64decode(image_base64)
        md5 = hashlib.md5(image_bytes).hexdigest()
        await self.send_payload(
            {
                "msgtype": "image",
                "image": {
                    "base64": image_base64,
                    "md5": md5,
                },
            }
        )

    async def upload_media(
        self, file_path: Path, media_type: Literal["file", "voice"]
    ) -> str:
        if not file_path.exists() or not file_path.is_file():
            raise WecomAIBotWebhookError(f"文件不存在: {file_path}")

        content_type = (
            mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        )
        form = aiohttp.FormData()
        form.add_field(
            "media",
            file_path.read_bytes(),
            filename=file_path.name,
            content_type=content_type,
        )

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                self._build_upload_url(media_type),
                data=form,
            ) as response:
                text = await response.text()
                if response.status != 200:
                    raise WecomAIBotWebhookError(
                        f"上传媒体失败: HTTP {response.status}, {text}"
                    )
                result = await response.json(content_type=None)
                if result.get("errcode") != 0:
                    raise WecomAIBotWebhookError(
                        f"上传媒体失败: {result.get('errcode')} {result.get('errmsg')}"
                    )
                media_id = result.get("media_id", "")
                if not media_id:
                    raise WecomAIBotWebhookError("上传媒体失败: 返回缺少 media_id")
                return str(media_id)

    async def send_file(self, file_path: Path) -> None:
        media_id = await self.upload_media(file_path, "file")
        await self.send_payload(
            {
                "msgtype": "file",
                "file": {"media_id": media_id},
            }
        )

    async def send_voice(self, file_path: Path) -> None:
        media_id = await self.upload_media(file_path, "voice")
        await self.send_payload(
            {
                "msgtype": "voice",
                "voice": {"media_id": media_id},
            }
        )

    @staticmethod
    def is_stream_supported_component(component: Any) -> bool:
        return isinstance(component, Plain | Image | At)

    async def send_message_chain(
        self,
        message_chain: MessageChain,
        unsupported_only: bool = False,
    ) -> None:
        async def flush_markdown_buffer(parts: list[str]) -> None:
            content = "".join(parts).strip()
            parts.clear()
            if content:
                await self.send_markdown_v2(content)

        markdown_buffer: list[str] = []

        for component in message_chain.chain:
            if unsupported_only and self.is_stream_supported_component(component):
                continue
            if isinstance(component, Plain):
                markdown_buffer.append(component.text)
            elif isinstance(component, At):
                mention_name = component.name or str(component.qq)
                markdown_buffer.append(f" @{mention_name} ")
            elif isinstance(component, Image):
                await flush_markdown_buffer(markdown_buffer)
                image_base64 = await component.convert_to_base64()
                await self.send_image_base64(image_base64)
            elif isinstance(component, File):
                await flush_markdown_buffer(markdown_buffer)
                file_path = await component.get_file()
                if not file_path:
                    logger.warning("文件消息缺少有效文件路径，已跳过: %s", component)
                    continue
                await self.send_file(Path(file_path))
            elif isinstance(component, Video):
                await flush_markdown_buffer(markdown_buffer)
                video_path = await component.convert_to_file_path()
                await self.send_file(Path(video_path))
            elif isinstance(component, Record):
                await flush_markdown_buffer(markdown_buffer)
                source_voice_path = Path(await component.convert_to_file_path())
                target_voice_path = source_voice_path
                converted = False
                if source_voice_path.suffix.lower() != ".amr":
                    target_voice_path = Path(
                        await convert_audio_format(str(source_voice_path), "amr"),
                    )
                    converted = target_voice_path != source_voice_path
                try:
                    await self.send_voice(target_voice_path)
                finally:
                    if converted and target_voice_path.exists():
                        try:
                            target_voice_path.unlink()
                        except Exception as e:
                            logger.warning(
                                "清理临时语音文件失败 %s: %s", target_voice_path, e
                            )
            else:
                logger.warning(
                    "企业微信消息推送暂不支持组件类型 %s，已跳过",
                    type(component).__name__,
                )

        await flush_markdown_buffer(markdown_buffer)
