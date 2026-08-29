import asyncio
import random
import traceback
from pathlib import Path

from astrbot import logger
from astrbot.core.message.components import Image, Plain, Record, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import (
    describe_media_ref,
    ensure_jpeg,
    ensure_wav,
    file_uri_to_path,
    is_file_uri,
)

from ..context import PipelineContext
from ..stage import Stage


def _split_path_mapping(mapping: str) -> tuple[str, str] | None:
    """Split a ``from:to`` path-mapping entry into its two paths.

    Naive ``str.split(":")`` breaks on Windows drive letters (e.g.
    ``C:\\src:C:\\dst`` yields four parts). This finds the separator colon
    while ignoring colons that belong to a ``X:`` drive prefix.

    Args:
        mapping: A ``from:to`` mapping string.

    Returns:
        The ``(from, to)`` pair, or None when the entry is malformed.
    """

    def _is_drive_colon(text: str, index: int) -> bool:
        # A drive-letter colon sits at position 1 and is preceded by a letter,
        # either at the very start or right after a path separator.
        return (index == 1 or (index >= 2 and text[index - 2] in "/\\")) and text[
            index - 1
        ].isalpha()

    for i, char in enumerate(mapping):
        if char == ":" and not _is_drive_colon(mapping, i):
            return mapping[:i], mapping[i + 1 :]
    return None


class PreProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config

        self.stt_settings: dict = self.config.get("provider_stt_settings", {})
        self.platform_settings: dict = self.config.get("platform_settings", {})

    @staticmethod
    def _track_temp_media(event: AstrMessageEvent, media_path: str) -> None:
        """Track a media file owned by the current event.

        Args:
            event: Message event whose lifecycle owns the temporary file.
            media_path: Local media path to track when it lives under AstrBot temp.
        """

        try:
            path = Path(media_path).resolve()
            temp_dir = Path(get_astrbot_temp_path()).resolve()
            path.relative_to(temp_dir)
        except OSError, ValueError:
            return
        event.track_temporary_local_file(str(path))

    async def _send_pre_ack_emoji(self, event: AstrMessageEvent) -> None:
        """React before processing when the platform configuration allows it."""
        supported = {"telegram", "lark", "discord"}
        platform = event.get_platform_name()
        cfg = (
            self.config.get("platform_specific", {})
            .get(platform, {})
            .get("pre_ack_emoji", {})
        ) or {}
        emojis = cfg.get("emojis") or []
        if not (
            cfg.get("enable", False)
            and platform in supported
            and emojis
            and (
                event.get_extra("should_run_command")
                or event.get_extra("should_run_llm")
            )
        ):
            return
        try:
            await event.react(random.choice(emojis))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("%s 预回应表情发送失败: %s", platform, exc)

    def _apply_path_mappings(self, message_chain: list) -> None:
        """Apply configured local path prefixes to top-level media components."""
        for component in message_chain:
            if not isinstance(component, Record | Image) or not component.url:
                continue
            for mapping in self.platform_settings.get("path_mapping", []):
                split_result = _split_path_mapping(mapping)
                if split_result is None:
                    logger.warning("无效的路径映射配置，已跳过: %s", mapping)
                    continue
                from_, to_ = split_result
                from_ = from_.removesuffix("/")
                to_ = to_.removesuffix("/")
                url = (
                    file_uri_to_path(component.url)
                    if is_file_uri(component.url)
                    else component.url
                )
                if url.startswith(from_):
                    component.url = url.replace(from_, to_, 1)
                    logger.debug("路径映射: %s -> %s", url, component.url)

    async def _normalize_media_component(
        self,
        event: AstrMessageEvent,
        component: Record | Image,
        *,
        is_reply: bool,
    ) -> None:
        """Normalize one media component and retain temporary files for the event."""
        try:
            original_path = await component.convert_to_file_path()
            self._track_temp_media(event, original_path)
            if isinstance(component, Record):
                media_path = await ensure_wav(original_path)
            else:
                media_path = await ensure_jpeg(original_path)
            self._track_temp_media(event, media_path)
            component.file = media_path
            component.path = media_path
            if isinstance(component, Image):
                # Image.convert_to_file_path() prefers url, so keep it aligned.
                component.url = media_path
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            prefix = " in reply chain" if is_reply else ""
            if isinstance(component, Image):
                media_ref = component.url or component.file
                logger.warning(
                    "Image processing%s failed for %s: %s",
                    prefix,
                    describe_media_ref(media_ref),
                    exc,
                )
            else:
                logger.warning("Voice processing%s failed: %s", prefix, exc)

    async def _normalize_media_chain(
        self,
        event: AstrMessageEvent,
        message_chain: list,
        *,
        is_reply: bool,
    ) -> None:
        """Normalize all supported media components in one message component chain."""
        for component in message_chain:
            if isinstance(component, Record | Image):
                await self._normalize_media_component(
                    event,
                    component,
                    is_reply=is_reply,
                )

    async def _stt_record(
        self,
        record_comp: Record,
        stt_provider,
        *,
        is_reply: bool,
    ) -> Plain | None:
        """Transcribe one record component, retrying only unavailable local files."""
        prefix = "引用消息" if is_reply else ""
        try:
            path = await record_comp.convert_to_file_path()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("获取%s语音路径失败: %s", prefix, exc)
            return None

        retry = 5
        for attempt in range(retry):
            try:
                result = await stt_provider.get_text(audio_url=path)
                if result:
                    suffix = "(引用消息)" if is_reply else ""
                    logger.info("语音转文本%s结果: %s", suffix, result)
                    return Plain(result)
                return None
            except FileNotFoundError:
                logger.debug("文件尚未就绪 (%s)，重试 %s/%s", path, attempt + 1, retry)
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(traceback.format_exc())
                suffix = "(引用消息)" if is_reply else ""
                logger.error("语音转文本%s失败: %s", suffix, exc)
                return None
        return None

    async def _transcribe_chain(
        self,
        event: AstrMessageEvent,
        message_chain: list,
        stt_provider,
        *,
        is_reply: bool,
    ) -> None:
        """Replace successfully transcribed records and update text mirrors."""
        for index, component in enumerate(message_chain):
            if not isinstance(component, Record):
                continue
            plain_comp = await self._stt_record(
                component,
                stt_provider,
                is_reply=is_reply,
            )
            if plain_comp is not None:
                message_chain[index] = plain_comp
                event.message_str += plain_comp.text
                event.message_obj.message_str += plain_comp.text

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None:
        """在处理事件之前的预处理"""
        message_chain = event.get_messages()
        await self._send_pre_ack_emoji(event)
        self._apply_path_mappings(message_chain)
        await self._normalize_media_chain(event, message_chain, is_reply=False)
        for component in message_chain:
            if isinstance(component, Reply) and component.chain:
                await self._normalize_media_chain(
                    event,
                    component.chain,
                    is_reply=True,
                )

        # STT
        if self.stt_settings.get("enable", False):
            # TODO: 独立
            ctx = self.ctx.execution_context
            stt_provider = ctx.get_using_stt_provider(event.unified_msg_origin)
            if not stt_provider:
                logger.warning(
                    f"会话 {event.unified_msg_origin} 未配置语音转文本模型。",
                )
                return

            await self._transcribe_chain(
                event,
                message_chain,
                stt_provider,
                is_reply=False,
            )
            for component in message_chain:
                if isinstance(component, Reply) and component.chain:
                    await self._transcribe_chain(
                        event,
                        component.chain,
                        stt_provider,
                        is_reply=True,
                    )
