import asyncio
import random
import json
from typing import Dict, Any, Optional, Awaitable, List

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSession
import astrbot.api.message_components as Comp

from .misskey_api import MisskeyAPI
import os

try:
    import magic  # type: ignore
except Exception:
    magic = None

from .misskey_event import MisskeyPlatformEvent
from .misskey_utils import (
    serialize_message_chain,
    resolve_message_visibility,
    is_valid_user_session_id,
    is_valid_room_session_id,
    add_at_mention_if_needed,
    process_files,
    extract_sender_info,
    create_base_message,
    process_at_mention,
    format_poll,
    cache_user_info,
    cache_room_info,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

# Constants
MAX_FILE_UPLOAD_COUNT = 16
DEFAULT_UPLOAD_CONCURRENCY = 3


@register_platform_adapter("misskey", "Misskey 平台适配器")
class MisskeyPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config or {}
        self.settings = platform_settings or {}
        self.instance_url = self.config.get("misskey_instance_url", "")
        self.access_token = self.config.get("misskey_token", "")
        self.max_message_length = self.config.get("max_message_length", 3000)
        self.default_visibility = self.config.get(
            "misskey_default_visibility", "public"
        )
        self.local_only = self.config.get("misskey_local_only", False)
        self.enable_chat = self.config.get("misskey_enable_chat", True)
        self.enable_file_upload = self.config.get("misskey_enable_file_upload", True)
        self.upload_folder = self.config.get("misskey_upload_folder")

        # download / security related options (exposed to platform_config)
        self.allow_insecure_downloads = bool(
            self.config.get("misskey_allow_insecure_downloads", False)
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

        self.unique_session = platform_settings["unique_session"]

        self.api: Optional[MisskeyAPI] = None
        self._running = False
        self.client_self_id = ""
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
        )

    async def run(self):
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
            self.client_self_id = str(user_info.get("id", ""))
            self._bot_username = user_info.get("username", "")
            logger.info(
                f"[Misskey] 已连接用户: {self._bot_username} (ID: {self.client_self_id})"
            )
        except Exception as e:
            logger.error(f"[Misskey] 获取用户信息失败: {e}")
            self._running = False
            return

        await self._start_websocket_connection()

    def _register_event_handlers(self, streaming):
        """注册事件处理器"""
        streaming.add_message_handler("notification", self._handle_notification)
        streaming.add_message_handler("main:notification", self._handle_notification)

        if self.enable_chat:
            streaming.add_message_handler("newChatMessage", self._handle_chat_message)
            streaming.add_message_handler(
                "messaging:newChatMessage", self._handle_chat_message
            )
            streaming.add_message_handler("_debug", self._debug_handler)

    async def _send_text_only_message(
        self, session_id: str, text: str, session, message_chain
    ):
        """发送纯文本消息（无文件上传）"""
        if not self.api:
            return await super().send_by_session(session, message_chain)

        if session_id and is_valid_user_session_id(session_id):
            from .misskey_utils import extract_user_id_from_session_id

            user_id = extract_user_id_from_session_id(session_id)
            payload: Dict[str, Any] = {"toUserId": user_id, "text": text}
            await self.api.send_message(payload)
        elif session_id and is_valid_room_session_id(session_id):
            from .misskey_utils import extract_room_id_from_session_id

            room_id = extract_room_id_from_session_id(session_id)
            payload = {"toRoomId": room_id, "text": text}
            await self.api.send_room_message(payload)

        return await super().send_by_session(session, message_chain)

    def _process_poll_data(
        self, message: AstrBotMessage, poll: Dict[str, Any], message_parts: List[str]
    ):
        """处理投票数据，将其添加到消息中"""
        try:
            if not isinstance(message.raw_message, dict):
                message.raw_message = {}
            message.raw_message["poll"] = poll
            setattr(message, "poll", poll)
        except Exception:
            pass

        poll_text = format_poll(poll)
        if poll_text:
            message.message.append(Comp.Plain(poll_text))
            message_parts.append(poll_text)

    def _extract_additional_fields(self, session, message_chain) -> Dict[str, Any]:
        """从会话和消息链中提取额外字段"""
        fields = {"cw": None, "poll": None, "renote_id": None, "channel_id": None}

        for comp in message_chain.chain:
            if hasattr(comp, "cw") and getattr(comp, "cw", None):
                fields["cw"] = getattr(comp, "cw")
                break

        if hasattr(session, "extra_data") and isinstance(
            getattr(session, "extra_data", None), dict
        ):
            extra_data = getattr(session, "extra_data")
            fields.update(
                {
                    "poll": extra_data.get("poll"),
                    "renote_id": extra_data.get("renote_id"),
                    "channel_id": extra_data.get("channel_id"),
                }
            )

        return fields

    async def _start_websocket_connection(self):
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
                        f"[Misskey] WebSocket 已连接 (尝试 #{connection_attempts})"
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
                        f"[Misskey] WebSocket 连接失败 (尝试 #{connection_attempts})"
                    )

            except Exception as e:
                logger.error(
                    f"[Misskey] WebSocket 异常 (尝试 #{connection_attempts}): {e}"
                )

            if self._running:
                jitter = random.uniform(0, 1.0)
                sleep_time = backoff_delay + jitter
                logger.info(
                    f"[Misskey] {sleep_time:.1f}秒后重连 (下次尝试 #{connection_attempts + 1})"
                )
                await asyncio.sleep(sleep_time)
                backoff_delay = min(backoff_delay * backoff_multiplier, max_backoff)

    async def _handle_notification(self, data: Dict[str, Any]):
        try:
            logger.debug(
                f"[Misskey] 收到通知事件:\n{json.dumps(data, indent=2, ensure_ascii=False)}"
            )
            notification_type = data.get("type")
            if notification_type in ["mention", "reply", "quote"]:
                note = data.get("note")
                if note and self._is_bot_mentioned(note):
                    logger.info(
                        f"[Misskey] 处理贴文提及: {note.get('text', '')[:50]}..."
                    )
                    message = await self.convert_message(note)
                    event = MisskeyPlatformEvent(
                        message_str=message.message_str,
                        message_obj=message,
                        platform_meta=self.meta(),
                        session_id=message.session_id,
                        client=self,
                    )
                    self.commit_event(event)
        except Exception as e:
            logger.error(f"[Misskey] 处理通知失败: {e}")

    async def _handle_chat_message(self, data: Dict[str, Any]):
        try:
            logger.debug(
                f"[Misskey] 收到聊天事件数据:\n{json.dumps(data, indent=2, ensure_ascii=False)}"
            )

            sender_id = str(
                data.get("fromUserId", "") or data.get("fromUser", {}).get("id", "")
            )
            if sender_id == self.client_self_id:
                return

            room_id = data.get("toRoomId")
            if room_id:
                raw_text = data.get("text", "")
                logger.debug(
                    f"[Misskey] 检查群聊消息: '{raw_text}', 机器人用户名: '{self._bot_username}'"
                )

                message = await self.convert_room_message(data)
                logger.info(f"[Misskey] 处理群聊消息: {message.message_str[:50]}...")
            else:
                message = await self.convert_chat_message(data)
                logger.info(f"[Misskey] 处理私聊消息: {message.message_str[:50]}...")

            event = MisskeyPlatformEvent(
                message_str=message.message_str,
                message_obj=message,
                platform_meta=self.meta(),
                session_id=message.session_id,
                client=self,
            )
            self.commit_event(event)
        except Exception as e:
            logger.error(f"[Misskey] 处理聊天消息失败: {e}")

    async def _debug_handler(self, data: Dict[str, Any]):
        logger.debug(
            f"[Misskey] 收到未处理事件:\n{json.dumps(data, indent=2, ensure_ascii=False)}"
        )

    def _is_bot_mentioned(self, note: Dict[str, Any]) -> bool:
        text = note.get("text", "")
        if not text:
            return False

        mentions = note.get("mentions", [])
        if self._bot_username and f"@{self._bot_username}" in text:
            return True
        if self.client_self_id in [str(uid) for uid in mentions]:
            return True

        reply = note.get("reply")
        if reply and isinstance(reply, dict):
            reply_user_id = str(reply.get("user", {}).get("id", ""))
            if reply_user_id == self.client_self_id:
                return bool(self._bot_username and f"@{self._bot_username}" in text)

        return False

    async def send_by_session(
        self, session: MessageSession, message_chain: MessageChain
    ) -> Awaitable[Any]:
        if not self.api:
            logger.error("[Misskey] API 客户端未初始化")
            return await super().send_by_session(session, message_chain)

        try:
            session_id = session.session_id

            text, has_at_user = serialize_message_chain(message_chain.chain)

            if not has_at_user and session_id:
                user_info = self._user_cache.get(session_id)
                text = add_at_mention_if_needed(text, user_info, has_at_user)

            # 检查是否有文件组件
            has_file_components = any(
                isinstance(comp, Comp.Image)
                or isinstance(comp, Comp.File)
                or hasattr(comp, "convert_to_file_path")
                or hasattr(comp, "get_file")
                or any(
                    hasattr(comp, a) for a in ("file", "url", "path", "src", "source")
                )
                for comp in message_chain.chain
            )

            if not text or not text.strip():
                if not has_file_components:
                    logger.warning("[Misskey] 消息内容为空且无文件组件，跳过发送")
                    return await super().send_by_session(session, message_chain)
                else:
                    text = ""

            if len(text) > self.max_message_length:
                text = text[: self.max_message_length] + "..."

            file_ids: List[str] = []
            fallback_urls: List[str] = []

            if not self.enable_file_upload:
                return await self._send_text_only_message(
                    session_id, text, session, message_chain
                )

            MAX_UPLOAD_CONCURRENCY = 10
            upload_concurrency = int(
                self.config.get(
                    "misskey_upload_concurrency", DEFAULT_UPLOAD_CONCURRENCY
                )
            )
            upload_concurrency = min(upload_concurrency, MAX_UPLOAD_CONCURRENCY)
            sem = asyncio.Semaphore(upload_concurrency)

            async def _upload_comp(comp) -> Optional[object]:
                """组件上传函数：处理 URL（下载后上传）或本地文件（直接上传）"""
                from .misskey_utils import (
                    resolve_component_url_or_path,
                    upload_local_with_retries,
                )

                local_path = None
                try:
                    async with sem:
                        if not self.api:
                            return None

                        # 解析组件的 URL 或本地路径
                        url_candidate, local_path = await resolve_component_url_or_path(
                            comp
                        )

                        if not url_candidate and not local_path:
                            return None

                        preferred_name = getattr(comp, "name", None) or getattr(
                            comp, "file", None
                        )

                        # URL 上传：下载后本地上传
                        if url_candidate:
                            result = await self.api.upload_and_find_file(
                                str(url_candidate),
                                preferred_name,
                                folder_id=self.upload_folder,
                            )
                            if isinstance(result, dict) and result.get("id"):
                                return str(result["id"])

                        # 本地文件上传
                        if local_path:
                            file_id = await upload_local_with_retries(
                                self.api,
                                str(local_path),
                                preferred_name,
                                self.upload_folder,
                            )
                            if file_id:
                                return file_id

                        # 所有上传都失败，尝试获取 URL 作为回退
                        if hasattr(comp, "register_to_file_service"):
                            try:
                                url = await comp.register_to_file_service()
                                if url:
                                    return {"fallback_url": url}
                            except Exception:
                                pass

                        return None

                finally:
                    # 清理临时文件
                    if local_path and isinstance(local_path, str):
                        data_temp = os.path.join(get_astrbot_data_path(), "temp")
                        if local_path.startswith(data_temp) and os.path.exists(
                            local_path
                        ):
                            try:
                                os.remove(local_path)
                                logger.debug(f"[Misskey] 已清理临时文件: {local_path}")
                            except Exception:
                                pass

            # 收集所有可能包含文件/URL信息的组件：支持异步接口或同步字段
            file_components = []
            for comp in message_chain.chain:
                try:
                    if (
                        isinstance(comp, Comp.Image)
                        or isinstance(comp, Comp.File)
                        or hasattr(comp, "convert_to_file_path")
                        or hasattr(comp, "get_file")
                        or any(
                            hasattr(comp, a)
                            for a in ("file", "url", "path", "src", "source")
                        )
                    ):
                        file_components.append(comp)
                except Exception:
                    # 保守跳过无法访问属性的组件
                    continue

            if len(file_components) > MAX_FILE_UPLOAD_COUNT:
                logger.warning(
                    f"[Misskey] 文件数量超过限制 ({len(file_components)} > {MAX_FILE_UPLOAD_COUNT})，只上传前{MAX_FILE_UPLOAD_COUNT}个文件"
                )
                file_components = file_components[:MAX_FILE_UPLOAD_COUNT]

            upload_tasks = [_upload_comp(comp) for comp in file_components]

            try:
                results = await asyncio.gather(*upload_tasks) if upload_tasks else []
                for r in results:
                    if not r:
                        continue
                    if isinstance(r, dict) and r.get("fallback_url"):
                        url = r.get("fallback_url")
                        if url:
                            fallback_urls.append(str(url))
                    else:
                        try:
                            fid_str = str(r)
                            if fid_str:
                                file_ids.append(fid_str)
                        except Exception:
                            pass
            except Exception:
                logger.debug("[Misskey] 并发上传过程中出现异常，继续发送文本")

            if session_id and is_valid_room_session_id(session_id):
                from .misskey_utils import extract_room_id_from_session_id

                room_id = extract_room_id_from_session_id(session_id)
                if fallback_urls:
                    appended = "\n" + "\n".join(fallback_urls)
                    text = (text or "") + appended
                payload: Dict[str, Any] = {"toRoomId": room_id, "text": text}
                if file_ids:
                    payload["fileIds"] = file_ids
                await self.api.send_room_message(payload)
            elif session_id:
                from .misskey_utils import (
                    extract_user_id_from_session_id,
                    is_valid_chat_session_id,
                )

                if is_valid_chat_session_id(session_id):
                    user_id = extract_user_id_from_session_id(session_id)
                    if fallback_urls:
                        appended = "\n" + "\n".join(fallback_urls)
                        text = (text or "") + appended
                    payload: Dict[str, Any] = {"toUserId": user_id, "text": text}
                    if file_ids:
                        # 聊天消息只支持单个文件，使用 fileId 而不是 fileIds
                        payload["fileId"] = file_ids[0]
                        if len(file_ids) > 1:
                            logger.warning(
                                f"[Misskey] 聊天消息只支持单个文件，忽略其余 {len(file_ids) - 1} 个文件"
                            )
                    await self.api.send_message(payload)
                else:
                    # 回退到发帖逻辑
                    # 去掉 session_id 中的 note% 前缀以匹配 user_cache 的键格式
                    user_id_for_cache = (
                        session_id.split("%")[1] if "%" in session_id else session_id
                    )
                    visibility, visible_user_ids = resolve_message_visibility(
                        user_id=user_id_for_cache,
                        user_cache=self._user_cache,
                        self_id=self.client_self_id,
                        default_visibility=self.default_visibility,
                    )
                    logger.debug(
                        f"[Misskey] 解析可见性: visibility={visibility}, visible_user_ids={visible_user_ids}, session_id={session_id}, user_id_for_cache={user_id_for_cache}"
                    )

                    fields = self._extract_additional_fields(session, message_chain)
                    if fallback_urls:
                        appended = "\n" + "\n".join(fallback_urls)
                        text = (text or "") + appended

                    await self.api.create_note(
                        text=text,
                        visibility=visibility,
                        visible_user_ids=visible_user_ids,
                        file_ids=file_ids or None,
                        local_only=self.local_only,
                        cw=fields["cw"],
                        poll=fields["poll"],
                        renote_id=fields["renote_id"],
                        channel_id=fields["channel_id"],
                    )

        except Exception as e:
            logger.error(f"[Misskey] 发送消息失败: {e}")

        return await super().send_by_session(session, message_chain)

    async def convert_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        """将 Misskey 贴文数据转换为 AstrBotMessage 对象"""
        sender_info = extract_sender_info(raw_data, is_chat=False)
        message = create_base_message(
            raw_data,
            sender_info,
            self.client_self_id,
            is_chat=False,
            unique_session=self.unique_session,
        )
        cache_user_info(
            self._user_cache, sender_info, raw_data, self.client_self_id, is_chat=False
        )

        message_parts = []
        raw_text = raw_data.get("text", "")

        if raw_text:
            text_parts, processed_text = process_at_mention(
                message, raw_text, self._bot_username, self.client_self_id
            )
            message_parts.extend(text_parts)

        files = raw_data.get("files", [])
        file_parts = process_files(message, files)
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

    async def convert_chat_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        """将 Misskey 聊天消息数据转换为 AstrBotMessage 对象"""
        sender_info = extract_sender_info(raw_data, is_chat=True)
        message = create_base_message(
            raw_data,
            sender_info,
            self.client_self_id,
            is_chat=True,
            unique_session=self.unique_session,
        )
        cache_user_info(
            self._user_cache, sender_info, raw_data, self.client_self_id, is_chat=True
        )

        raw_text = raw_data.get("text", "")
        if raw_text:
            message.message.append(Comp.Plain(raw_text))

        files = raw_data.get("files", [])
        process_files(message, files, include_text_parts=False)

        message.message_str = raw_text if raw_text else ""
        return message

    async def convert_room_message(self, raw_data: Dict[str, Any]) -> AstrBotMessage:
        """将 Misskey 群聊消息数据转换为 AstrBotMessage 对象"""
        sender_info = extract_sender_info(raw_data, is_chat=True)
        room_id = raw_data.get("toRoomId", "")
        message = create_base_message(
            raw_data,
            sender_info,
            self.client_self_id,
            is_chat=False,
            room_id=room_id,
            unique_session=self.unique_session,
        )

        cache_user_info(
            self._user_cache, sender_info, raw_data, self.client_self_id, is_chat=False
        )
        cache_room_info(self._user_cache, raw_data, self.client_self_id)

        raw_text = raw_data.get("text", "")
        message_parts = []

        if raw_text:
            if self._bot_username and f"@{self._bot_username}" in raw_text:
                text_parts, processed_text = process_at_mention(
                    message, raw_text, self._bot_username, self.client_self_id
                )
                message_parts.extend(text_parts)
            else:
                message.message.append(Comp.Plain(raw_text))
                message_parts.append(raw_text)

        files = raw_data.get("files", [])
        file_parts = process_files(message, files)
        message_parts.extend(file_parts)

        message.message_str = (
            " ".join(part for part in message_parts if part.strip())
            if message_parts
            else ""
        )
        return message

    async def terminate(self):
        self._running = False
        if self.api:
            await self.api.close()

    def get_client(self) -> Any:
        return self.api
