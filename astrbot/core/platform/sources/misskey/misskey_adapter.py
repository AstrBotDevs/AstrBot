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

from .misskey_api import MisskeyAPI, APIError
import mimetypes
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
import os


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
        # whether to enable file upload to Misskey (drive/files/create)
        self.enable_file_upload = self.config.get("misskey_enable_file_upload", True)
        self.upload_folder = self.config.get("misskey_upload_folder")

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

        self.api = MisskeyAPI(self.instance_url, self.access_token)
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
                # register handlers for both plain event types and channel-prefixed variants
                streaming.add_message_handler("notification", self._handle_notification)
                streaming.add_message_handler("main:notification", self._handle_notification)
                if self.enable_chat:
                    streaming.add_message_handler("newChatMessage", self._handle_chat_message)
                    streaming.add_message_handler("messaging:newChatMessage", self._handle_chat_message)
                    streaming.add_message_handler("_debug", self._debug_handler)

                if await streaming.connect():
                    logger.info(
                        f"[Misskey] WebSocket 已连接 (尝试 #{connection_attempts})"
                    )
                    connection_attempts = 0  # 重置计数器
                    await streaming.subscribe_channel("main")
                    if self.enable_chat:
                        await streaming.subscribe_channel("messaging")
                        await streaming.subscribe_channel("messagingIndex")
                        logger.info("[Misskey] 聊天频道已订阅")

                    backoff_delay = 1.0  # 重置延迟
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
                        client=self.api,
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
                client=self.api,
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

            if not text or not text.strip():
                logger.warning("[Misskey] 消息内容为空，跳过发送")
                return await super().send_by_session(session, message_chain)

            if len(text) > self.max_message_length:
                text = text[: self.max_message_length] + "..."

            # handle file uploads concurrently with a semaphore limit
            file_ids: List[str] = []
            fallback_urls: List[str] = []

            if not self.enable_file_upload:
                logger.debug("[Misskey] 文件上传已在配置中禁用，跳过上传流程")
                # skip to sending text-only payloads
                if session_id and is_valid_user_session_id(session_id):
                    from .misskey_utils import extract_user_id_from_session_id

                    user_id = extract_user_id_from_session_id(session_id)
                    payload: Dict[str, Any] = {"toUserId": user_id, "text": text}
                    await self.api.send_message(payload)
                    return await super().send_by_session(session, message_chain)
                elif session_id and is_valid_room_session_id(session_id):
                    from .misskey_utils import extract_room_id_from_session_id

                    room_id = extract_room_id_from_session_id(session_id)
                    payload = {"toRoomId": room_id, "text": text}
                    await self.api.send_room_message(payload)
                    return await super().send_by_session(session, message_chain)
            upload_concurrency = int(self.config.get("misskey_upload_concurrency", 3))
            sem = asyncio.Semaphore(upload_concurrency)

            async def _upload_comp(comp) -> Optional[object]:
                upload_path = None
                def _detect_mime_and_ext(path: str) -> Optional[str]:
                    # Try python-magic first (from buffer), fallback to mimetypes
                    try:
                        if magic:
                            m = magic.Magic(mime=True)
                            mime = m.from_file(path)
                        else:
                            mime, _ = mimetypes.guess_type(path)
                    except Exception:
                        mime = None
                    if not mime:
                        return None
                    # map common mime to ext
                    mapping = {
                        "image/jpeg": ".jpg",
                        "image/jpg": ".jpg",
                        "image/png": ".png",
                        "image/gif": ".gif",
                        "text/plain": ".txt",
                        "application/pdf": ".pdf",
                    }
                    return mapping.get(mime, mimetypes.guess_extension(mime) or None)
                try:
                    if hasattr(comp, "convert_to_file_path"):
                        try:
                            upload_path = await comp.convert_to_file_path()
                        except Exception:
                            pass
                    if not upload_path and hasattr(comp, "get_file"):
                        try:
                            upload_path = await comp.get_file()
                        except Exception:
                            pass

                    if not upload_path:
                        return None

                    # upload under semaphore
                    async with sem:
                        if not self.api:
                            return None
                        try:
                            upload_result = await self.api.upload_file(
                                upload_path,
                                getattr(comp, "name", None) or getattr(comp, "file", None),
                                folder_id=self.upload_folder,
                            )
                            fid = None
                            if isinstance(upload_result, dict):
                                fid = (
                                    upload_result.get("id")
                                    or (upload_result.get("raw") or {}).get("createdFile", {}).get("id")
                                )
                            return str(fid) if fid else None
                        except Exception as e:
                            logger.error(f"[Misskey] 文件上传失败: {e}")
                            # If it's an unallowed file type, try detecting mime and retry with a suitable extension
                            tried_names = []
                            try:
                                msg = str(e).lower()
                                if "unallowed" in msg or "unallowed_file_type" in msg or (
                                    isinstance(e, APIError) and "unallowed" in str(e).lower()
                                ):
                                    base_name = os.path.basename(upload_path)
                                    name_root, ext = os.path.splitext(base_name)
                                    # try detect mime -> extension
                                    try_ext = _detect_mime_and_ext(upload_path)
                                    candidates = []
                                    if try_ext:
                                        candidates.append(try_ext)
                                    # fall back to a small set
                                    candidates.extend([".jpg", ".png", ".txt", ".bin"])
                                    # if ext is non-empty and short, include it first
                                    if ext and len(ext) <= 5 and ext not in candidates:
                                        candidates.insert(0, ext)
                                    for c in candidates:
                                        try_name = name_root + c
                                        if try_name in tried_names:
                                            continue
                                        tried_names.append(try_name)
                                        try:
                                            upload_result = await self.api.upload_file(upload_path, try_name, folder_id=self.upload_folder)
                                            fid = None
                                            if isinstance(upload_result, dict):
                                                fid = (
                                                    upload_result.get("id")
                                                    or (upload_result.get("raw") or {}).get("createdFile", {}).get("id")
                                                )
                                            if fid:
                                                logger.debug(f"[Misskey] 通过重试上传成功，使用文件名: {try_name}")
                                                return str(fid)
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                            # fallback: try register_to_file_service or get_file(allow_return_url=True)
                            try:
                                if hasattr(comp, "register_to_file_service"):
                                    try:
                                        url = await comp.register_to_file_service()
                                        if url:
                                            return {"fallback_url": url}
                                    except Exception:
                                        pass
                                if hasattr(comp, "get_file"):
                                    try:
                                        url_or_path = await comp.get_file(True)
                                        if url_or_path and str(url_or_path).startswith("http"):
                                            return {"fallback_url": url_or_path}
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            return None
                finally:
                    # cleanup temporary file if it was created under data/temp
                    try:
                        if upload_path:
                            data_temp = os.path.join(get_astrbot_data_path(), "temp")
                            if upload_path.startswith(data_temp) and os.path.exists(upload_path):
                                try:
                                    os.remove(upload_path)
                                    logger.debug(f"[Misskey] 已清理临时文件: {upload_path}")
                                except Exception:
                                    pass
                    except Exception:
                        pass

            upload_tasks = [ _upload_comp(comp) for comp in message_chain.chain ]
            fallback_urls: List[str] = []
            try:
                results = await asyncio.gather(*upload_tasks)
                for r in results:
                    if not r:
                        continue
                    if isinstance(r, dict) and r.get("fallback_url"):
                        url = r.get("fallback_url")
                        if url:
                            fallback_urls.append(str(url))
                    else:
                        # ensure we only append string file ids
                        try:
                            fid_str = str(r)
                        except Exception:
                            fid_str = None
                        if fid_str:
                            file_ids.append(fid_str)
            except Exception:
                logger.debug("[Misskey] 并发上传过程中出现异常，继续发送文本")

            if session_id and is_valid_user_session_id(session_id):
                from .misskey_utils import extract_room_id_from_session_id

                room_id = extract_room_id_from_session_id(session_id)
                if fallback_urls:
                    appended = "\n" + "\n".join(fallback_urls)
                    text = (text or "") + appended
                payload: Dict[str, Any] = {"toRoomId": room_id, "text": text}
                if file_ids:
                    payload["fileIds"] = file_ids
                await self.api.send_room_message(payload)
            else:
                visibility, visible_user_ids = resolve_message_visibility(
                    user_id=session_id,
                    user_cache=self._user_cache,
                    self_id=self.client_self_id,
                    default_visibility=self.default_visibility,
                )

                await self.api.create_note(
                    text,
                    visibility=visibility,
                    visible_user_ids=visible_user_ids,
                    file_ids=file_ids if file_ids else None,
                    local_only=self.local_only,
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

        # poll 支持：将 poll 结构保存在 message.raw_message / message.poll 中，并将格式化文本追加到消息链
        poll = raw_data.get("poll")
        if not poll and isinstance(raw_data.get("note"), dict):
            poll = raw_data["note"].get("poll")
        if poll and isinstance(poll, dict):
            # 保证 raw_message 是一个可写字典
            try:
                if not isinstance(message.raw_message, dict):
                    message.raw_message = {}
                message.raw_message["poll"] = poll
            except Exception:
                # 忽略设置失败，确保 raw_message 最少为 dict
                try:
                    message.raw_message = {}
                    message.raw_message["poll"] = poll
                except Exception:
                    pass
            # 方便插件直接读取，使用 setattr 以兼容不同 message 类型
            try:
                setattr(message, "poll", poll)
            except Exception:
                pass

            poll_text = format_poll(poll)
            if poll_text:
                message.message.append(Comp.Plain(poll_text))
                message_parts.append(poll_text)

        message.message_str = (
            " ".join(part for part in message_parts if part.strip())
            if message_parts
            else ""
        )
        return message
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
