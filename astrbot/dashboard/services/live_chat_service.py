from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
import uuid
import wave
from collections.abc import Awaitable, Callable
from typing import Any

import jwt
from starlette.websockets import WebSocketDisconnect

from astrbot import logger
from astrbot.core import sp
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    build_webchat_message_parts,
    create_attachment_part_from_existing_file,
    strip_message_parts_path_fields,
    webchat_message_parts_have_content,
)
from astrbot.core.platform.sources.webchat.request_flags import (
    resolve_webchat_request_flags,
)
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import to_utc_isoformat
from astrbot.dashboard.services.chat_service import (
    BotMessageAccumulator,
    build_bot_history_content,
    collect_plain_text_from_message_parts,
)

SendJson = Callable[[dict], Awaitable[None]]
ReceiveJson = Callable[[], Awaitable[dict]]
CloseWebSocket = Callable[[int, str], Awaitable[None]]


class LiveChatAuthError(Exception):
    pass


class LiveChatSession:
    """Live Chat 会话管理器"""

    def __init__(self, session_id: str, username: str) -> None:
        self.session_id = session_id
        self.username = username
        self.conversation_id = str(uuid.uuid4())
        self.is_speaking = False
        self.is_processing = False
        self.should_interrupt = False
        self.audio_frames: list[bytes] = []
        self.current_stamp: str | None = None
        self.temp_audio_path: str | None = None
        self.chat_subscriptions: dict[str, str] = {}
        self.chat_subscription_tasks: dict[str, asyncio.Task] = {}
        self.chat_request_tasks: dict[str, asyncio.Task] = {}
        self.interrupted_chat_requests: set[str] = set()
        self.ws_send_lock = asyncio.Lock()

    def start_speaking(self, stamp: str) -> None:
        self.is_speaking = True
        self.current_stamp = stamp
        self.audio_frames = []
        logger.debug(f"[Live Chat] {self.username} 开始说话 stamp={stamp}")

    def add_audio_frame(self, data: bytes) -> None:
        if self.is_speaking:
            self.audio_frames.append(data)

    async def end_speaking(self, stamp: str) -> tuple[str | None, float]:
        start_time = time.time()
        if not self.is_speaking or stamp != self.current_stamp:
            logger.warning(
                f"[Live Chat] stamp 不匹配或未在说话状态: {stamp} vs {self.current_stamp}"
            )
            return None, 0.0

        self.is_speaking = False

        if not self.audio_frames:
            logger.warning("[Live Chat] 没有音频帧数据")
            return None, 0.0

        try:
            temp_dir = get_astrbot_temp_path()
            os.makedirs(temp_dir, exist_ok=True)
            audio_path = os.path.join(temp_dir, f"live_audio_{uuid.uuid4()}.wav")

            with wave.open(audio_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                for frame in self.audio_frames:
                    wav_file.writeframes(frame)

            self.temp_audio_path = audio_path
            logger.info(
                f"[Live Chat] 音频文件已保存: {audio_path}, 大小: {os.path.getsize(audio_path)} bytes"
            )
            return audio_path, time.time() - start_time

        except Exception as exc:
            logger.error(f"[Live Chat] 组装 WAV 文件失败: {exc}", exc_info=True)
            return None, 0.0

    def cleanup(self) -> None:
        if self.temp_audio_path and os.path.exists(self.temp_audio_path):
            try:
                os.remove(self.temp_audio_path)
                logger.debug(f"[Live Chat] 已删除临时文件: {self.temp_audio_path}")
            except Exception as exc:
                logger.warning(f"[Live Chat] 删除临时文件失败: {exc}")
        self.temp_audio_path = None


class LiveChatService:
    def __init__(
        self,
        db: Any,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config
        self.plugin_manager = core_lifecycle.plugin_manager
        self.platform_history_mgr = core_lifecycle.platform_message_history_manager
        self.sessions: dict[str, LiveChatSession] = {}
        self.attachments_dir = os.path.join(get_astrbot_data_path(), "attachments")
        self.webchat_img_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")
        os.makedirs(self.attachments_dir, exist_ok=True)

    def authenticate_token(
        self,
        token: str | None,
        jwt_secret: str | None = None,
    ) -> str:
        if not token:
            raise LiveChatAuthError("Missing authentication token")
        jwt_secret = jwt_secret or self.config["dashboard"].get("jwt_secret")
        try:
            payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            return payload["username"]
        except jwt.ExpiredSignatureError as exc:
            raise LiveChatAuthError("Token expired") from exc
        except jwt.InvalidTokenError as exc:
            raise LiveChatAuthError("Invalid token") from exc

    def create_session(self, username: str) -> LiveChatSession:
        session_id = f"webchat_live!{username}!{uuid.uuid4()}"
        session = LiveChatSession(session_id, username)
        self.sessions[session_id] = session
        return session

    async def cleanup_session(self, session: LiveChatSession) -> None:
        if session.session_id in self.sessions:
            await self.cleanup_chat_subscriptions(session)
            session.cleanup()
            del self.sessions[session.session_id]

    async def run_websocket_session(
        self,
        *,
        token: str | None,
        force_ct: str | None,
        receive_json: ReceiveJson,
        send_json: SendJson,
        close: CloseWebSocket,
    ) -> None:
        try:
            username = self.authenticate_token(token)
        except LiveChatAuthError as exc:
            await close(1008, str(exc))
            return

        live_session = self.create_session(username)
        logger.info(f"[Live Chat] WebSocket 连接建立: {username}")

        def finish_chat_request(
            completed: asyncio.Task,
            request_id: str,
        ) -> None:
            """Release a multiplexed request task and observe its exception.

            Args:
                completed: Finished WebSocket chat request task.
                request_id: Request identifier used in the session task map.
            """
            if live_session.chat_request_tasks.get(request_id) is completed:
                live_session.chat_request_tasks.pop(request_id, None)
            try:
                completed.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.error(
                    f"[Live Chat] WebSocket chat request failed: {exc}",
                    exc_info=True,
                )

        try:
            while True:
                message = await receive_json()
                ct = force_ct or message.get("ct", "live")
                if ct == "chat":
                    if message.get("t") == "send":
                        request_id = str(message.get("message_id") or uuid.uuid4())
                        message["message_id"] = request_id
                        existing_task = live_session.chat_request_tasks.get(request_id)
                        if existing_task and not existing_task.done():
                            await self.send_chat_payload(
                                live_session,
                                {
                                    "ct": "chat",
                                    "t": "error",
                                    "data": "Duplicate active message_id",
                                    "code": "INVALID_MESSAGE_FORMAT",
                                    "message_id": request_id,
                                },
                                send_json,
                            )
                            continue
                        task = asyncio.create_task(
                            self.handle_chat_message(
                                live_session,
                                message,
                                send_json,
                            ),
                            name=f"chat_ws_request_{request_id}",
                        )
                        live_session.chat_request_tasks[request_id] = task
                        task.add_done_callback(
                            lambda completed, request_id=request_id: (
                                finish_chat_request(
                                    completed,
                                    request_id,
                                )
                            )
                        )
                    else:
                        await self.handle_chat_message(
                            live_session,
                            message,
                            send_json,
                        )
                else:
                    await self.handle_live_message(
                        live_session,
                        message,
                        send_json,
                    )

        except WebSocketDisconnect as exc:
            logger.debug(
                f"[Live Chat] WebSocket disconnected: {username}, code={exc.code}"
            )
        except Exception as exc:
            logger.error(f"[Live Chat] WebSocket 错误: {exc}", exc_info=True)

        finally:
            await self.cleanup_session(live_session)
            logger.info(f"[Live Chat] WebSocket 连接关闭: {username}")

    async def create_attachment_from_file(
        self, filename: str, attach_type: str, display_name: str | None = None
    ) -> dict | None:
        return await create_attachment_part_from_existing_file(
            filename,
            attach_type=attach_type,
            insert_attachment=self.db.insert_attachment,
            attachments_dir=self.attachments_dir,
            fallback_dirs=[self.webchat_img_dir],
            display_name=display_name,
        )

    @staticmethod
    def extract_web_search_refs(accumulated_text: str, accumulated_parts: list) -> dict:
        supported = [
            "web_search_baidu",
            "web_search_tavily",
            "web_search_bocha",
            "web_search_brave",
        ]
        web_search_results = {}
        tool_call_parts = [
            p
            for p in accumulated_parts
            if p.get("type") == "tool_call" and p.get("tool_calls")
        ]

        for part in tool_call_parts:
            for tool_call in part["tool_calls"]:
                if tool_call.get("name") not in supported or not tool_call.get(
                    "result"
                ):
                    continue
                try:
                    result_data = json.loads(tool_call["result"])
                    for item in result_data.get("results", []):
                        if idx := item.get("index"):
                            web_search_results[idx] = {
                                "url": item.get("url"),
                                "title": item.get("title"),
                                "snippet": item.get("snippet"),
                            }
                except (json.JSONDecodeError, KeyError):
                    pass

        if not web_search_results:
            return {}

        ref_indices = {
            match.strip() for match in re.findall(r"<ref>(.*?)</ref>", accumulated_text)
        }

        used_refs = []
        for ref_index in ref_indices:
            if ref_index not in web_search_results:
                continue
            payload = {"index": ref_index, **web_search_results[ref_index]}
            if favicon := sp.temporary_cache.get("_ws_favicon", {}).get(payload["url"]):
                payload["favicon"] = favicon
            used_refs.append(payload)

        return {"used": used_refs} if used_refs else {}

    async def save_bot_message(
        self,
        webchat_conv_id: str,
        message_parts: list[dict],
        agent_stats: dict,
        refs: dict,
        llm_checkpoint_id: str | None = None,
    ):
        new_his = build_bot_history_content(
            message_parts,
            agent_stats=agent_stats,
            refs=refs,
        )

        return await self.platform_history_mgr.insert(
            platform_id="webchat",
            user_id=webchat_conv_id,
            content=new_his,
            sender_id="bot",
            sender_name="bot",
            llm_checkpoint_id=llm_checkpoint_id,
        )

    async def send_chat_payload(
        self,
        session: LiveChatSession,
        payload: dict,
        send_json: SendJson,
    ) -> None:
        async with session.ws_send_lock:
            await send_json(payload)

    async def forward_chat_subscription(
        self,
        session: LiveChatSession,
        chat_session_id: str,
        request_id: str,
        send_json: SendJson,
    ) -> None:
        back_queue = webchat_queue_mgr.get_or_create_back_queue(
            request_id, chat_session_id
        )
        try:
            while True:
                result = await back_queue.get()
                if not result:
                    continue
                await self.send_chat_payload(
                    session, {"ct": "chat", **result}, send_json
                )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(
                f"[Live Chat] chat subscription forward failed ({chat_session_id}): {exc}",
                exc_info=True,
            )
        finally:
            webchat_queue_mgr.remove_back_queue(request_id)
            if session.chat_subscriptions.get(chat_session_id) == request_id:
                session.chat_subscriptions.pop(chat_session_id, None)
            session.chat_subscription_tasks.pop(chat_session_id, None)

    async def ensure_chat_subscription(
        self,
        session: LiveChatSession,
        chat_session_id: str,
        send_json: SendJson,
    ) -> str:
        existing_request_id = session.chat_subscriptions.get(chat_session_id)
        existing_task = session.chat_subscription_tasks.get(chat_session_id)
        if existing_request_id and existing_task and not existing_task.done():
            return existing_request_id

        request_id = f"ws_sub_{uuid.uuid4().hex}"
        session.chat_subscriptions[chat_session_id] = request_id
        task = asyncio.create_task(
            self.forward_chat_subscription(
                session,
                chat_session_id,
                request_id,
                send_json,
            ),
            name=f"chat_ws_sub_{chat_session_id}",
        )
        session.chat_subscription_tasks[chat_session_id] = task
        return request_id

    async def cleanup_chat_subscriptions(self, session: LiveChatSession) -> None:
        tasks = [
            *session.chat_subscription_tasks.values(),
            *session.chat_request_tasks.values(),
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        for request_id in list(session.chat_subscriptions.values()):
            webchat_queue_mgr.remove_back_queue(request_id)
        session.chat_subscriptions.clear()
        session.chat_subscription_tasks.clear()
        session.chat_request_tasks.clear()
        session.interrupted_chat_requests.clear()

    async def handle_chat_message(
        self,
        session: LiveChatSession,
        message: dict,
        send_json: SendJson,
    ) -> None:
        msg_type = message.get("t")
        message_id = str(message.get("message_id") or uuid.uuid4())
        request_metadata = (
            {"message_id": message_id}
            if msg_type == "send" or message.get("message_id")
            else {}
        )

        if msg_type == "bind":
            chat_session_id = message.get("session_id")
            if not isinstance(chat_session_id, str) or not chat_session_id:
                await self.send_chat_payload(
                    session,
                    {
                        "ct": "chat",
                        "t": "error",
                        "data": "session_id is required",
                        "code": "INVALID_MESSAGE_FORMAT",
                    },
                    send_json,
                )
                return

            request_id = await self.ensure_chat_subscription(
                session, chat_session_id, send_json
            )
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "type": "session_bound",
                    "session_id": chat_session_id,
                    "message_id": request_id,
                },
                send_json,
            )
            return

        if msg_type == "interrupt":
            if message.get("message_id"):
                session.interrupted_chat_requests.add(message_id)
            else:
                session.interrupted_chat_requests.update(
                    session.chat_request_tasks.keys()
                )
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "INTERRUPTED",
                    "code": "INTERRUPTED",
                    **request_metadata,
                },
                send_json,
            )
            return

        if msg_type != "send":
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": f"Unsupported message type: {msg_type}",
                    "code": "INVALID_MESSAGE_FORMAT",
                },
                send_json,
            )
            return

        payload = message.get("message")
        session_id = message.get("session_id") or session.session_id
        selected_provider = message.get("selected_provider")
        selected_model = message.get("selected_model")
        selected_stt_provider = message.get("selected_stt_provider")
        selected_tts_provider = message.get("selected_tts_provider")
        persona_prompt = message.get("persona_prompt")
        show_reasoning = message.get("show_reasoning")
        flags = resolve_webchat_request_flags(message)

        if not isinstance(payload, list):
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "message must be list",
                    "code": "INVALID_MESSAGE_FORMAT",
                    **request_metadata,
                },
                send_json,
            )
            return

        message_parts = await self.build_chat_message_parts(payload)
        has_content = webchat_message_parts_have_content(message_parts)
        if not has_content:
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "Message content is empty",
                    "code": "INVALID_MESSAGE_FORMAT",
                    **request_metadata,
                },
                send_json,
            )
            return

        await self.ensure_chat_subscription(session, session_id, send_json)

        back_queue = webchat_queue_mgr.get_or_create_back_queue(message_id, session_id)
        llm_checkpoint_id = str(uuid.uuid4())

        pending_bot_message_flusher = None
        try:
            chat_queue = webchat_queue_mgr.get_or_create_queue(session_id)
            await chat_queue.put(
                (
                    session.username,
                    session_id,
                    {
                        "message": message_parts,
                        "selected_provider": selected_provider,
                        "selected_model": selected_model,
                        "selected_stt_provider": selected_stt_provider,
                        "selected_tts_provider": selected_tts_provider,
                        "persona_prompt": persona_prompt,
                        "show_reasoning": show_reasoning,
                        "flags": flags,
                        "message_id": message_id,
                        "llm_checkpoint_id": llm_checkpoint_id,
                    },
                ),
            )

            message_parts_for_storage = strip_message_parts_path_fields(message_parts)
            saved_user_record = await self.platform_history_mgr.insert(
                platform_id="webchat",
                user_id=session_id,
                content={"type": "user", "message": message_parts_for_storage},
                sender_id=session.username,
                sender_name=session.username,
                llm_checkpoint_id=llm_checkpoint_id,
            )
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "type": "user_message_saved",
                    "data": {
                        "id": saved_user_record.id,
                        "created_at": to_utc_isoformat(saved_user_record.created_at),
                        "llm_checkpoint_id": llm_checkpoint_id,
                    },
                    **request_metadata,
                },
                send_json,
            )

            message_accumulator = BotMessageAccumulator()
            agent_stats = {}
            refs = {}

            async def flush_pending_bot_message():
                nonlocal message_accumulator, agent_stats, refs
                if not (message_accumulator.has_content() or refs or agent_stats):
                    return None

                message_parts_to_save = message_accumulator.build_message_parts(
                    include_pending_tool_calls=True
                )
                plain_text = collect_plain_text_from_message_parts(
                    message_parts_to_save
                )
                try:
                    extracted_refs = self.extract_web_search_refs(
                        plain_text,
                        message_parts_to_save,
                    )
                except Exception as exc:
                    logger.exception(
                        f"[Live Chat] Failed to extract web search refs: {exc}",
                        exc_info=True,
                    )
                    extracted_refs = refs

                saved_record = await self.save_bot_message(
                    session_id,
                    message_parts_to_save,
                    agent_stats,
                    extracted_refs,
                    llm_checkpoint_id,
                )
                message_accumulator = BotMessageAccumulator()
                agent_stats = {}
                refs = {}
                return saved_record

            pending_bot_message_flusher = flush_pending_bot_message

            async def send_attachment_saved_event(part: dict | None) -> None:
                if not part or not part.get("attachment_id") or not part.get("type"):
                    return

                await self.send_chat_payload(
                    session,
                    {
                        "ct": "chat",
                        "type": "attachment_saved",
                        "data": {
                            "id": part["attachment_id"],
                            "type": part["type"],
                        },
                        **request_metadata,
                    },
                    send_json,
                )

            while True:
                if message_id in session.interrupted_chat_requests:
                    session.interrupted_chat_requests.discard(message_id)
                    await flush_pending_bot_message()
                    break

                try:
                    result = await asyncio.wait_for(back_queue.get(), timeout=1)
                except asyncio.TimeoutError:
                    continue

                if not result:
                    continue
                if result.get("message_id") and result.get("message_id") != message_id:
                    continue

                result_text = result.get("data", "")
                result_type = result.get("type")
                streaming = result.get("streaming", False)
                chain_type = result.get("chain_type")
                if chain_type == "agent_stats":
                    try:
                        parsed_agent_stats = json.loads(result_text)
                        agent_stats = parsed_agent_stats
                        await self.send_chat_payload(
                            session,
                            {
                                "ct": "chat",
                                "type": "agent_stats",
                                "data": parsed_agent_stats,
                                **request_metadata,
                            },
                            send_json,
                        )
                    except Exception:
                        pass
                    continue

                outgoing = {"ct": "chat", **result}
                await self.send_chat_payload(session, outgoing, send_json)

                if result_type == "plain":
                    message_accumulator.add_plain(
                        result_text,
                        chain_type=chain_type,
                        streaming=streaming,
                    )
                elif result_type == "image":
                    filename = str(result_text).replace("[IMAGE]", "")
                    part = await self.create_attachment_from_file(filename, "image")
                    message_accumulator.add_attachment(part)
                    await send_attachment_saved_event(part)
                elif result_type == "record":
                    filename = str(result_text).replace("[RECORD]", "")
                    part = await self.create_attachment_from_file(filename, "record")
                    message_accumulator.add_attachment(part)
                    await send_attachment_saved_event(part)
                elif result_type == "file":
                    filename = str(result_text).replace("[FILE]", "", 1)
                    display_name = None
                    if "|" in filename:
                        filename, display_name = filename.split("|", 1)
                    part = await self.create_attachment_from_file(
                        filename,
                        "file",
                        display_name=display_name,
                    )
                    message_accumulator.add_attachment(part)
                    await send_attachment_saved_event(part)
                elif result_type == "video":
                    filename = str(result_text).replace("[VIDEO]", "", 1)
                    display_name = None
                    if "|" in filename:
                        filename, display_name = filename.split("|", 1)
                    part = await self.create_attachment_from_file(
                        filename,
                        "video",
                        display_name=display_name,
                    )
                    message_accumulator.add_attachment(part)
                    await send_attachment_saved_event(part)

                should_save = False
                if result_type == "end":
                    should_save = bool(
                        message_accumulator.has_content() or refs or agent_stats
                    )
                elif (streaming and result_type == "complete") or not streaming:
                    if chain_type not in (
                        "tool_call",
                        "tool_call_result",
                        "agent_stats",
                    ):
                        should_save = True

                if should_save:
                    saved_record = await flush_pending_bot_message()
                    if saved_record:
                        await self.send_chat_payload(
                            session,
                            {
                                "ct": "chat",
                                "type": "message_saved",
                                "data": {
                                    "id": saved_record.id,
                                    "created_at": to_utc_isoformat(
                                        saved_record.created_at
                                    ),
                                    "llm_checkpoint_id": llm_checkpoint_id,
                                },
                                **request_metadata,
                            },
                            send_json,
                        )

                if result_type == "end":
                    break

        except Exception as exc:
            logger.error(f"[Live Chat] 处理 chat 消息失败: {exc}", exc_info=True)
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": f"处理失败: {str(exc)}",
                    "code": "PROCESSING_ERROR",
                    **request_metadata,
                },
                send_json,
            )
        finally:
            try:
                if pending_bot_message_flusher is not None:
                    await pending_bot_message_flusher()
            except Exception as exc:
                logger.exception(
                    f"[Live Chat] Failed to persist pending chat message: {exc}",
                    exc_info=True,
                )
            session.interrupted_chat_requests.discard(message_id)
            webchat_queue_mgr.remove_back_queue(message_id)

    async def build_chat_message_parts(self, message: list[dict]) -> list[dict]:
        return await build_webchat_message_parts(
            message,
            get_attachment_by_id=self.db.get_attachment_by_id,
            strict=False,
        )

    async def handle_live_message(
        self,
        session: LiveChatSession,
        message: dict,
        send_json: SendJson,
    ) -> None:
        msg_type = message.get("t")

        if msg_type == "start_speaking":
            stamp = message.get("stamp")
            if not stamp:
                logger.warning("[Live Chat] start_speaking 缺少 stamp")
                return
            session.start_speaking(stamp)
            return

        if msg_type == "speaking_part":
            audio_data_b64 = message.get("data")
            if not audio_data_b64:
                return
            try:
                audio_data = base64.b64decode(audio_data_b64)
                session.add_audio_frame(audio_data)
            except Exception as exc:
                logger.error(f"[Live Chat] 解码音频数据失败: {exc}")
            return

        if msg_type == "end_speaking":
            stamp = message.get("stamp")
            if not stamp:
                logger.warning("[Live Chat] end_speaking 缺少 stamp")
                return

            audio_path, assemble_duration = await session.end_speaking(stamp)
            if not audio_path:
                await send_json({"t": "error", "data": "音频组装失败"})
                return

            await self.process_audio(session, audio_path, assemble_duration, send_json)
            return

        if msg_type == "interrupt":
            session.should_interrupt = True
            logger.info(f"[Live Chat] 用户打断: {session.username}")

    async def process_audio(
        self,
        session: LiveChatSession,
        audio_path: str,
        assemble_duration: float,
        send_json: SendJson,
    ) -> None:
        try:
            await send_json(
                {"t": "metrics", "data": {"wav_assemble_time": assemble_duration}}
            )
            wav_assembly_finish_time = time.time()

            session.is_processing = True
            session.should_interrupt = False

            ctx = self.plugin_manager.context
            stt_provider = ctx.provider_manager.stt_provider_insts[0]

            if not stt_provider:
                logger.error("[Live Chat] STT Provider 未配置")
                await send_json({"t": "error", "data": "语音识别服务未配置"})
                return

            await send_json({"t": "metrics", "data": {"stt": stt_provider.meta().type}})

            user_text = await stt_provider.get_text(audio_path)
            if not user_text:
                logger.warning("[Live Chat] STT 识别结果为空")
                return

            logger.info(f"[Live Chat] STT 结果: {user_text}")

            await send_json(
                {
                    "t": "user_msg",
                    "data": {"text": user_text, "ts": int(time.time() * 1000)},
                }
            )

            conversation_id = session.conversation_id
            queue = webchat_queue_mgr.get_or_create_queue(conversation_id)

            message_id = str(uuid.uuid4())
            payload = {
                "message_id": message_id,
                "message": [{"type": "plain", "text": user_text}],
                "action_type": "live",
            }

            await queue.put((session.username, conversation_id, payload))
            back_queue = webchat_queue_mgr.get_or_create_back_queue(
                message_id, conversation_id
            )

            bot_text = ""
            audio_playing = False

            try:
                while True:
                    if session.should_interrupt:
                        logger.info("[Live Chat] 检测到用户打断")
                        await send_json({"t": "stop_play"})
                        await self.save_interrupted_message(
                            session, user_text, bot_text
                        )
                        while not back_queue.empty():
                            try:
                                back_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                        break

                    try:
                        result = await asyncio.wait_for(back_queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue

                    if not result:
                        continue

                    result_message_id = result.get("message_id")
                    if result_message_id != message_id:
                        logger.warning(
                            f"[Live Chat] 消息 ID 不匹配: {result_message_id} != {message_id}"
                        )
                        continue

                    result_type = result.get("type")
                    result_chain_type = result.get("chain_type")
                    data = result.get("data", "")

                    if result_chain_type == "agent_stats":
                        try:
                            stats = json.loads(data)
                            await send_json(
                                {
                                    "t": "metrics",
                                    "data": {
                                        "llm_ttft": stats.get("time_to_first_token", 0),
                                        "llm_total_time": stats.get("end_time", 0)
                                        - stats.get("start_time", 0),
                                    },
                                }
                            )
                        except Exception as exc:
                            logger.error(f"[Live Chat] 解析 AgentStats 失败: {exc}")
                        continue

                    if result_chain_type == "tts_stats":
                        try:
                            stats = json.loads(data)
                            await send_json(
                                {
                                    "t": "metrics",
                                    "data": stats,
                                }
                            )
                        except Exception as exc:
                            logger.error(f"[Live Chat] 解析 TTSStats 失败: {exc}")
                        continue

                    if result_type == "plain":
                        bot_text += data

                    elif result_type == "audio_chunk":
                        if not audio_playing:
                            audio_playing = True
                            logger.debug("[Live Chat] 开始播放音频流")

                            speak_to_first_frame_latency = (
                                time.time() - wav_assembly_finish_time
                            )
                            await send_json(
                                {
                                    "t": "metrics",
                                    "data": {
                                        "speak_to_first_frame": speak_to_first_frame_latency
                                    },
                                }
                            )

                        text = result.get("text")
                        if text:
                            await send_json(
                                {
                                    "t": "bot_text_chunk",
                                    "data": {"text": text},
                                }
                            )

                        await send_json(
                            {
                                "t": "response",
                                "data": data,
                            }
                        )

                    elif result_type in ["complete", "end"]:
                        logger.info(f"[Live Chat] Bot 回复完成: {bot_text}")

                        if not audio_playing:
                            await send_json(
                                {
                                    "t": "bot_msg",
                                    "data": {
                                        "text": bot_text,
                                        "ts": int(time.time() * 1000),
                                    },
                                }
                            )

                        await send_json({"t": "end"})

                        wav_to_tts_duration = time.time() - wav_assembly_finish_time
                        await send_json(
                            {
                                "t": "metrics",
                                "data": {"wav_to_tts_total_time": wav_to_tts_duration},
                            }
                        )
                        break
            finally:
                webchat_queue_mgr.remove_back_queue(message_id)

        except Exception as exc:
            logger.error(f"[Live Chat] 处理音频失败: {exc}", exc_info=True)
            await send_json({"t": "error", "data": f"处理失败: {str(exc)}"})

        finally:
            session.is_processing = False
            session.should_interrupt = False

    @staticmethod
    async def save_interrupted_message(
        session: LiveChatSession, user_text: str, bot_text: str
    ) -> None:
        interrupted_text = bot_text + " [用户打断]"
        logger.info(f"[Live Chat] 保存打断消息: {interrupted_text}")

        try:
            timestamp = int(time.time() * 1000)
            logger.info(
                f"[Live Chat] 用户消息: {user_text} (session: {session.session_id}, ts: {timestamp})"
            )
            if bot_text:
                logger.info(
                    f"[Live Chat] Bot 消息（打断）: {interrupted_text} (session: {session.session_id}, ts: {timestamp})"
                )
        except Exception as exc:
            logger.error(f"[Live Chat] 记录消息失败: {exc}", exc_info=True)


__all__ = ["LiveChatAuthError", "LiveChatService", "LiveChatSession"]
