import datetime
import json
import random
import uuid
from collections import defaultdict, deque
from pathlib import Path

from PIL.Image import DecompressionBombError

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import (
    At,
    AtAll,
    Face,
    File,
    Forward,
    Image,
    Json,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.api.platform import MessageType
from astrbot.api.provider import Provider, ProviderRequest
from astrbot.core.agent.message import TextPart
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import (
    ImageInputTooLargeError,
    normalize_model_image_max_size,
    prepare_model_image,
)

"""
Group chat context awareness.
"""

IMAGE_CAPTION_SKIPPED = "图片过大，已跳过转述"
ANIMATION_MONTAGE_CAPTION_NOTICE = (
    "\n\nThis image is a montage of evenly sampled frames from an animation, "
    "laid out in reading order. Describe what the animation shows and how it "
    "changes over time; do not describe the grid layout."
)

GROUP_HISTORY_HEADER = (
    "<system_reminder>"
    "You are in a group chat. "
    "Belows are group chat context after your last reply:\n"
    "--- BEGIN CONTEXT---\n"
)
GROUP_HISTORY_FOOTER = "\n--- END CONTEXT ---\n</system_reminder>"
DEFAULT_GROUP_MESSAGE_MAX_CNT = 1000


class GroupChatContext:
    def __init__(self, acm: AstrBotConfigManager, context: star.Context) -> None:
        self.acm = acm
        self.context = context
        self.raw_records: dict[str, deque[str]] = defaultdict(deque)
        self._record_ids: dict[str, deque[str]] = defaultdict(deque)

    def cfg(self, event: AstrMessageEvent):
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        group_context_cfg = cfg["provider_ltm_settings"]
        image_caption_prompt = cfg["provider_settings"]["image_caption_prompt"]
        image_caption_provider_id = group_context_cfg.get("image_caption_provider_id")
        image_caption = group_context_cfg["image_caption"] and bool(
            image_caption_provider_id
        )
        active_reply = group_context_cfg["active_reply"]
        enable_active_reply = active_reply.get("enable", False)
        ar_method = active_reply["method"]
        ar_possibility = active_reply["possibility_reply"]
        ar_prompt = active_reply.get("prompt", "")
        ar_whitelist = active_reply.get("whitelist", [])
        image_compress_options = cfg.get("provider_settings", {}).get(
            "image_compress_options",
        )
        image_max_size = normalize_model_image_max_size(
            image_compress_options.get("max_size")
            if isinstance(image_compress_options, dict)
            else None,
        )
        return {
            "group_message_max_cnt": _positive_int(
                group_context_cfg.get(
                    "group_message_max_cnt",
                    DEFAULT_GROUP_MESSAGE_MAX_CNT,
                ),
                DEFAULT_GROUP_MESSAGE_MAX_CNT,
            ),
            "image_caption": image_caption,
            "image_caption_prompt": image_caption_prompt,
            "image_caption_provider_id": image_caption_provider_id,
            "image_max_size": image_max_size,
            "enable_active_reply": enable_active_reply,
            "ar_method": ar_method,
            "ar_possibility": ar_possibility,
            "ar_prompt": ar_prompt,
            "ar_whitelist": ar_whitelist,
        }

    async def get_image_caption(
        self,
        image_url: str,
        image_caption_provider_id: str,
        image_caption_prompt: str,
        image_max_size: int,
    ) -> str:
        if not image_caption_provider_id:
            provider = await self.context.get_using_provider_async()
        else:
            provider = self.context.get_provider_by_id(image_caption_provider_id)
            if not provider:
                raise Exception(f"没有找到 ID 为 {image_caption_provider_id} 的提供商")
        if not isinstance(provider, Provider):
            raise Exception(f"提供商类型错误({type(provider)})，无法获取图片描述")

        # Normalize the image before captioning so animations become a still
        # montage and non-model-friendly formats are re-encoded. Without this
        # the raw reference (often an animated GIF) is forwarded verbatim and
        # vision APIs may reject it with `invalid image input`.
        image_ref = image_url
        caption_prompt = image_caption_prompt
        cleanup_paths: list[Path] = []
        try:
            prepared = await prepare_model_image(
                image_url,
                max_size=image_max_size,
                output_dir=Path(get_astrbot_temp_path()),
            )
        except ImageInputTooLargeError:
            # The source is over the input cap; never forward it to the provider.
            logger.warning(f"图片超过转述输入上限，已跳过: {image_url}")
            return IMAGE_CAPTION_SKIPPED
        except DecompressionBombError:
            # Pillow's decoded-pixel safety limit tripped; never decode it again.
            logger.warning(f"图片解码尺寸超过安全上限，已跳过: {image_url}")
            return IMAGE_CAPTION_SKIPPED
        except Exception as e:
            logger.warning(f"图片转述预处理失败，回退原图: {e}")
            prepared = None
        if prepared:
            image_ref, is_montage, temporary, original_path, original_temporary = (
                prepared
            )
            if temporary:
                cleanup_paths.append(Path(image_ref))
            # `prepare_model_image` detaches the file it downloaded or decoded for
            # this call, so the caption path owns it. A reused source belongs to
            # the caller or event and must survive captioning.
            if original_temporary:
                cleanup_paths.append(Path(original_path))
            if is_montage:
                caption_prompt = (
                    f"{image_caption_prompt}{ANIMATION_MONTAGE_CAPTION_NOTICE}"
                )

        try:
            response = await provider.text_chat(
                prompt=caption_prompt,
                session_id=uuid.uuid4().hex,
                image_urls=[image_ref],
                persist=False,
            )
        finally:
            for path in cleanup_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(f"清理临时图片失败: {e}")
        return response.completion_text

    async def need_active_reply(self, event: AstrMessageEvent) -> bool:
        cfg = self.cfg(event)
        if not cfg["enable_active_reply"]:
            return False
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return False
        if event.is_at_or_wake_command:
            return False
        if cfg["ar_whitelist"] and (
            event.unified_msg_origin not in cfg["ar_whitelist"]
            and (
                event.get_group_id() and event.get_group_id() not in cfg["ar_whitelist"]
            )
        ):
            return False
        match cfg["ar_method"]:
            case "possibility_reply":
                return random.random() < cfg["ar_possibility"]
        return False

    async def remove_session(self, event: AstrMessageEvent) -> int:
        return self.clear_session(event.unified_msg_origin)

    def clear_session(self, umo: str) -> int:
        """Discard pending observations for one message origin.

        Args:
            umo: Unified message origin whose conversation was cleared.

        Returns:
            Number of discarded observations.
        """
        records = self.raw_records.pop(umo, None)
        self._record_ids.pop(umo, None)
        return len(records) if records else 0

    def clear_platform(self, platform_id: str) -> None:
        """Discard all buffered observations owned by one adapter instance.

        Args:
            platform_id: Exact platform instance ID being cleaned up.
        """
        for umo in list(self.raw_records):
            if umo.partition(":")[0] == platform_id:
                self.clear_session(umo)

    async def handle_message(self, event: AstrMessageEvent) -> None:
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return

        umo = event.unified_msg_origin
        cfg = self.cfg(event)
        records = self.raw_records[umo]
        final_message = await self._format_message(event, cfg)
        # A deletion during image captioning retires this particular buffer.
        if self.raw_records.get(umo) is not records:
            return

        record_ids = self._record_ids[umo]
        record_id = uuid.uuid4().hex
        records.append(final_message)
        record_ids.append(record_id)
        _trim_left(records, cfg["group_message_max_cnt"], record_ids)
        event.set_extra("_group_context_record_id", record_id)

        logger.debug(f"group_chat_context | {umo} | {final_message}")

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        umo = event.unified_msg_origin
        record_id = event.get_extra("_group_context_record_id", None)
        record_ids = self._record_ids.get(umo)
        if (
            not isinstance(record_id, str)
            or not record_ids
            or record_id not in record_ids
        ):
            return

        # Consume through this event without yielding to other buffer mutations.
        records = self.raw_records[umo]
        records_to_inject = []
        while record_ids.popleft() != record_id:
            records_to_inject.append(records.popleft())
        records.popleft()

        if records_to_inject:
            req.extra_user_content_parts.append(
                TextPart(text=_format_group_history_block(records_to_inject))
            )

    async def _format_message(self, event: AstrMessageEvent, cfg: dict) -> str:
        datetime_str = datetime.datetime.now().strftime("%H:%M:%S")
        parts = [f"[{event.message_obj.sender.nickname}/{datetime_str}]: "]

        for comp in event.get_messages():
            if isinstance(comp, Plain):
                parts.append(f" {comp.text}")
            elif isinstance(comp, Image):
                if cfg["image_caption"]:
                    try:
                        url = comp.url if comp.url else comp.file
                        if not url:
                            raise Exception("图片 URL 为空")
                        caption = await self.get_image_caption(
                            url,
                            cfg["image_caption_provider_id"],
                            cfg["image_caption_prompt"],
                            cfg["image_max_size"],
                        )
                        parts.append(f" [Image: {caption}]")
                    except Exception as e:
                        logger.error(f"获取图片描述失败: {e}")
                else:
                    parts.append(" [Image]")
            elif isinstance(comp, Json):
                card_data = comp.data
                if isinstance(card_data, dict) and isinstance(
                    card_data.get("data"), str
                ):
                    try:
                        nested_data = json.loads(card_data["data"])
                        if isinstance(nested_data, dict):
                            card_data = nested_data
                    except json.JSONDecodeError:
                        pass

                detail = {}
                if isinstance(card_data, dict):
                    meta = card_data.get("meta")
                    if isinstance(meta, dict):
                        candidate = meta.get("detail_1") or meta.get("news")
                        if isinstance(candidate, dict):
                            detail = candidate

                fields = []
                for label, value in (
                    ("Title", detail.get("title")),
                    ("Description", detail.get("desc")),
                    ("URL", detail.get("qqdocurl") or detail.get("jumpUrl")),
                ):
                    if isinstance(value, str) and value.strip():
                        normalized = " ".join(value.split())
                        fields.append(f"{label}: {_truncate_reply_text(normalized)}")
                suffix = f": {'; '.join(fields)}" if fields else ""
                parts.append(f" [Shared Card{suffix}]")
            elif isinstance(comp, At):
                is_at_self = str(comp.qq) in (
                    event.get_self_id(),
                    "all",
                )
                if is_at_self:
                    parts.insert(1, "⚠️[DIRECTED AT YOU] ")
                parts.append(f" [At: {comp.name}]")
            elif isinstance(comp, Reply):
                if comp.message_str:
                    parts.append(
                        f" [Quote({comp.sender_nickname}: {_truncate_reply_text(comp.message_str)})]"
                    )
                elif comp.chain:
                    chain_desc = _describe_chain(comp.chain)
                    parts.append(f" [Quote({comp.sender_nickname}: {chain_desc})]")
                else:
                    parts.append(" [Quote]")

        return "".join(parts)


_MAX_REPLY_TEXT_LENGTH = 200


def _describe_chain(chain: list) -> str:
    """Summarize message chain content for quoted reply display."""
    desc = []
    for c in chain:
        if isinstance(c, Plain) and getattr(c, "text", None):
            desc.append(c.text)
        elif isinstance(c, Image):
            desc.append("[Image]")
        elif isinstance(c, At):
            name = getattr(c, "name", "") or getattr(c, "qq", "")
            desc.append(f"[At: {name}]")
        elif isinstance(c, Record):
            desc.append("[Voice]")
        elif isinstance(c, Video):
            desc.append("[Video]")
        elif isinstance(c, File):
            desc.append(f"[File: {getattr(c, 'name', '') or ''}]")
        elif isinstance(c, Forward):
            desc.append("[Forward]")
        elif isinstance(c, AtAll):
            desc.append("[At: All]")
        elif isinstance(c, Face):
            desc.append(f"[Sticker: {getattr(c, 'id', '')}]")
        elif isinstance(c, Reply):
            desc.append("[Quote]")
        else:
            desc.append(f"[{c.__class__.__name__}]")
    return "".join(desc) or "[Unknown]"


def _truncate_reply_text(text: str) -> str:
    """Truncate overly long quoted reply text."""
    if len(text) <= _MAX_REPLY_TEXT_LENGTH:
        return text
    return text[:_MAX_REPLY_TEXT_LENGTH] + "..."


def _positive_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _trim_left(
    records: deque[str],
    max_records: int,
    record_ids: deque[str] | None = None,
) -> None:
    while len(records) > max_records:
        records.popleft()
        if record_ids:
            record_ids.popleft()


def _format_group_history_block(records: list[str]) -> str:
    return GROUP_HISTORY_HEADER + "\n".join(records) + GROUP_HISTORY_FOOTER
