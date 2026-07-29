import asyncio
import random
import traceback
from collections.abc import AsyncGenerator
from pathlib import Path

from astrbot.core import logger
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
from ..stage import Stage, register_stage


@register_stage
class PreProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        self.plugin_manager = ctx.plugin_manager

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
        except (OSError, ValueError):
            return
        event.track_temporary_local_file(str(path))

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        """在处理事件之前的预处理"""
        # 平台特异配置：platform_specific.<platform>.pre_ack_emoji
        supported = {"telegram", "lark", "discord"}
        platform = event.get_platform_name()
        cfg = (
            self.config.get("platform_specific", {})
            .get(platform, {})
            .get("pre_ack_emoji", {})
        ) or {}
        emojis = cfg.get("emojis") or []
        if (
            cfg.get("enable", False)
            and platform in supported
            and emojis
            and event.is_at_or_wake_command
        ):
            try:
                await event.react(random.choice(emojis))
            except Exception as e:
                logger.warning(
                    f"Failed to send a pre-response reaction on {platform}: {e}"
                )

        # 路径映射
        if mappings := self.platform_settings.get("path_mapping", []):
            # 支持 Record，Image 消息段的路径映射。
            message_chain = event.get_messages()

            for idx, component in enumerate(message_chain):
                if isinstance(component, Record | Image) and component.url:
                    for mapping in mappings:
                        from_, to_ = mapping.split(":")
                        from_ = from_.removesuffix("/")
                        to_ = to_.removesuffix("/")

                        url = (
                            file_uri_to_path(component.url)
                            if is_file_uri(component.url)
                            else component.url
                        )
                        if url.startswith(from_):
                            component.url = url.replace(from_, to_, 1)
                            logger.debug(f"Path mapping: {url} -> {component.url}")
                    message_chain[idx] = component

        # Normalize provider-facing media early so downstream code sees local files.
        message_chain = event.get_messages()
        for idx, component in enumerate(message_chain):
            if isinstance(component, Record):
                try:
                    original_path = await component.convert_to_file_path()
                    self._track_temp_media(event, original_path)
                    record_path = await ensure_wav(original_path)
                    self._track_temp_media(event, record_path)
                    component.file = record_path
                    component.path = record_path
                    message_chain[idx] = component
                except Exception as e:
                    logger.warning(f"Voice processing failed: {e}")
            elif isinstance(component, Image):
                try:
                    original_path = await component.convert_to_file_path()
                    self._track_temp_media(event, original_path)
                    image_path = await ensure_jpeg(original_path)
                    self._track_temp_media(event, image_path)
                    component.file = image_path
                    component.path = image_path
                    # Image.convert_to_file_path() prefers url, so keep it aligned.
                    component.url = image_path
                    message_chain[idx] = component
                except Exception as e:
                    media_ref = component.url or component.file
                    logger.warning(
                        "Image processing failed for %s: %s",
                        describe_media_ref(media_ref),
                        e,
                    )

        # Also normalize media components inside Reply chains.
        for component in event.get_messages():
            if isinstance(component, Reply) and component.chain:
                for idx, reply_comp in enumerate(component.chain):
                    if isinstance(reply_comp, Record):
                        try:
                            original_path = await reply_comp.convert_to_file_path()
                            self._track_temp_media(event, original_path)
                            record_path = await ensure_wav(original_path)
                            self._track_temp_media(event, record_path)
                            reply_comp.file = record_path
                            reply_comp.path = record_path
                            component.chain[idx] = reply_comp
                        except Exception as e:
                            logger.warning(
                                f"Voice processing in reply chain failed: {e}"
                            )
                    elif isinstance(reply_comp, Image):
                        try:
                            original_path = await reply_comp.convert_to_file_path()
                            self._track_temp_media(event, original_path)
                            image_path = await ensure_jpeg(original_path)
                            self._track_temp_media(event, image_path)
                            reply_comp.file = image_path
                            reply_comp.path = image_path
                            # Image.convert_to_file_path() prefers url, so keep it aligned.
                            reply_comp.url = image_path
                            component.chain[idx] = reply_comp
                        except Exception as e:
                            media_ref = reply_comp.url or reply_comp.file
                            logger.warning(
                                "Image processing in reply chain failed for %s: %s",
                                describe_media_ref(media_ref),
                                e,
                            )

        # STT
        if self.stt_settings.get("enable", False):
            # TODO: 独立
            ctx = self.plugin_manager.context
            stt_provider = ctx.get_using_stt_provider(event.unified_msg_origin)
            if not stt_provider:
                logger.warning(
                    f"Session {event.unified_msg_origin} has no speech-to-text "
                    "provider configured.",
                )
                return

            async def _stt_record(record_comp: Record, is_reply: bool = False):
                """对单个 Record 组件执行语音转文本，成功返回 Plain，失败返回 None。"""
                prefix = "referenced " if is_reply else ""
                try:
                    path = await record_comp.convert_to_file_path()
                except Exception as e:
                    logger.warning(f"Failed to resolve the {prefix}voice path: {e}")
                    return None

                retry = 5
                for i in range(retry):
                    try:
                        result = await stt_provider.get_text(audio_url=path)
                        if result:
                            suffix = " (referenced message)" if is_reply else ""
                            logger.info(f"Speech-to-text{suffix} result: " + result)
                            return Plain(result)
                        break
                    except FileNotFoundError:
                        # napcat workaround: file may not be ready immediately
                        logger.debug(
                            f"File is not ready ({path}); retrying {i + 1}/{retry}."
                        )
                        await asyncio.sleep(0.5)
                        continue
                    except BaseException as e:
                        logger.error(traceback.format_exc())
                        suffix = " (referenced message)" if is_reply else ""
                        logger.error(f"Speech-to-text{suffix} failed: {e}")
                        break
                return None

            message_chain = event.get_messages()
            for idx, component in enumerate(message_chain):
                if isinstance(component, Record):
                    plain_comp = await _stt_record(component)
                    if plain_comp:
                        message_chain[idx] = plain_comp
                        event.message_str += plain_comp.text
                        event.message_obj.message_str += plain_comp.text

            # Also STT for Record components inside Reply chains
            for component in event.get_messages():
                if isinstance(component, Reply) and component.chain:
                    for idx, reply_comp in enumerate(component.chain):
                        if isinstance(reply_comp, Record):
                            plain_comp = await _stt_record(reply_comp, is_reply=True)
                            if plain_comp:
                                component.chain[idx] = plain_comp
                                event.message_str += plain_comp.text
                                event.message_obj.message_str += plain_comp.text
