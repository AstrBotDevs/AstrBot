import asyncio
import random
from typing import Any

import anyio

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSesion as MessageSession

from .misskey_api import MisskeyAPI

try:
    import magic
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
    is_valid_room_session_id,
    is_valid_user_session_id,
    process_at_mention,
    process_files,
    resolve_message_visibility,
    serialize_message_chain,
    summarize_note_for_context,
)

MAX_FILE_UPLOAD_COUNT = 16
DEFAULT_UPLOAD_CONCURRENCY = 3


@register_platform_adapter(
    "misskey",
    "Misskey 平台适配器",
    support_streaming_message=False,
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
        self.allow_insecure_downloads = bool(
            self.config.get("misskey_allow_insecure_downloads", False),
        )
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
        _md_bytes = self.config.get("misskey_max_download_bytes")
        try:
            self.max_download_bytes = int(_md_bytes) if _md_bytes is not None else None
        except Exception:
            self.max_download_bytes = None

        # 评论区原帖上下文注入
        self.include_reply_context = bool(
            self.config.get("misskey_include_reply_context", True),
        )
        try:
            self.reply_context_max_depth = max(
                0,
                min(int(self.config.get("misskey_reply_context_max_depth", 1)), 5),
            )
        except Exception:
            self.reply_context_max_depth = 1
        try:
            _raw_len = int(
                self.config.get("misskey_reply_context_max_text_length", 500)
            )
            # -1 表示不截断；否则强制下限 50 防止误填导致摘要几乎为空
            self.reply_context_max_text_length = (
                -1 if _raw_len < 0 else max(50, _raw_len)
            )
        except Exception:
            self.reply_context_max_text_length = 500

        self.api: MisskeyAPI | None = None
        self._running = False
        self.bot_self_id = ""
        self._bot_username = ""
        self._user_cache: dict[str, Any] = {}

    def meta(self) -> PlatformMetadata:
        default_config = {
            "misskey_instance_url": "",
            "misskey_token": "",
            "max_message_length": 3000,
            "misskey_default_visibility": "public",
            "misskey_local_only": False,
            "misskey_enable_chat": True,
            "misskey_allow_insecure_downloads": False,
            "misskey_download_timeout": 15,
            "misskey_download_chunk_size": 65536,
            "misskey_max_download_bytes": None,
            # 评论区原帖上下文注入
            "misskey_include_reply_context": True,
            "misskey_reply_context_max_depth": 1,
            "misskey_reply_context_max_text_length": 500,
        }
        default_config.update(self.config)
        return PlatformMetadata(
            name="misskey",
            description="Misskey 平台适配器",
            id=self.config.get("id", "misskey"),
            default_config_tmpl=default_config,
            support_streaming_message=False,
        )

    async def run(self) -> None:
        if not self.instance_url or not self.access_token:
            logger.error("[Misskey] 配置不完整,无法启动")
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

    async def _send_text_only_message(
        self,
        session_id: str,
        text: str,
        session,
        message_chain,
    ):
        """发送纯文本消息(无文件上传)"""
        if not self.api:
            return await super().send_by_session(session, message_chain)
        if session_id and is_valid_user_session_id(session_id):
            from .misskey_utils import extract_user_id_from_session_id

            user_id = extract_user_id_from_session_id(session_id)
            payload: dict[str, Any] = {"toUserId": user_id, "text": text}
            await self.api.send_message(payload)
        elif session_id and is_valid_room_session_id(session_id):
            from .misskey_utils import extract_room_id_from_session_id

            room_id = extract_room_id_from_session_id(session_id)
            payload = {"toRoomId": room_id, "text": text}
            await self.api.send_room_message(payload)
        return await super().send_by_session(session, message_chain)

    def _process_poll_data(
        self,
        message: AstrBotMessage,
        poll: dict[str, Any],
        message_parts: list[str],
    ) -> None:
        """处理投票数据,将其添加到消息中"""
        try:
            if not isinstance(message.raw_message, dict):
                message.raw_message = {}
            raw_message_dict = message.raw_message
            raw_message_dict["poll"] = poll
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
    ) -> None:
        if not self.api:
            logger.error("[Misskey] API 客户端未初始化")
            return await super().send_by_session(session, message_chain)
        try:
            session_id = session.session_id
            text, has_at_user = serialize_message_chain(message_chain.chain)
            if not has_at_user and session_id:
                user_id_for_cache = None
                if "%" in session_id:
                    parts = session_id.split("%")
                    if len(parts) >= 2:
                        user_id_for_cache = parts[1]
                user_info = None
                if user_id_for_cache:
                    user_info = self._user_cache.get(user_id_for_cache)
                text = add_at_mention_if_needed(text, user_info, has_at_user)
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
                    logger.warning("[Misskey] 消息内容为空且无文件组件,跳过发送")
                    return await super().send_by_session(session, message_chain)
                text = ""
            if len(text) > self.max_message_length:
                text = text[: self.max_message_length] + "..."
            file_ids: list[str] = []
            fallback_urls: list[str] = []
            if not self.enable_file_upload:
                return await self._send_text_only_message(
                    session_id,
                    text,
                    session,
                    message_chain,
                )
            MAX_UPLOAD_CONCURRENCY = 10
            upload_concurrency = int(
                self.config.get(
                    "misskey_upload_concurrency",
                    DEFAULT_UPLOAD_CONCURRENCY,
                ),
            )
            upload_concurrency = min(upload_concurrency, MAX_UPLOAD_CONCURRENCY)
            sem = asyncio.Semaphore(upload_concurrency)

            async def _upload_comp(comp) -> object | None:
                """组件上传函数:处理 URL(下载后上传)或本地文件(直接上传)"""
                from .misskey_utils import (
                    resolve_component_url_or_path,
                    upload_local_with_retries,
                )

                local_path = None
                try:
                    async with sem:
                        if not self.api:
                            return None
                        url_candidate, local_path = await resolve_component_url_or_path(
                            comp,
                        )
                        if not url_candidate and (not local_path):
                            return None
                        preferred_name = getattr(comp, "name", None) or getattr(
                            comp,
                            "file",
                            None,
                        )
                        if url_candidate:
                            result = await self.api.upload_and_find_file(
                                str(url_candidate),
                                preferred_name,
                                folder_id=self.upload_folder,
                            )
                            if isinstance(result, dict) and result.get("id"):
                                return str(result["id"])
                        if local_path:
                            file_id = await upload_local_with_retries(
                                self.api,
                                str(local_path),
                                preferred_name,
                                self.upload_folder,
                            )
                            if file_id:
                                return file_id
                        if hasattr(comp, "register_to_file_service"):
                            try:
                                url = await comp.register_to_file_service()
                                if url:
                                    return {"fallback_url": url}
                            except Exception:
                                pass
                        return None
                finally:
                    if local_path and isinstance(local_path, str):
                        data_temp = get_astrbot_temp_path()
                        if (
                            local_path.startswith(data_temp)
                            and await anyio.Path(local_path).exists()
                        ):
                            try:
                                await anyio.Path(local_path).unlink()
                                logger.debug(f"[Misskey] 已清理临时文件: {local_path}")
                            except Exception:
                                pass

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
                    continue
            if len(file_components) > MAX_FILE_UPLOAD_COUNT:
                logger.warning(
                    f"[Misskey] 文件数量超过限制 ({len(file_components)} > {MAX_FILE_UPLOAD_COUNT}),只上传前{MAX_FILE_UPLOAD_COUNT}个文件",
                )
                file_components = file_components[:MAX_FILE_UPLOAD_COUNT]
            upload_tasks = [_upload_comp(comp) for comp in file_components]
            try:
                results = await asyncio.gather(*upload_tasks) if upload_tasks else []
                for r in results:
                    if not r:
                        continue
                    if isinstance(r, dict):
                        r_dict = r
                        url = r_dict.get("fallback_url")
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
                logger.debug("[Misskey] 并发上传过程中出现异常,继续发送文本")
            if session_id and is_valid_room_session_id(session_id):
                from .misskey_utils import extract_room_id_from_session_id

                room_id = extract_room_id_from_session_id(session_id)
                if fallback_urls:
                    appended = "\n" + "\n".join(fallback_urls)
                    text = (text or "") + appended
                payload: dict[str, Any] = {"toRoomId": room_id, "text": text}
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
                    payload = {"toUserId": user_id, "text": text}
                    if file_ids:
                        payload["fileId"] = file_ids[0]
                        if len(file_ids) > 1:
                            logger.warning(
                                f"[Misskey] 聊天消息只支持单个文件,忽略其余 {len(file_ids) - 1} 个文件",
                            )
                    await self.api.send_message(payload)
                else:
                    user_id_for_cache = (
                        session_id.split("%")[1] if "%" in session_id else session_id
                    )
                    user_info_for_reply = self._user_cache.get(user_id_for_cache, {})
                    visibility, visible_user_ids = resolve_message_visibility(
                        user_id=user_id_for_cache,
                        user_cache=self._user_cache,
                        self_id=self.bot_self_id,
                        default_visibility=self.default_visibility,
                    )
                    logger.debug(
                        f"[Misskey] 解析可见性: visibility={visibility}, visible_user_ids={visible_user_ids}, session_id={session_id}, user_id_for_cache={user_id_for_cache}",
                    )
                    fields = self._extract_additional_fields(session, message_chain)
                    if fallback_urls:
                        appended = "\n" + "\n".join(fallback_urls)
                        text = (text or "") + appended
                    reply_id = user_info_for_reply.get("reply_to_note_id")
                    await self.api.create_note(
                        text=text,
                        visibility=visibility,
                        visible_user_ids=visible_user_ids,
                        file_ids=file_ids or None,
                        local_only=self.local_only,
                        reply_id=reply_id,
                        cw=fields["cw"],
                        poll=fields["poll"],
                        renote_id=fields["renote_id"],
                        channel_id=fields["channel_id"],
                    )
        except Exception as e:
            logger.error(f"[Misskey] 发送消息失败: {e}")
        return await super().send_by_session(session, message_chain)

    async def _resolve_reply_target(
        self,
        current: dict[str, Any],
    ) -> dict[str, Any] | None:
        """解析当前 note 的 reply 目标（被回复的原帖）。

        优先用 payload 中已展开的 `reply` 对象；缺失时通过 `replyId`
        走一次 notes/show API 回退。两者皆无返回 None。
        """
        reply_obj = current.get("reply")
        if isinstance(reply_obj, dict):
            return reply_obj
        reply_id = current.get("replyId")
        if reply_id and self.api:
            fetched = await self.api.get_note(str(reply_id))
            if isinstance(fetched, dict):
                return fetched
        return None

    async def _resolve_renote_target(
        self,
        current: dict[str, Any],
    ) -> dict[str, Any] | None:
        """解析当前 note 的 renote 目标（被引用/转发的原帖）。

        优先用 payload 中已展开的 `renote` 对象；缺失时通过 `renoteId`
        走一次 notes/show API 回退。两者皆无返回 None。
        """
        renote_obj = current.get("renote")
        if isinstance(renote_obj, dict):
            return renote_obj
        renote_id = current.get("renoteId")
        if renote_id and self.api:
            fetched = await self.api.get_note(str(renote_id))
            if isinstance(fetched, dict):
                return fetched
        return None

    async def _resolve_parent_note(
        self,
        current: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None]:
        """解析当前 note 的父帖（按优先级返回首个候选）。

        优先返回 reply 目标（被回复的原帖）；reply 不存在时回退到 renote 目标
        （被引用/转发的原帖）。reply-with-quote 场景：返回 reply，调用方需要
        再单独走 _resolve_renote_target 取引用帖。
        """
        reply_parent = await self._resolve_reply_target(current)
        if reply_parent is not None:
            return reply_parent, "被回复的原帖"
        renote_parent = await self._resolve_renote_target(current)
        if renote_parent is not None:
            return renote_parent, "被引用/转发的原帖"
        return None, None

    async def _build_parent_note_context(
        self,
        raw_data: dict[str, Any],
    ) -> str:
        """从一条 note 出发，向上追溯 reply / renote 链，返回拼好的纯文本上下文。

        - depth=0 时如果同时存在 reply + renote（reply-with-quote），两个都注入。
        - 顶层（depth=0）父帖作者是机器人自己时整段跳过，避免反馈循环。
        - 链中循环或 API 失败时静默截断，不阻断消息处理。
        - 返回值会被作为后缀拼到 ``message_str`` 末尾，因此自带前导分隔符
          ``\\n\\n---\\n``，让 LLM 看到的 prompt 形如「用户文本 \\n--- 父帖摘要」。
          放尾部而非头部是为了不破坏 wake_prefix 与命令前缀的 startswith 匹配。
        """
        if self.reply_context_max_depth <= 0:
            return ""

        # 既无 reply/replyId 又无 renote/renoteId 的独立帖子，没有父帖可追，直接退出，
        # 避免空循环以及无谓的 API 调用。
        if not (
            raw_data.get("reply")
            or raw_data.get("replyId")
            or raw_data.get("renote")
            or raw_data.get("renoteId")
        ):
            return ""

        blocks: list[str] = []
        visited: set[str] = set()
        current = raw_data
        labelled_by_depth = self.reply_context_max_depth > 1

        def append_summary_block(
            target: dict[str, Any],
            relation: str,
            depth_index: int,
        ) -> None:
            """生成摘要并追加到 blocks。两处调用（主父帖 / 引用帖）共用此 helper
            以避免「summarize + label + blocks.append」的重复逻辑。"""
            summary = summarize_note_for_context(
                target,
                max_text_length=self.reply_context_max_text_length,
            )
            if not summary:
                return
            label = relation
            if labelled_by_depth:
                label = f"{label} - 第{depth_index + 1}层"
            blocks.append(f"[{label}]\n{summary}")

        for depth in range(self.reply_context_max_depth):
            parent, relation = await self._resolve_parent_note(current)
            if not isinstance(parent, dict):
                break

            parent_id = str(parent.get("id") or "")
            if not parent_id or parent_id in visited:
                break
            visited.add(parent_id)

            if depth == 0:
                parent_uid = str((parent.get("user") or {}).get("id") or "")
                if parent_uid and parent_uid == self.bot_self_id:
                    return ""

            append_summary_block(parent, relation or "被回复的原帖", depth)

            # depth=0 且当前是 reply：如果还有 renote（reply-with-quote），也补上。
            # 走 _resolve_renote_target 而不是只检查 isinstance(current.get("renote"))，
            # 这样 payload 仅给 renoteId 时也能通过 API 回退拉取引用帖。
            if depth == 0 and relation == "被回复的原帖":
                renote_parent = await self._resolve_renote_target(current)
                if isinstance(renote_parent, dict):
                    renote_id = str(renote_parent.get("id") or "")
                    if renote_id and renote_id not in visited:
                        visited.add(renote_id)
                        append_summary_block(renote_parent, "被引用/转发的原帖", 0)

            current = parent

        if not blocks:
            return ""
        # 作为 message_str 的后缀返回，前导分隔符确保与用户原文有清晰边界
        return "\n\n---\n" + "\n\n".join(blocks)

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

        # 评论区原帖上下文：拼到 message_str 尾部，避免破坏 wake_prefix / 命令
        # 前缀 startswith 匹配（waking_check 与 star.filter.command 都是头部匹配）。
        # LLM 主路径直接读 message_str（astr_main_agent / agent third_party 都遍历
        # message chain 时只取多模态 Comp，忽略 Comp.Plain），所以这里不再把
        # parent_ctx 加到 message.message —— 那会变成读不到的死代码。
        parent_ctx = ""
        if self.include_reply_context:
            try:
                parent_ctx = await self._build_parent_note_context(raw_data)
            except Exception as e:
                logger.warning(f"[Misskey] 构建父帖上下文失败: {e}")
                parent_ctx = ""

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
        file_parts = process_files(message, files)
        message_parts.extend(file_parts)
        poll = raw_data.get("poll") or (
            raw_data.get("note", {}).get("poll")
            if isinstance(raw_data.get("note"), dict)
            else None
        )
        if poll and isinstance(poll, dict):
            self._process_poll_data(message, poll, message_parts)

        body = (
            " ".join(part for part in message_parts if part.strip())
            if message_parts
            else ""
        )
        message.message_str = body + parent_ctx if parent_ctx else body
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
        process_files(message, files, include_text_parts=False)
        message.message_str = raw_text or ""
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
        file_parts = process_files(message, files)
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

    def get_client(self) -> Any:
        return self.api
