import asyncio
import datetime
import hashlib
import random
import re
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

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
    format_json_card_prompt,
    format_qq_face,
)
from astrbot.api.platform import MessageType
from astrbot.api.provider import Provider, ProviderRequest
from astrbot.core.agent.message import TextPart

"""
Group chat context awareness.
"""

GROUP_HISTORY_HEADER = (
    "<system_reminder>"
    "You are in a group chat. "
    "Belows are group chat context after your last reply:\n"
    "--- BEGIN CONTEXT---\n"
)
GROUP_HISTORY_FOOTER = "\n--- END CONTEXT ---\n</system_reminder>"
DEFAULT_GROUP_MESSAGE_MAX_CNT = 300
DEFAULT_CAPTION_CONCURRENCY = 2
MAX_CAPTION_INTERVAL_ENTRIES = 2048
MAX_CAPTION_CACHE_ENTRIES = 512
MAX_PENDING_LAZY_IMAGES = 2048
_VALID_CAPTION_SCOPES = frozenset({"all", "allowlist", "denylist"})
_LAZY_IMAGE_RE = re.compile(r"\[Image:__LAZY__:([0-9a-fA-F]+)\]")


class GroupChatContext:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context
        self._locks: dict[str, asyncio.Lock] = {}
        self.raw_records: dict[str, deque[str]] = defaultdict(deque)
        self._record_ids: dict[str, deque[str]] = defaultdict(deque)
        self._caption_sema = asyncio.Semaphore(DEFAULT_CAPTION_CONCURRENCY)
        self._caption_sema_bound = DEFAULT_CAPTION_CONCURRENCY
        self._caption_claim_lock = asyncio.Lock()
        self._caption_last_claim: dict[str, float] = {}
        self._caption_cache: OrderedDict[tuple[str, str], tuple[str, float]] = (
            OrderedDict()
        )
        self._caption_inflight: dict[tuple[str, str], asyncio.Future[str]] = {}
        self._caption_cache_lock = asyncio.Lock()
        self._pending_images: OrderedDict[str, tuple[str, str]] = OrderedDict()

    def _get_lock(self, umo: str) -> asyncio.Lock:
        lock = self._locks.get(umo)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[umo] = lock
        return lock

    def cfg(self, event: AstrMessageEvent):
        cfg = self.context.config.get(umo=event.unified_msg_origin)
        group_context_cfg = cfg["provider_ltm_settings"]
        image_caption_prompt = cfg["provider_settings"]["image_caption_prompt"]
        image_caption_provider_id = group_context_cfg.get("image_caption_provider_id")
        image_caption = group_context_cfg["image_caption"] and bool(
            image_caption_provider_id
        )
        scope = str(group_context_cfg.get("image_caption_scope") or "all").strip()
        if scope not in _VALID_CAPTION_SCOPES:
            scope = "all"
        groups = [
            str(item)
            for item in (group_context_cfg.get("image_caption_groups") or [])
            if isinstance(item, str) and item
        ]
        min_interval = _non_negative_float(
            group_context_cfg.get("image_caption_min_interval", 0),
            0.0,
        )
        max_concurrency = _positive_int(
            group_context_cfg.get(
                "image_caption_max_concurrency",
                DEFAULT_CAPTION_CONCURRENCY,
            ),
            DEFAULT_CAPTION_CONCURRENCY,
        )
        cache_ttl = _non_negative_float(
            group_context_cfg.get("image_caption_cache_ttl", 0),
            0.0,
        )
        lazy = bool(group_context_cfg.get("image_caption_lazy", False)) is True
        active_reply = group_context_cfg["active_reply"]
        enable_active_reply = active_reply.get("enable", False)
        ar_method = active_reply["method"]
        ar_possibility = active_reply["possibility_reply"]
        ar_prompt = active_reply.get("prompt", "")
        ar_whitelist = active_reply.get("whitelist", [])
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
            "image_caption_scope": scope,
            "image_caption_groups": groups,
            "image_caption_min_interval": min_interval,
            "image_caption_max_concurrency": max_concurrency,
            "image_caption_cache_ttl": cache_ttl,
            "image_caption_lazy": lazy,
            "enable_active_reply": enable_active_reply,
            "ar_method": ar_method,
            "ar_possibility": ar_possibility,
            "ar_prompt": ar_prompt,
            "ar_whitelist": ar_whitelist,
        }

    def _sync_caption_semaphore(self, max_concurrency: int) -> None:
        if max_concurrency == self._caption_sema_bound:
            return
        self._caption_sema = asyncio.Semaphore(max_concurrency)
        self._caption_sema_bound = max_concurrency

    def allows_group_image_caption(self, umo: str, cfg: dict) -> bool:
        if not cfg["image_caption"]:
            return False
        scope = cfg["image_caption_scope"]
        groups: list[str] = cfg["image_caption_groups"]
        if scope == "allowlist":
            return umo in groups
        if scope == "denylist":
            return umo not in groups
        return True

    async def _claim_caption_slot(self, umo: str, min_interval: float) -> bool:
        if min_interval <= 0:
            return True
        now = time.monotonic()
        async with self._caption_claim_lock:
            last = self._caption_last_claim.get(umo)
            if last is not None and now - last < min_interval:
                return False
            self._caption_last_claim[umo] = now
            self._prune_caption_claims(now, min_interval)
            return True

    def _prune_caption_claims(self, now: float, min_interval: float) -> None:
        expired = [
            key
            for key, claimed_at in self._caption_last_claim.items()
            if now - claimed_at >= min_interval
        ]
        for key in expired:
            self._caption_last_claim.pop(key, None)
        overflow = len(self._caption_last_claim) - MAX_CAPTION_INTERVAL_ENTRIES
        if overflow <= 0:
            return
        oldest = sorted(self._caption_last_claim.items(), key=lambda item: item[1])
        for key, _claimed_at in oldest[:overflow]:
            self._caption_last_claim.pop(key, None)

    def _cache_get(self, key: tuple[str, str]) -> str | None:
        entry = self._caption_cache.get(key)
        if entry is None:
            return None
        caption, expires_at = entry
        if expires_at <= time.monotonic():
            self._caption_cache.pop(key, None)
            return None
        self._caption_cache.move_to_end(key)
        return caption

    def _cache_put(self, key: tuple[str, str], caption: str, ttl: float) -> None:
        if ttl <= 0 or not caption:
            return
        self._caption_cache[key] = (caption, time.monotonic() + ttl)
        self._caption_cache.move_to_end(key)
        while len(self._caption_cache) > MAX_CAPTION_CACHE_ENTRIES:
            self._caption_cache.popitem(last=False)

    async def _image_content_id(self, image_url: str) -> str:
        path: Path | None = None
        if image_url.startswith("file://"):
            path = Path(image_url.removeprefix("file://"))
        else:
            candidate = Path(image_url)
            if candidate.is_file():
                path = candidate
        if path is not None and path.is_file():
            return await asyncio.to_thread(_md5_file, path)
        return hashlib.sha256(image_url.encode("utf-8")).hexdigest()

    async def caption_with_singleflight(
        self,
        umo: str,
        image_url: str,
        cfg: dict,
    ) -> str:
        content_id = await self._image_content_id(image_url)
        key = (umo, content_id)
        ttl = float(cfg.get("image_caption_cache_ttl") or 0)
        async with self._caption_cache_lock:
            cached = self._cache_get(key) if ttl > 0 else None
            if cached is not None:
                return cached
            inflight = self._caption_inflight.get(key)
            created = False
            if inflight is None:
                inflight = asyncio.get_running_loop().create_future()
                self._caption_inflight[key] = inflight
                created = True
        if not created:
            return await inflight
        try:
            self._sync_caption_semaphore(cfg["image_caption_max_concurrency"])
            await self._caption_sema.acquire()
            try:
                caption = await self.get_image_caption(
                    image_url,
                    cfg["image_caption_provider_id"],
                    cfg["image_caption_prompt"],
                )
            finally:
                self._caption_sema.release()
            if ttl > 0 and caption:
                async with self._caption_cache_lock:
                    self._cache_put(key, caption, ttl)
            if not inflight.done():
                inflight.set_result(caption)
            return caption
        except asyncio.CancelledError:
            if not inflight.done():
                inflight.cancel()
            raise
        except Exception as exc:
            if not inflight.done():
                inflight.set_exception(exc)
            raise
        finally:
            async with self._caption_cache_lock:
                if self._caption_inflight.get(key) is inflight:
                    self._caption_inflight.pop(key, None)

    def _remember_lazy_image(self, umo: str, url: str) -> str:
        token = uuid.uuid4().hex
        self._pending_images[token] = (umo, url)
        while len(self._pending_images) > MAX_PENDING_LAZY_IMAGES:
            self._pending_images.popitem(last=False)
        return token

    async def _resolve_lazy_captions(
        self,
        records: list[str],
        cfg: dict,
        umo: str,
    ) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for text in records:
            for token in _LAZY_IMAGE_RE.findall(text):
                if token not in seen:
                    seen.add(token)
                    tokens.append(token)
        if not tokens:
            return records

        async def _one(token: str) -> tuple[str, str]:
            pending = self._pending_images.get(token)
            if not pending:
                return token, "[Image]"
            pending_umo, url = pending
            try:
                caption = await self.caption_with_singleflight(pending_umo, url, cfg)
                if caption:
                    return token, f"[Image: {caption}]"
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("延迟图片转述失败: %s", exc)
            return token, "[Image]"

        results = await asyncio.gather(*[_one(token) for token in tokens])
        replace_map = dict(results)
        for token in tokens:
            self._pending_images.pop(token, None)

        def _sub(match: re.Match[str]) -> str:
            return replace_map.get(match.group(1), "[Image]")

        return [_LAZY_IMAGE_RE.sub(_sub, text) for text in records]

    async def get_image_caption(
        self,
        image_url: str,
        image_caption_provider_id: str,
        image_caption_prompt: str,
    ) -> str:
        if not image_caption_provider_id:
            provider = self.context.models.using_chat()
        else:
            provider = self.context.models.get(image_caption_provider_id)
            if not provider:
                raise Exception(f"没有找到 ID 为 {image_caption_provider_id} 的提供商")
        if not isinstance(provider, Provider):
            raise Exception(f"提供商类型错误({type(provider)})，无法获取图片描述")
        response = await provider.text_chat(
            prompt=image_caption_prompt,
            session_id=uuid.uuid4().hex,
            image_urls=[image_url],
            persist=False,
        )
        # A valid provider response may carry tool calls or an empty completion.
        # Keep the group-context prompt text-only rather than rendering ``None``.
        return response.completion_text or ""

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
        umo = event.unified_msg_origin
        lock = self._get_lock(umo)
        async with lock:
            cnt = len(self.raw_records.get(umo, deque()))
            self.raw_records.pop(umo, None)
            self._record_ids.pop(umo, None)
        self._locks.pop(umo, None)
        async with self._caption_claim_lock:
            self._caption_last_claim.pop(umo, None)
        stale_tokens = [
            token
            for token, (pending_umo, _url) in self._pending_images.items()
            if pending_umo == umo
        ]
        for token in stale_tokens:
            self._pending_images.pop(token, None)
        async with self._caption_cache_lock:
            for key in [key for key in self._caption_cache if key[0] == umo]:
                self._caption_cache.pop(key, None)
            for key in [key for key in self._caption_inflight if key[0] == umo]:
                future = self._caption_inflight.pop(key, None)
                if future is not None and not future.done():
                    future.cancel()
        return cnt

    async def handle_message(self, event: AstrMessageEvent) -> None:
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return

        umo = event.unified_msg_origin
        cfg = self.cfg(event)
        final_message = await self._format_message(event, cfg)

        async with self._get_lock(umo):
            records = self.raw_records[umo]
            record_ids = self._record_ids[umo]
            record_id = uuid.uuid4().hex
            records.append(final_message)
            record_ids.append(record_id)
            _trim_left(records, cfg["group_message_max_cnt"], record_ids)
            event.set_extra("_group_context_record_id", record_id)
            event.set_extra("_group_context_raw_idx", len(records) - 1)

        logger.debug(f"group_chat_context | {umo} | {final_message}")

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        umo = event.unified_msg_origin
        record_id = event.get_extra("_group_context_record_id", None)
        prompt_idx = event.get_extra("_group_context_raw_idx", -1)
        if not isinstance(record_id, str) and (
            not isinstance(prompt_idx, int) or prompt_idx < 0
        ):
            return

        async with self._get_lock(umo):
            records = self.raw_records.get(umo)
            if not records:
                return

            raw_list = list(records)
            id_list = list(self._record_ids.get(umo, deque()))
            if isinstance(record_id, str) and record_id in id_list:
                prompt_idx = id_list.index(record_id)

            if prompt_idx >= len(raw_list):
                return

            records_to_inject = raw_list[:prompt_idx]
            remaining = raw_list[prompt_idx + 1 :]
            remaining_ids = id_list[prompt_idx + 1 :] if id_list else []
            records.clear()
            records.extend(remaining)
            if id_list:
                record_ids = self._record_ids[umo]
                record_ids.clear()
                record_ids.extend(remaining_ids)

        if records_to_inject:
            cfg = self.cfg(event)
            if cfg.get("image_caption_lazy"):
                records_to_inject = await self._resolve_lazy_captions(
                    records_to_inject,
                    cfg,
                    umo,
                )
            req.extra_user_content_parts.append(
                TextPart(text=_format_group_history_block(records_to_inject))
            )

    async def _format_message(self, event: AstrMessageEvent, cfg: dict) -> str:
        datetime_str = datetime.datetime.now().strftime("%H:%M:%S")
        parts = [f"[{event.message_obj.sender.nickname}/{datetime_str}]: "]
        caption_claimed = False

        for comp in event.get_messages():
            if isinstance(comp, Plain):
                parts.append(f" {comp.text}")
            elif isinstance(comp, Image):
                captioned = False
                if self.allows_group_image_caption(event.unified_msg_origin, cfg):
                    if not caption_claimed:
                        caption_claimed = await self._claim_caption_slot(
                            event.unified_msg_origin,
                            cfg["image_caption_min_interval"],
                        )
                    if caption_claimed:
                        try:
                            url = comp.url if comp.url else comp.file
                            if not url:
                                raise Exception("图片 URL 为空")
                            if cfg.get("image_caption_lazy"):
                                token = self._remember_lazy_image(
                                    event.unified_msg_origin,
                                    url,
                                )
                                parts.append(f" [Image:__LAZY__:{token}]")
                                captioned = True
                            else:
                                caption = await self.caption_with_singleflight(
                                    event.unified_msg_origin,
                                    url,
                                    cfg,
                                )
                                if caption:
                                    parts.append(f" [Image: {caption}]")
                                    captioned = True
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.error("获取图片描述失败: %s", e)
                if not captioned:
                    parts.append(" [Image]")
            elif isinstance(comp, Json):
                parts.append(f" {format_json_card_prompt(comp)}")
            elif isinstance(comp, At):
                is_at_self = str(comp.qq) in (
                    event.get_self_id(),
                    "all",
                )
                if is_at_self:
                    parts.insert(1, "⚠️[DIRECTED AT YOU] ")
                parts.append(f" [At: {comp.name}]")
            elif isinstance(comp, Reply):
                if comp.chain:
                    chain_desc = _describe_chain(comp.chain)
                    parts.append(
                        f" [Quote({comp.sender_nickname}: {_truncate_reply_text(chain_desc)})]"
                    )
                elif comp.message_str:
                    parts.append(
                        f" [Quote({comp.sender_nickname}: {_truncate_reply_text(comp.message_str)})]"
                    )
                else:
                    parts.append(" [Quote]")
            elif isinstance(comp, Face):
                parts.append(f" {format_qq_face(comp.id)}")

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
            desc.append(format_qq_face(getattr(c, "id", None)))
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


def _md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _positive_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
    except TypeError, ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


def _non_negative_float(value, fallback: float) -> float:
    try:
        parsed = float(value)
    except TypeError, ValueError:
        return fallback
    return parsed if parsed >= 0 else fallback


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
