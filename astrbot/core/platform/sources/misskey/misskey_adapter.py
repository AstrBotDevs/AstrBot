import asyncio
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import (
    AstrBotMessage,
    Group,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.platform.send_result import PlatformSendResult

from .misskey_api import MisskeyAPI

try:
    import magic  # type: ignore
except Exception:
    magic = None

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .misskey_event import MisskeyPlatformEvent
from .misskey_utils import (
    add_at_mention_if_needed,
    cache_room_info,
    cache_user_info,
    create_base_message,
    extract_sender_info,
    format_poll,
    is_valid_chat_session_id,
    is_valid_room_session_id,
    process_at_mention,
    process_files,
    resolve_message_visibility,
    serialize_message_chain,
)

# Constants
MAX_FILE_UPLOAD_COUNT = 16
DEFAULT_UPLOAD_CONCURRENCY = 3


def _misskey_room_owner_role(message: AstrBotMessage) -> str | None:
    raw = getattr(message, "raw_message", None)
    if not isinstance(raw, dict):
        return None
    room_id = raw.get("toRoomId")
    room = raw.get("toRoom")
    if room_id is None or not isinstance(room, dict):
        return None
    if str(room_id) != str(message.group_id or ""):
        return None
    owner_id = room.get("ownerId")
    sender_id = getattr(message.sender, "user_id", None)
    if owner_id is None or sender_id is None:
        return None
    if str(owner_id) != str(sender_id):
        return None
    return "owner"


@register_platform_adapter(
    "misskey", "Misskey 平台适配器", support_streaming_message=False
)
class MisskeyPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config or {}, event_queue)
        self.settings = platform_settings or {}
        self.instance_url = self.config.get("misskey_instance_url", "")
        self.access_token = self.config.get("misskey_token", "")
        self.max_message_length = self.config.get("max_message_length", 3000)
        self.default_visibility = self.config.get(
            "misskey_default_visibility",
            "public",
        )
        self.local_only = self.config.get("misskey_local_only", False)
        self.enable_chat = self.config.get("misskey_enable_chat", True)
        self.enable_file_upload = self.config.get("misskey_enable_file_upload", True)
        self.upload_folder = self.config.get("misskey_upload_folder")

        # download / security related options (exposed to platform_config)
        self.allow_insecure_downloads = bool(
            self.config.get("misskey_allow_insecure_downloads", False),
        )
        # parse download timeout and chunk size safely
        _dt = self.config.get("misskey_download_timeout")
        try:
            self.download_timeout = int(_dt) if _dt is not None else 15
        except Exception:
            self.download_timeout = 15

        _chunk = self.config.get("misskey_download_chunk_size")
        try:
            self.download_chunk_size = int(_chunk) if _chunk is not None else 64 * 1024
        except Exception:
            self.download_chunk_size = 64 * 1024
        # parse max download bytes safely
        _md_bytes = self.config.get("misskey_max_download_bytes")
        try:
            self.max_download_bytes = int(_md_bytes) if _md_bytes is not None else None
        except Exception:
            self.max_download_bytes = None

        self.api: MisskeyAPI | None = None
        self._running = False
        self.bot_self_id = ""
        self._bot_username = ""
        self._user_cache = {}

    def meta(self) -> PlatformMetadata:
        default_config = {
            "misskey_instance_url": "",
            "misskey_token": "",
            "max_message_length": 3000,
            "misskey_default_visibility": "public",
            "misskey_local_only": False,
            "misskey_enable_chat": True,
            # download / security options
            "misskey_allow_insecure_downloads": False,
            "misskey_download_timeout": 15,
            "misskey_download_chunk_size": 65536,
            "misskey_max_download_bytes": None,
        }
        default_config.update(self.config)

        return PlatformMetadata(
            name="misskey",
            description="Misskey 平台适配器",
            id=self.config.get("id", "misskey"),
            default_config_tmpl=default_config,
            support_streaming_message=False,
        )

    def create_event(self, message: AstrBotMessage) -> MisskeyPlatformEvent:
        """Creates a Misskey message event.

        Args:
            message: AstrBot message object to wrap.

        Returns:
            Created Misskey message event.
        """
        event = MisskeyPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self,
        )
        if not event.is_private_chat():
            role = _misskey_room_owner_role(message)
            if role is not None:
                event.set_platform_member_role(role, source="adapter")
        return event

    async def run(self) -> None:
        if not self.instance_url or not self.access_token:
            logger.error("[Misskey] 配置不完整，无法启动")
            return

        self.api = MisskeyAPI(
            self.instance_url,
            self.access_token,
            allow_insecure_downloads=self.allow_insecure_downloads,
            download_timeout=self.download_timeout,
            chunk_size=self.download_chunk_size,
            max_download_bytes=self.max_download_bytes,
        )
        self._running = True

        try:
            user_info = await self.api.get_current_user()
            self.bot_self_id = str(user_info.get("id", ""))
            self._bot_username = user_info.get("username", "")
            logger.info(
                f"[Misskey] 已连接用户: {self._bot_username} (ID: {self.bot_self_id})",
            )
        except Exception as e:
            logger.error(f"[Misskey] 获取用户信息失败: {e}")
            self._running = False
            return

        await self._start_websocket_connection()

    def _register_event_handlers(self, streaming) -> None:
        """注册事件处理器"""
        streaming.add_message_handler("notification", self._handle_notification)
        streaming.add_message_handler("main:notification", self._handle_notification)

        if self.enable_chat:
            streaming.add_message_handler("newChatMessage", self._handle_chat_message)
            streaming.add_message_handler(
                "messaging:newChatMessage",
                self._handle_chat_message,
            )
            streaming.add_message_handler("_debug", self._debug_handler)

    def _is_file_component(self, component: object) -> bool:
        """Return whether a component can provide an uploadable file source."""
        return isinstance(
            component,
            (Comp.Image, Comp.File, Comp.Record, Comp.Video),
        ) or any(
            hasattr(component, attribute)
            for attribute in (
                "convert_to_file_path",
                "get_file",
                "file",
                "url",
                "path",
                "src",
                "source",
            )
        )

    def _prepare_outbound_message(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> tuple[str, Sequence[object]]:
        """Serialize text, add a recipient mention, and collect file components."""
        text, has_at_user = serialize_message_chain(message_chain.chain)
        session_id = session.session_id

        if not has_at_user and session_id and "%" in session_id:
            user_id_for_cache = session_id.split("%", 1)[1]
            text = add_at_mention_if_needed(
                text,
                self._user_cache.get(user_id_for_cache),
                has_at_user,
            )

        if len(text) > self.max_message_length:
            text = text[: self.max_message_length] + "..."

        file_components = [
            component
            for component in message_chain.chain
            if self._is_file_component(component)
        ][:MAX_FILE_UPLOAD_COUNT]
        return text, file_components

    async def _upload_file_components(
        self,
        components: Sequence[object],
    ) -> tuple[list[str], list[str]]:
        """Upload file components and return Misskey IDs plus URL fallbacks."""
        api = self.api
        if not api or not components:
            return [], []

        from .misskey_utils import (
            resolve_component_url_or_path,
            upload_local_with_retries,
        )

        try:
            configured_concurrency = int(
                self.config.get(
                    "misskey_upload_concurrency",
                    DEFAULT_UPLOAD_CONCURRENCY,
                ),
            )
        except TypeError, ValueError:
            configured_concurrency = DEFAULT_UPLOAD_CONCURRENCY
        semaphore = asyncio.Semaphore(min(max(configured_concurrency, 1), 10))
        temp_root = Path(get_astrbot_temp_path()).resolve(strict=False)

        async def upload_component(component: object) -> str | dict[str, str] | None:
            local_path: Path | None = None
            try:
                async with semaphore:
                    url_candidate, resolved_path = await resolve_component_url_or_path(
                        component,
                    )
                    if resolved_path:
                        local_path = Path(resolved_path).resolve(strict=False)

                    preferred_name = getattr(component, "name", None) or getattr(
                        component,
                        "file",
                        None,
                    )
                    if url_candidate:
                        result = await api.upload_and_find_file(
                            str(url_candidate),
                            preferred_name,
                            folder_id=self.upload_folder,
                        )
                        if isinstance(result, dict) and result.get("id"):
                            return str(result["id"])
                    if local_path:
                        file_id = await upload_local_with_retries(
                            api,
                            str(local_path),
                            preferred_name,
                            self.upload_folder,
                        )
                        if file_id:
                            return file_id
            except Exception as exc:
                logger.warning("[Misskey] 文件上传失败: %s", exc)
            finally:
                if local_path and local_path.is_relative_to(temp_root):
                    try:
                        local_path.unlink(missing_ok=True)
                        logger.debug("[Misskey] 已清理临时文件: %s", local_path)
                    except OSError as exc:
                        logger.warning("[Misskey] 清理临时文件失败: %s", exc)

            register_file = getattr(component, "register_to_file_service", None)
            if register_file:
                try:
                    fallback_url = await register_file()
                except Exception as exc:
                    logger.warning("[Misskey] 获取文件回退 URL 失败: %s", exc)
                else:
                    if fallback_url:
                        return {"fallback_url": str(fallback_url)}
            return None

        results = await asyncio.gather(
            *(upload_component(component) for component in components)
        )
        file_ids: list[str] = []
        fallback_urls: list[str] = []
        for result in results:
            if isinstance(result, dict):
                fallback_urls.append(result["fallback_url"])
            elif result:
                file_ids.append(result)
        return file_ids, fallback_urls

    async def _send_prepared_message(
        self,
        session: MessageSession,
        message_chain: MessageChain,
        text: str,
        file_ids: list[str],
        fallback_urls: list[str],
    ) -> None:
        """Route one prepared message to a room, chat, or note target."""
        if not self.api:
            raise RuntimeError("Misskey API client is not initialized")

        session_id = session.session_id
        if fallback_urls:
            text = "\n".join(part for part in (text, *fallback_urls) if part)

        if session_id and is_valid_room_session_id(session_id):
            from .misskey_utils import extract_room_id_from_session_id

            payload: dict[str, Any] = {
                "toRoomId": extract_room_id_from_session_id(session_id),
                "text": text,
            }
            if file_ids:
                payload["fileIds"] = file_ids
            await self.api.send_room_message(payload)
        elif session_id and is_valid_chat_session_id(session_id):
            from .misskey_utils import extract_user_id_from_session_id

            user_id = extract_user_id_from_session_id(session_id)
            payload: dict[str, Any] = {"toUserId": user_id, "text": text}
            if file_ids:
                payload["fileId"] = file_ids[0]
                if len(file_ids) > 1:
                    logger.warning(
                        "[Misskey] 聊天消息只支持单个文件，忽略其余 %s 个文件",
                        len(file_ids) - 1,
                    )
            await self.api.send_message(payload)
        else:
            user_id_for_cache = (
                session_id.split("%", 1)[1] if "%" in session_id else session_id
            )
            visibility, visible_user_ids = resolve_message_visibility(
                user_id=user_id_for_cache,
                user_cache=self._user_cache,
                self_id=self.bot_self_id,
                default_visibility=self.default_visibility,
            )
            fields = self._extract_additional_fields(session, message_chain)
            await self.api.create_note(
                text=text,
                visibility=visibility,
                visible_user_ids=visible_user_ids,
                file_ids=file_ids or None,
                local_only=self.local_only,
                reply_id=self._user_cache.get(user_id_for_cache, {}).get(
                    "reply_to_note_id"
                ),
                cw=fields["cw"],
                poll=fields["poll"],
                renote_id=fields["renote_id"],
                channel_id=fields["channel_id"],
            )

    def _process_poll_data(
        self,
        message: AstrBotMessage,
        poll: dict[str, Any],
        message_parts: list[str],
    ) -> None:
        """处理投票数据，将其添加到消息中"""
        try:
            if not isinstance(message.raw_message, dict):
                message.raw_message = {}
            message.raw_message["poll"] = poll
            message.__setattr__("poll", poll)
        except Exception:
            pass

        poll_text = format_poll(poll)
        if poll_text:
            message.message.append(Comp.Plain(poll_text))
            message_parts.append(poll_text)

    def _extract_additional_fields(self, session, message_chain) -> dict[str, Any]:
        """从会话和消息链中提取额外字段"""
        fields = {"cw": None, "poll": None, "renote_id": None, "channel_id": None}

        for comp in message_chain.chain:
            if hasattr(comp, "cw") and getattr(comp, "cw", None):
                fields["cw"] = comp.cw
                break

        if hasattr(session, "extra_data") and isinstance(
            getattr(session, "extra_data", None),
            dict,
        ):
            extra_data = session.extra_data
            fields.update(
                {
                    "poll": extra_data.get("poll"),
                    "renote_id": extra_data.get("renote_id"),
                    "channel_id": extra_data.get("channel_id"),
                },
            )

        return fields

    async def _start_websocket_connection(self) -> None:
        backoff_delay = 1.0
        max_backoff = 300.0
        backoff_multiplier = 1.5
        connection_attempts = 0

        while self._running:
            try:
                connection_attempts += 1
                if not self.api:
                    logger.error("[Misskey] API 客户端未初始化")
                    break

                streaming = self.api.get_streaming_client()
                self._register_event_handlers(streaming)

                if await streaming.connect():
                    logger.info(
                        f"[Misskey] WebSocket 已连接 (尝试 #{connection_attempts})",
                    )
                    connection_attempts = 0
                    await streaming.subscribe_channel("main")
                    if self.enable_chat:
                        await streaming.subscribe_channel("messaging")
                        await streaming.subscribe_channel("messagingIndex")
                        logger.info("[Misskey] 聊天频道已订阅")

                    backoff_delay = 1.0
                    await streaming.listen()
                else:
                    logger.error(
                        f"[Misskey] WebSocket 连接失败 (尝试 #{connection_attempts})",
                    )

            except Exception as e:
                logger.error(
                    f"[Misskey] WebSocket 异常 (尝试 #{connection_attempts}): {e}",
                )

            if self._running:
                jitter = random.uniform(0, 1.0)
                sleep_time = backoff_delay + jitter
                logger.info(
                    f"[Misskey] {sleep_time:.1f}秒后重连 (下次尝试 #{connection_attempts + 1})",
                )
                await asyncio.sleep(sleep_time)
                backoff_delay = min(backoff_delay * backoff_multiplier, max_backoff)

    async def _handle_notification(self, data: dict[str, Any]) -> None:
        try:
            notification_type = data.get("type")
            logger.debug(
                f"[Misskey] 收到通知事件: type={notification_type}, user_id={data.get('userId', 'unknown')}",
            )
            if notification_type in ["mention", "reply", "quote"]:
                note = data.get("note")
                if note and self._is_bot_mentioned(note):
                    logger.info(
                        f"[Misskey] 处理贴文提及: {note.get('text', '')[:50]}...",
                    )
                    message = await self.convert_message(note)
                    self.commit_event(self.create_event(message))
        except Exception as e:
            logger.error(f"[Misskey] 处理通知失败: {e}")

    async def _handle_chat_message(self, data: dict[str, Any]) -> None:
        try:
            sender_id = str(
                data.get("fromUserId", "") or data.get("fromUser", {}).get("id", ""),
            )
            room_id = data.get("toRoomId")
            logger.debug(
                f"[Misskey] 收到聊天事件: sender_id={sender_id}, room_id={room_id}, is_self={sender_id == self.bot_self_id}",
            )
            if sender_id == self.bot_self_id:
                return

            if room_id:
                raw_text = data.get("text", "")
                logger.debug(
                    f"[Misskey] 检查群聊消息: '{raw_text}', 机器人用户名: '{self._bot_username}'",
                )

                message = await self.convert_room_message(data)
                logger.info(f"[Misskey] 处理群聊消息: {message.message_str[:50]}...")
            else:
                message = await self.convert_chat_message(data)
                logger.info(f"[Misskey] 处理私聊消息: {message.message_str[:50]}...")

            self.commit_event(self.create_event(message))
        except Exception as e:
            logger.error(f"[Misskey] 处理聊天消息失败: {e}")

    async def _debug_handler(self, data: dict[str, Any]) -> None:
        event_type = data.get("type", "unknown")
        logger.debug(
            f"[Misskey] 收到未处理事件: type={event_type}, channel={data.get('channel', 'unknown')}",
        )

    def _is_bot_mentioned(self, note: dict[str, Any]) -> bool:
        text = note.get("text", "")
        if not text:
            return False

        mentions = note.get("mentions", [])
        if self._bot_username and f"@{self._bot_username}" in text:
            return True
        if self.bot_self_id in [str(uid) for uid in mentions]:
            return True

        reply = note.get("reply")
        if reply and isinstance(reply, dict):
            reply_user_id = str(reply.get("user", {}).get("id", ""))
            if reply_user_id == self.bot_self_id:
                return bool(self._bot_username and f"@{self._bot_username}" in text)

        return False

    async def send_by_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> PlatformSendResult | None:
        if not self.api:
            logger.error("[Misskey] API 客户端未初始化")
            return PlatformSendResult(
                platform_id=self.meta().id,
                success=False,
                target=session.session_id,
                message_count=len(message_chain.chain),
                error_message="Misskey API client is not initialized",
            )

        try:
            text, file_components = self._prepare_outbound_message(
                session, message_chain
            )
            if not text.strip() and not file_components:
                logger.warning("[Misskey] 消息内容为空且无文件组件，跳过发送")
                return PlatformSendResult(
                    platform_id=self.meta().id,
                    success=False,
                    target=session.session_id,
                    error_message="Message content is empty",
                )
            file_ids, fallback_urls = ([], [])
            if self.enable_file_upload:
                file_ids, fallback_urls = await self._upload_file_components(
                    file_components,
                )
            await self._send_prepared_message(
                session,
                message_chain,
                text,
                file_ids,
                fallback_urls,
            )
        except Exception as exc:
            logger.error("[Misskey] 发送消息失败: %s", exc)
            return PlatformSendResult(
                platform_id=self.meta().id,
                success=False,
                target=session.session_id,
                message_count=len(message_chain.chain),
                error_message=str(exc),
            )

        return await super().send_by_session(session, message_chain)

    async def convert_message(self, raw_data: dict[str, Any]) -> AstrBotMessage:
        """将 Misskey 贴文数据转换为 AstrBotMessage 对象"""
        sender_info = extract_sender_info(raw_data, is_chat=False)
        message = create_base_message(
            raw_data,
            sender_info,
            self.bot_self_id,
            is_chat=False,
        )
        cache_user_info(
            self._user_cache,
            sender_info,
            raw_data,
            self.bot_self_id,
            is_chat=False,
        )

        message_parts = []
        raw_text = raw_data.get("text", "")

        if raw_text:
            text_parts, processed_text = process_at_mention(
                message,
                raw_text,
                self._bot_username,
                self.bot_self_id,
            )
            message_parts.extend(text_parts)

        files = raw_data.get("files", [])
        file_parts = await process_files(message, files)
        message_parts.extend(file_parts)

        poll = raw_data.get("poll") or (
            raw_data.get("note", {}).get("poll")
            if isinstance(raw_data.get("note"), dict)
            else None
        )
        if poll and isinstance(poll, dict):
            self._process_poll_data(message, poll, message_parts)

        message.message_str = (
            " ".join(part for part in message_parts if part.strip())
            if message_parts
            else ""
        )
        return message

    async def convert_chat_message(self, raw_data: dict[str, Any]) -> AstrBotMessage:
        """将 Misskey 聊天消息数据转换为 AstrBotMessage 对象"""
        sender_info = extract_sender_info(raw_data, is_chat=True)
        message = create_base_message(
            raw_data,
            sender_info,
            self.bot_self_id,
            is_chat=True,
        )
        cache_user_info(
            self._user_cache,
            sender_info,
            raw_data,
            self.bot_self_id,
            is_chat=True,
        )

        raw_text = raw_data.get("text", "")
        if raw_text:
            message.message.append(Comp.Plain(raw_text))

        files = raw_data.get("files", [])
        await process_files(message, files, include_text_parts=False)

        message.message_str = raw_text if raw_text else ""
        return message

    async def convert_room_message(self, raw_data: dict[str, Any]) -> AstrBotMessage:
        """将 Misskey 群聊消息数据转换为 AstrBotMessage 对象"""
        sender_info = extract_sender_info(raw_data, is_chat=True)
        room_id = raw_data.get("toRoomId", "")
        message = create_base_message(
            raw_data,
            sender_info,
            self.bot_self_id,
            is_chat=False,
            room_id=room_id,
        )
        room_data = raw_data.get("toRoom")
        if message.group and isinstance(room_data, dict):
            message.group = Group(
                group_id=message.group.group_id,
                group_name=room_data.get("name") or None,
                group_owner=str(room_data.get("ownerId") or "") or None,
            )

        cache_user_info(
            self._user_cache,
            sender_info,
            raw_data,
            self.bot_self_id,
            is_chat=False,
        )
        cache_room_info(self._user_cache, raw_data, self.bot_self_id)

        raw_text = raw_data.get("text", "")
        message_parts = []

        if raw_text:
            if self._bot_username and f"@{self._bot_username}" in raw_text:
                text_parts, processed_text = process_at_mention(
                    message,
                    raw_text,
                    self._bot_username,
                    self.bot_self_id,
                )
                message_parts.extend(text_parts)
            else:
                message.message.append(Comp.Plain(raw_text))
                message_parts.append(raw_text)

        files = raw_data.get("files", [])
        file_parts = await process_files(message, files)
        message_parts.extend(file_parts)

        message.message_str = (
            " ".join(part for part in message_parts if part.strip())
            if message_parts
            else ""
        )
        return message

    async def terminate(self) -> None:
        self._running = False
        if self.api:
            await self.api.close()
