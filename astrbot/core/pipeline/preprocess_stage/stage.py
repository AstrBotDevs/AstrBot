import asyncio
import random
import re
import traceback
from collections.abc import AsyncGenerator
from pathlib import Path

from astrbot.core import logger
from astrbot.core.message.components import (
    File,
    Image,
    Node,
    Nodes,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import (
    describe_media_ref,
    detect_image_mime_type_async,
    ensure_wav,
    file_uri_to_path,
    is_file_uri,
)
from astrbot.core.utils.platform_files import (
    retain_platform_file,
    update_platform_image_path,
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

    @staticmethod
    def _is_existing_local_image_ref(media_ref: str | None) -> bool:
        """Return whether an image reference already points at a local file."""
        if not media_ref:
            return False
        if is_file_uri(media_ref):
            return True
        if media_ref.startswith(("http://", "https://", "data:", "base64://")):
            return False
        try:
            return Path(media_ref).exists()
        except OSError:
            return False

    async def _normalize_image_component(
        self,
        event: AstrMessageEvent,
        component: Image,
    ) -> None:
        """Resolve an image in place while preserving cleanup ownership.

        Args:
            event: Incoming event with its finalized session identity.
            component: Image component to localize in place.
        """
        media_ref = component.url or component.file
        image_path: str | None = None
        materialized = False
        try:
            image_path = await component.convert_to_file_path()
            materialized = (
                not self._is_existing_local_image_ref(media_ref)
                and Path(image_path).is_file()
            )
            if materialized:
                self._track_temp_media(event, image_path)
                detected_mime_type = await detect_image_mime_type_async(
                    image_path,
                    default_mime_type=None,
                )
                if detected_mime_type is None:
                    raise ValueError("image content could not be identified")
        except Exception:
            if image_path and not materialized:
                event.untrack_temporary_local_file(image_path)
            raise

        retained_path = await retain_platform_file(image_path, event.unified_msg_origin)
        update_platform_image_path(component, retained_path, event.get_messages())
        event.untrack_temporary_local_file(retained_path)

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
                        # ":" is ambiguous for Windows absolute paths. Parse
                        # the separator after a drive-lettered source first,
                        # then handle a drive-lettered target.
                        drive_source_mapping = re.fullmatch(
                            r"([A-Za-z]:[^:]+):(.+)", mapping
                        )
                        drive_target_mapping = re.fullmatch(
                            r"(.+):([A-Za-z]:.+)", mapping
                        )
                        if drive_source_mapping:
                            from_, to_ = drive_source_mapping.groups()
                        elif drive_target_mapping:
                            from_, to_ = drive_target_mapping.groups()
                        else:
                            from_, separator, to_ = mapping.partition(":")
                            if not separator:
                                logger.warning(f"Invalid path mapping: {mapping}")
                                continue
                        from_ = from_.removesuffix("/").removesuffix("\\")
                        to_ = to_.removesuffix("/").removesuffix("\\")

                        url = (
                            file_uri_to_path(component.url)
                            if is_file_uri(component.url)
                            else component.url
                        )
                        if url.startswith(from_):
                            component.url = url.replace(from_, to_, 1)
                            logger.debug(f"Path mapping: {url} -> {component.url}")
                    message_chain[idx] = component

        # WakingCheckStage has finalized the UMO before attachments are retained.
        # Traverse quoted and forwarded chains as well as the incoming message.
        pending = list(reversed(event.get_messages()))
        while pending:
            component = pending.pop()
            if isinstance(component, Reply) and component.chain:
                pending.extend(reversed(component.chain))
            elif isinstance(component, Node):
                pending.extend(reversed(component.content))
            elif isinstance(component, Nodes):
                pending.extend(reversed(component.nodes))
            elif isinstance(component, Image):
                try:
                    await self._normalize_image_component(event, component)
                except Exception as exc:
                    logger.warning(
                        "Image processing failed for %s: %s",
                        describe_media_ref(component.url or component.file),
                        exc,
                    )
            elif isinstance(component, Record):
                try:
                    original_path = await component.convert_to_file_path()
                    self._track_temp_media(event, original_path)
                    record_path = await ensure_wav(original_path)
                    self._track_temp_media(event, record_path)
                    retained_path = await retain_platform_file(
                        record_path,
                        event.unified_msg_origin,
                    )
                    component.file = retained_path
                    component.path = retained_path
                    component.url = retained_path
                    event.untrack_temporary_local_file(retained_path)
                except Exception as exc:
                    logger.warning("Voice processing failed: %s", exc)
            elif isinstance(component, File | Video):
                try:
                    source_ref = (
                        component.file_
                        if isinstance(component, File)
                        else component.file or component.url
                    )
                    was_local = self._is_existing_local_image_ref(source_ref)
                    source_path = (
                        await component.get_file()
                        if isinstance(component, File)
                        else await component.convert_to_file_path()
                    )
                    if not source_path:
                        continue
                    if not was_local:
                        self._track_temp_media(event, source_path)
                    retained_path = await retain_platform_file(
                        source_path,
                        event.unified_msg_origin,
                    )
                    if isinstance(component, File):
                        component.file_ = retained_path
                    else:
                        component.file = retained_path
                        component.path = retained_path
                        component.url = retained_path
                    event.untrack_temporary_local_file(retained_path)
                except Exception as exc:
                    logger.warning("Attachment localization failed: %s", exc)

        # STT
        if self.stt_settings.get("enable", False):
            # TODO: 独立
            ctx = self.plugin_manager.context
            stt_provider = await ctx.get_using_stt_provider_async(
                event.unified_msg_origin
            )
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
