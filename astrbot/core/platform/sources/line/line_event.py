import asyncio
import os
import re
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    At,
    BaseMessageComponent,
    File,
    Image,
    Plain,
    Record,
    Video,
)
from astrbot.core.agent.stop_policy import AgentOutputStopped, event_requests_agent_stop
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import get_media_duration

from .line_api import LineAPIClient


class LineMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        line_api: LineAPIClient,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.line_api = line_api

    @staticmethod
    async def _component_to_message_object(
        segment: BaseMessageComponent,
        stop_event: AstrMessageEvent | None = None,
    ) -> dict | None:
        if event_requests_agent_stop(stop_event):
            raise AgentOutputStopped
        if isinstance(segment, Plain):
            text = segment.text.strip()
            if not text:
                return None
            return {"type": "text", "text": text[:5000]}

        if isinstance(segment, At):
            name = str(segment.name or segment.qq or "").strip()
            if not name:
                return None
            return {"type": "text", "text": f"@{name}"[:5000]}

        if isinstance(segment, Image):
            image_url = await LineMessageEvent._resolve_image_url(segment, stop_event)
            if not image_url:
                return None
            return {
                "type": "image",
                "originalContentUrl": image_url,
                "previewImageUrl": image_url,
            }

        if isinstance(segment, Record):
            audio_url = await LineMessageEvent._resolve_record_url(segment, stop_event)
            if not audio_url:
                return None
            duration = await LineMessageEvent._resolve_record_duration(
                segment,
                stop_event,
            )
            return {
                "type": "audio",
                "originalContentUrl": audio_url,
                "duration": duration,
            }

        if isinstance(segment, Video):
            video_url = await LineMessageEvent._resolve_video_url(segment, stop_event)
            if not video_url:
                return None
            preview_url = await LineMessageEvent._resolve_video_preview_url(
                segment,
                stop_event,
            )
            if not preview_url:
                return None
            return {
                "type": "video",
                "originalContentUrl": video_url,
                "previewImageUrl": preview_url,
            }

        if isinstance(segment, File):
            file_url = await LineMessageEvent._resolve_file_url(segment, stop_event)
            if not file_url:
                return None
            file_name = str(segment.name or "").strip() or "file.bin"
            file_size = await LineMessageEvent._resolve_file_size(segment, stop_event)
            if file_size <= 0:
                return None
            return {
                "type": "file",
                "fileName": file_name,
                "fileSize": file_size,
                "originalContentUrl": file_url,
            }

        return None

    @staticmethod
    async def _resolve_image_url(
        segment: Image,
        stop_event: AstrMessageEvent | None = None,
    ) -> str:
        candidate = (segment.url or segment.file or "").strip()
        if candidate.startswith("https://"):
            return candidate
        try:
            result = await segment.register_to_file_service()
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            return result
        except AgentOutputStopped:
            raise
        except Exception as e:
            logger.debug("[LINE] resolve image url failed: %s", e)
            return ""

    @staticmethod
    async def _resolve_record_url(
        segment: Record,
        stop_event: AstrMessageEvent | None = None,
    ) -> str:
        candidate = (segment.url or segment.file or "").strip()
        if candidate.startswith("https://"):
            return candidate
        try:
            result = await segment.register_to_file_service()
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            return result
        except AgentOutputStopped:
            raise
        except Exception as e:
            logger.debug("[LINE] resolve record url failed: %s", e)
            return ""

    @staticmethod
    async def _resolve_record_duration(
        segment: Record,
        stop_event: AstrMessageEvent | None = None,
    ) -> int:
        try:
            file_path = await segment.convert_to_file_path()
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            duration_ms = await get_media_duration(file_path)
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            if isinstance(duration_ms, int) and duration_ms > 0:
                return duration_ms
        except AgentOutputStopped:
            raise
        except Exception as e:
            logger.debug("[LINE] resolve record duration failed: %s", e)
        return 1000

    @staticmethod
    async def _resolve_video_url(
        segment: Video,
        stop_event: AstrMessageEvent | None = None,
    ) -> str:
        candidate = (segment.file or "").strip()
        if candidate.startswith("https://"):
            return candidate
        try:
            result = await segment.register_to_file_service()
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            return result
        except AgentOutputStopped:
            raise
        except Exception as e:
            logger.debug("[LINE] resolve video url failed: %s", e)
            return ""

    @staticmethod
    async def _resolve_video_preview_url(
        segment: Video,
        stop_event: AstrMessageEvent | None = None,
    ) -> str:
        cover_candidate = (segment.cover or "").strip()
        if cover_candidate.startswith("https://"):
            return cover_candidate

        if cover_candidate:
            try:
                cover_seg = Image(file=cover_candidate)
                result = await cover_seg.register_to_file_service()
                if event_requests_agent_stop(stop_event):
                    raise AgentOutputStopped
                return result
            except AgentOutputStopped:
                raise
            except Exception as e:
                logger.debug("[LINE] resolve video cover failed: %s", e)

        try:
            video_path = await segment.convert_to_file_path()
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            temp_dir = Path(get_astrbot_temp_path())
            temp_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = temp_dir / f"line_video_preview_{uuid.uuid4().hex}.jpg"
            if stop_event is not None:
                stop_event.track_temporary_local_file(str(thumb_path))

            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped

            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",
                "-ss",
                "00:00:01",
                "-i",
                video_path,
                "-frames:v",
                "1",
                str(thumb_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            if process.returncode != 0 or not thumb_path.exists():
                return ""

            cover_seg = Image.fromFileSystem(str(thumb_path))
            result = await cover_seg.register_to_file_service()
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            return result
        except AgentOutputStopped:
            raise
        except Exception as e:
            logger.debug("[LINE] generate video preview failed: %s", e)
            return ""

    @staticmethod
    async def _resolve_file_url(
        segment: File,
        stop_event: AstrMessageEvent | None = None,
    ) -> str:
        if segment.url and segment.url.startswith("https://"):
            return segment.url
        try:
            result = await segment.register_to_file_service()
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            return result
        except AgentOutputStopped:
            raise
        except Exception as e:
            logger.debug("[LINE] resolve file url failed: %s", e)
            return ""

    @staticmethod
    async def _resolve_file_size(
        segment: File,
        stop_event: AstrMessageEvent | None = None,
    ) -> int:
        try:
            file_path = await segment.get_file(allow_return_url=False)
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            if file_path and os.path.exists(file_path):
                return int(os.path.getsize(file_path))
        except AgentOutputStopped:
            raise
        except Exception as e:
            logger.debug("[LINE] resolve file size failed: %s", e)
        return 0

    @classmethod
    async def build_line_messages(
        cls,
        message_chain: MessageChain,
        stop_event: AstrMessageEvent | None = None,
    ) -> list[dict]:
        messages: list[dict] = []
        for segment in message_chain.chain:
            if event_requests_agent_stop(stop_event):
                raise AgentOutputStopped
            obj = await cls._component_to_message_object(segment, stop_event)
            if obj:
                messages.append(obj)

        if not messages:
            return []

        if len(messages) > 5:
            logger.warning(
                "[LINE] message count exceeds 5, extra segments will be dropped."
            )
            messages = messages[:5]
        return messages

    async def send(self, message: MessageChain) -> None:
        if event_requests_agent_stop(self):
            raise AgentOutputStopped
        messages = await self.build_line_messages(message, self)
        if not messages:
            raise RuntimeError(
                "LINE message conversion produced no deliverable content."
            )

        raw = self.message_obj.raw_message
        reply_token = ""
        if isinstance(raw, dict):
            reply_token = str(raw.get("replyToken") or "")

        sent = False
        if reply_token:
            sent = await self.line_api.reply_message(reply_token, messages)

        if not sent:
            if event_requests_agent_stop(self):
                raise AgentOutputStopped
            target_id = self.get_group_id() or self.get_sender_id()
            if target_id:
                sent = await self.line_api.push_message(target_id, messages)
        if not sent:
            raise RuntimeError("LINE message delivery failed.")

        await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ):
        if not use_fallback:
            buffer = None
            async for chain in generator:
                if event_requests_agent_stop(self):
                    raise AgentOutputStopped
                if not buffer:
                    buffer = chain
                else:
                    buffer.chain.extend(chain.chain)
            if not buffer:
                return None
            buffer.squash_plain()
            await self.send(buffer)
            return await super().send_streaming(generator, use_fallback)

        buffer = ""
        pattern = re.compile(r"[^。？！~…]+[。？！~…]+")

        async for chain in generator:
            if event_requests_agent_stop(self):
                raise AgentOutputStopped
            if isinstance(chain, MessageChain):
                for comp in chain.chain:
                    if event_requests_agent_stop(self):
                        raise AgentOutputStopped
                    if isinstance(comp, Plain):
                        buffer += comp.text
                        if any(p in buffer for p in "。？！~…"):
                            buffer = await self.process_buffer(buffer, pattern)
                    else:
                        await self.send_streaming_fallback_component(comp)

        if buffer.strip():
            await self.send(MessageChain([Plain(buffer)]))
        return await super().send_streaming(generator, use_fallback)
