import asyncio
import json
import os
import re
import time
import uuid
import wave
from datetime import timezone
from typing import Any

import jwt
from quart import websocket

from astrbot import logger
from astrbot.core import sp
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    build_webchat_message_parts,
    create_attachment_part_from_existing_file,
    strip_message_parts_path_fields,
    webchat_message_parts_have_content,
)
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path

from .route import Route, RouteContext


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
        self.ws_send_lock = asyncio.Lock()

    def start_speaking(self, stamp: str) -> None:
        """开始说话"""
        self.is_speaking = True
        self.current_stamp = stamp
        self.audio_frames = []
        logger.debug(f"[Live Chat] {self.username} 开始说话 stamp={stamp}")

    def add_audio_frame(self, data: bytes) -> None:
        """添加音频帧"""
        if self.is_speaking:
            self.audio_frames.append(data)

    async def end_speaking(self, stamp: str) -> tuple[str | None, float]:
        """结束说话，返回组装的 WAV 文件路径和耗时"""
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

        # 组装 WAV 文件
        try:
            temp_dir = get_astrbot_temp_path()
            os.makedirs(temp_dir, exist_ok=True)
            audio_path = os.path.join(temp_dir, f"live_audio_{uuid.uuid4()}.wav")

            # 假设前端发送的是 PCM 数据，采样率 16000Hz，单声道，16位
            with wave.open(audio_path, "wb") as wav_file:
                wav_file.setnchannels(1)  # 单声道
                wav_file.setsampwidth(2)  # 16位 = 2字节
                wav_file.setframerate(16000)  # 采样率 16000Hz
                for frame in self.audio_frames:
                    wav_file.writeframes(frame)

            self.temp_audio_path = audio_path
            logger.info(
                f"[Live Chat] 音频文件已保存: {audio_path}, 大小: {os.path.getsize(audio_path)} bytes"
            )
            return audio_path, time.time() - start_time

        except Exception as e:
            logger.error(f"[Live Chat] 组装 WAV 文件失败: {e}", exc_info=True)
            return None, 0.0

    def cleanup(self) -> None:
        """清理临时文件"""
        if self.temp_audio_path and os.path.exists(self.temp_audio_path):
            try:
                os.remove(self.temp_audio_path)
                logger.debug(f"[Live Chat] 已删除临时文件: {self.temp_audio_path}")
            except Exception as e:
                logger.warning(f"[Live Chat] 删除临时文件失败: {e}")
        self.temp_audio_path = None


class LiveChatRoute(Route):
    """Live Chat WebSocket 路由"""

    def __init__(
        self,
        context: RouteContext,
        db: Any,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.db = db
        self.plugin_manager = core_lifecycle.plugin_manager
        self.platform_history_mgr = core_lifecycle.platform_message_history_manager
        self.sessions: dict[str, LiveChatSession] = {}
        self.attachments_dir = os.path.join(get_astrbot_data_path(), "attachments")
        self.legacy_img_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")
        os.makedirs(self.attachments_dir, exist_ok=True)

        # 注册 WebSocket 路由
        self.app.websocket("/api/live_chat/ws")(self.live_chat_ws)
        self.app.websocket("/api/unified_chat/ws")(self.unified_chat_ws)

    async def live_chat_ws(self) -> None:
        """Legacy Live Chat WebSocket 处理器（默认 ct=live）"""
        await self._unified_ws_loop(force_ct="live")

    async def unified_chat_ws(self) -> None:
        """Unified Chat WebSocket 处理器（支持 ct=live/chat）"""
        await self._unified_ws_loop(force_ct=None)

    async def _unified_ws_loop(self, force_ct: str | None = None) -> None:
        """统一 WebSocket 循环"""
        # WebSocket 不能通过 header 传递 token，需要从 query 参数获取
        # 注意：WebSocket 上下文使用 websocket.args 而不是 request.args
        token = websocket.args.get("token")
        if not token:
            await websocket.close(1008, "Missing authentication token")
            return

        try:
            jwt_secret = self.config["dashboard"].get("jwt_secret")
            payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            username = payload["username"]
        except jwt.ExpiredSignatureError:
            await websocket.close(1008, "Token expired")
            return
        except jwt.InvalidTokenError:
            await websocket.close(1008, "Invalid token")
            return

        session_id = f"webchat_live!{username}!{uuid.uuid4()}"
        live_session = LiveChatSession(session_id, username)
        self.sessions[session_id] = live_session

        logger.info(f"[Live Chat] WebSocket 连接建立: {username}")

        try:
            while True:
                message = await websocket.receive_json()
                ct = force_ct or message.get("ct", "live")
                if ct == "chat":
                    await self._handle_chat_message(live_session, message)
                else:
                    await self._handle_message(live_session, message)

        except Exception as e:
            logger.error(f"[Live Chat] WebSocket 错误: {e}", exc_info=True)

        finally:
            # 清理会话
            if session_id in self.sessions:
                await self._cleanup_chat_subscriptions(live_session)
                live_session.cleanup()
                del self.sessions[session_id]
            logger.info(f"[Live Chat] WebSocket 连接关闭: {username}")

    async def _create_attachment_from_file(
        self, filename: str, attach_type: str
    ) -> dict | None:
        """从本地文件创建 attachment 并返回消息部分。"""
        return await create_attachment_part_from_existing_file(
            filename,
            attach_type=attach_type,
            insert_attachment=self.db.insert_attachment,
            attachments_dir=self.attachments_dir,
            fallback_dirs=[self.legacy_img_dir],
        )

    def _extract_web_search_refs(
        self, accumulated_text: str, accumulated_parts: list
    ) -> dict:
        """从消息中提取 web_search 引用。"""
        supported = ["web_search_tavily", "web_search_bocha"]
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
            m.strip() for m in re.findall(r"<ref>(.*?)</ref>", accumulated_text)
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

    async def _save_bot_message(
        self,
        webchat_conv_id: str,
        text: str,
        media_parts: list,
        reasoning: str,
        agent_stats: dict,
        refs: dict,
    ):
        """保存 bot 消息到历史记录。"""
        bot_message_parts = []
        bot_message_parts.extend(media_parts)
        if text:
            bot_message_parts.append({"type": "plain", "text": text})

        new_his = {"type": "bot", "message": bot_message_parts}
        if reasoning:
            new_his["reasoning"] = reasoning
        if agent_stats:
            new_his["agent_stats"] = agent_stats
        if refs:
            new_his["refs"] = refs

        return await self.platform_history_mgr.insert(
            platform_id="webchat",
            user_id=webchat_conv_id,
            content=new_his,
            sender_id="bot",
            sender_name="bot",
        )

    async def _send_chat_payload(self, session: LiveChatSession, payload: dict) -> None:
        async with session.ws_send_lock:
            await websocket.send_json(payload)

    async def _forward_chat_subscription(
        self,
        session: LiveChatSession,
        chat_session_id: str,
        request_id: str,
    ) -> None:
        back_queue = webchat_queue_mgr.get_or_create_back_queue(
            request_id, chat_session_id
        )
        try:
            while True:
                result = await back_queue.get()
                if not result:
                    continue
                await self._send_chat_payload(session, {"ct": "chat", **result})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(
                f"[Live Chat] chat subscription forward failed ({chat_session_id}): {e}",
                exc_info=True,
            )
        finally:
            webchat_queue_mgr.remove_back_queue(request_id)
            if session.chat_subscriptions.get(chat_session_id) == request_id:
                session.chat_subscriptions.pop(chat_session_id, None)
            session.chat_subscription_tasks.pop(chat_session_id, None)

    async def _ensure_chat_subscription(
        self,
        session: LiveChatSession,
        chat_session_id: str,
    ) -> str:
        existing_request_id = session.chat_subscriptions.get(chat_session_id)
        existing_task = session.chat_subscription_tasks.get(chat_session_id)
        if existing_request_id and existing_task and not existing_task.done():
            return existing_request_id

        request_id = f"ws_sub_{uuid.uuid4().hex}"
        session.chat_subscriptions[chat_session_id] = request_id
        task = asyncio.create_task(
            self._forward_chat_subscription(session, chat_session_id, request_id),
            name=f"chat_ws_sub_{chat_session_id}",
        )
        session.chat_subscription_tasks[chat_session_id] = task
        return request_id

    async def _cleanup_chat_subscriptions(self, session: LiveChatSession) -> None:
        tasks = list(session.chat_subscription_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        for request_id in list(session.chat_subscriptions.values()):
            webchat_queue_mgr.remove_back_queue(request_id)
        session.chat_subscriptions.clear()
        session.chat_subscription_tasks.clear()

    async def _handle_chat_message(
        self, session: LiveChatSession, message: dict
    ) -> None:
        """处理 Chat Mode 消息（ct=chat）"""
        msg_type = message.get("t")

        if msg_type == "bind":
            chat_session_id = message.get("session_id")
            if not isinstance(chat_session_id, str) or not chat_session_id:
                await self._send_chat_payload(
                    session,
                    {
                        "ct": "chat",
                        "t": "error",
                        "data": "session_id is required",
                        "code": "INVALID_MESSAGE_FORMAT",
                    },
                )
                return

            request_id = await self._ensure_chat_subscription(session, chat_session_id)
            await self._send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "type": "session_bound",
                    "session_id": chat_session_id,
                    "message_id": request_id,
                },
            )
            return

        if msg_type == "interrupt":
            session.should_interrupt = True
            await self._send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "INTERRUPTED",
                    "code": "INTERRUPTED",
                },
            )
            return

        if msg_type != "send":
            await self._send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": f"Unsupported message type: {msg_type}",
                    "code": "INVALID_MESSAGE_FORMAT",
                },
            )
            return

        if session.is_processing:
            await self._send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "Session is busy",
                    "code": "PROCESSING_ERROR",
                },
            )
            return

        payload = message.get("message")
        session_id = message.get("session_id") or session.session_id
        message_id = message.get("message_id") or str(uuid.uuid4())
        selected_provider = message.get("selected_provider")
        selected_model = message.get("selected_model")
        selected_stt_provider = message.get("selected_stt_provider")
        selected_tts_provider = message.get("selected_tts_provider")
        persona_prompt = message.get("persona_prompt")
        show_reasoning = message.get("show_reasoning")
        enable_streaming = message.get("enable_streaming", True)

        if not isinstance(payload, list):
            await self._send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "message must be list",
                    "code": "INVALID_MESSAGE_FORMAT",
                },
            )
            return

        message_parts = await self._build_chat_message_parts(payload)
        has_content = webchat_message_parts_have_content(message_parts)
        if not has_content:
            await self._send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "Message content is empty",
                    "code": "INVALID_MESSAGE_FORMAT",
                },
            )
            return

        await self._ensure_chat_subscription(session, session_id)

        session.is_processing = True
        session.should_interrupt = False
        back_queue = webchat_queue_mgr.get_or_create_back_queue(message_id, session_id)

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
                        "enable_streaming": enable_streaming,
                        "message_id": message_id,
                    },
                ),
            )

            message_parts_for_storage = strip_message_parts_path_fields(message_parts)
            await self.platform_history_mgr.insert(
                platform_id="webchat",
                user_id=session_id,
                content={"type": "user", "message": message_parts_for_storage},
                sender_id=session.username,
                sender_name=session.username,
            )

            accumulated_parts = []
            accumulated_text = ""
            accumulated_reasoning = ""
            tool_calls = {}
            agent_stats = {}
            refs = {}

            while True:
                if session.should_interrupt:
                    session.should_interrupt = False
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
                msg_type = result.get("type")
                streaming = result.get("streaming", False)
                chain_type = result.get("chain_type")
                if chain_type == "agent_stats":
                    try:
                        parsed_agent_stats = json.loads(result_text)
                        agent_stats = parsed_agent_stats
                        await self._send_chat_payload(
                            session,
                            {
                                "ct": "chat",
                                "type": "agent_stats",
                                "data": parsed_agent_stats,
                            },
                        )
                    except Exception:
                        pass
                    continue

                outgoing = {"ct": "chat", **result}
                await self._send_chat_payload(session, outgoing)

                if msg_type == "plain":
                    if chain_type == "tool_call":
                        try:
                            tool_call = json.loads(result_text)
                            tool_calls[tool_call.get("id")] = tool_call
                            if accumulated_text:
                                accumulated_parts.append(
                                    {"type": "plain", "text": accumulated_text}
                                )
                                accumulated_text = ""
                        except Exception:
                            pass
                    elif chain_type == "tool_call_result":
                        try:
                            tcr = json.loads(result_text)
                            tc_id = tcr.get("id")
                            if tc_id in tool_calls:
                                tool_calls[tc_id]["result"] = tcr.get("result")
                                tool_calls[tc_id]["finished_ts"] = tcr.get("ts")
                                accumulated_parts.append(
                                    {
                                        "type": "tool_call",
                                        "tool_calls": [tool_calls[tc_id]],
                                    }
                                )
                                tool_calls.pop(tc_id, None)
                        except Exception:
                            pass
                    elif chain_type == "reasoning":
                        accumulated_reasoning += result_text
                    elif streaming:
                        accumulated_text += result_text
                    else:
                        accumulated_text = result_text
                elif msg_type == "image":
                    filename = str(result_text).replace("[IMAGE]", "")
                    part = await self._create_attachment_from_file(filename, "image")
                    if part:
                        accumulated_parts.append(part)
                elif msg_type == "record":
                    filename = str(result_text).replace("[RECORD]", "")
                    part = await self._create_attachment_from_file(filename, "record")
                    if part:
                        accumulated_parts.append(part)
                elif msg_type == "file":
                    filename = str(result_text).replace("[FILE]", "").split("|", 1)[0]
                    part = await self._create_attachment_from_file(filename, "file")
                    if part:
                        accumulated_parts.append(part)
                elif msg_type == "video":
                    filename = str(result_text).replace("[VIDEO]", "").split("|", 1)[0]
                    part = await self._create_attachment_from_file(filename, "video")
                    if part:
                        accumulated_parts.append(part)

                should_save = False
                if msg_type == "end":
                    should_save = bool(
                        accumulated_parts
                        or accumulated_text
                        or accumulated_reasoning
                        or refs
                        or agent_stats
                    )
                elif (streaming and msg_type == "complete") or not streaming:
                    if chain_type not in (
                        "tool_call",
                        "tool_call_result",
                        "agent_stats",
                    ):
                        should_save = True

                if should_save:
                    try:
                        refs = self._extract_web_search_refs(
                            accumulated_text,
                            accumulated_parts,
                        )
                    except Exception as e:
                        logger.exception(
                            f"[Live Chat] Failed to extract web search refs: {e}",
                            exc_info=True,
                        )

                    saved_record = await self._save_bot_message(
                        session_id,
                        accumulated_text,
                        accumulated_parts,
                        accumulated_reasoning,
                        agent_stats,
                        refs,
                    )
                    if saved_record:
                        await self._send_chat_payload(
                            session,
                            {
                                "ct": "chat",
                                "type": "message_saved",
                                "data": {
                                    "id": saved_record.id,
                                    "created_at": saved_record.created_at.replace(tzinfo=timezone.utc).isoformat(),
                                },
                            },
                        )

                    accumulated_parts = []
                    accumulated_text = ""
                    accumulated_reasoning = ""
                    agent_stats = {}
                    refs = {}

                if msg_type == "end":
                    break

        except Exception as e:
            logger.error(f"[Live Chat] 处理 chat 消息失败: {e}", exc_info=True)
            await self._send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": f"处理失败: {str(e)}",
                    "code": "PROCESSING_ERROR",
                },
            )
        finally:
            session.is_processing = False
            webchat_queue_mgr.remove_back_queue(message_id)

    async def _build_chat_message_parts(self, message: list[dict]) -> list[dict]:
        """构建 chat websocket 用户消息段（复用 webchat 逻辑）"""
        return await build_webchat_message_parts(
            message,
            get_attachment_by_id=self.db.get_attachment_by_id,
            strict=False,
        )

    async def _handle_message(self, session: LiveChatSession, message: dict) -> None:
        """处理 WebSocket 消息"""
        msg_type = message.get("t")  # 使用 t 代替 type

        if msg_type == "start_speaking":
            # 开始说话
            stamp = message.get("stamp")
            if not stamp:
                logger.warning("[Live Chat] start_speaking 缺少 stamp")
                return
            session.start_speaking(stamp)

        elif msg_type == "speaking_part":
            # 音频片段
            audio_data_b64 = message.get("data")
            if not audio_data_b64:
                return

            # 解码 base64
            import base64

            try:
                audio_data = base64.b64decode(audio_data_b64)
                session.add_audio_frame(audio_data)
            except Exception as e:
                logger.error(f"[Live Chat] 解码音频数据失败: {e}")

        elif msg_type == "end_speaking":
            # 结束说话
            stamp = message.get("stamp")
            if not stamp:
                logger.warning("[Live Chat] end_speaking 缺少 stamp")
                return

            audio_path, assemble_duration = await session.end_speaking(stamp)
            if not audio_path:
                await websocket.send_json({"t": "error", "data": "音频组装失败"})
                return

            # 处理音频：STT -> LLM -> TTS
            await self._process_audio(session, audio_path, assemble_duration)

        elif msg_type == "interrupt":
            # 用户打断
            session.should_interrupt = True
            logger.info(f"[Live Chat] 用户打断: {session.username}")

    async def _process_audio(
        self, session: LiveChatSession, audio_path: str, assemble_duration: float
    ) -> None:
        """处理音频：STT -> LLM -> 流式 TTS"""
        try:
            # 发送 WAV 组装耗时
            await websocket.send_json(
                {"t": "metrics", "data": {"wav_assemble_time": assemble_duration}}
            )
            wav_assembly_finish_time = time.time()

            session.is_processing = True
            session.should_interrupt = False

            # 1. STT - 语音转文字
            ctx = self.plugin_manager.context
            stt_provider = ctx.provider_manager.stt_provider_insts[0]

            if not stt_provider:
                logger.error("[Live Chat] STT Provider 未配置")
                await websocket.send_json({"t": "error", "data": "语音识别服务未配置"})
                return

            await websocket.send_json(
                {"t": "metrics", "data": {"stt": stt_provider.meta().type}}
            )

            user_text = await stt_provider.get_text(audio_path)
            if not user_text:
                logger.warning("[Live Chat] STT 识别结果为空")
                return

            logger.info(f"[Live Chat] STT 结果: {user_text}")

            await websocket.send_json(
                {
                    "t": "user_msg",
                    "data": {"text": user_text, "ts": int(time.time() * 1000)},
                }
            )

            # 2. 构造消息事件并发送到 pipeline
            # 使用 webchat queue 机制
            cid = session.conversation_id
            queue = webchat_queue_mgr.get_or_create_queue(cid)

            message_id = str(uuid.uuid4())
            payload = {
                "message_id": message_id,
                "message": [{"type": "plain", "text": user_text}],  # 直接发送文本
                "action_type": "live",  # 标记为 live mode
            }

            # 将消息放入队列
            await queue.put((session.username, cid, payload))

            # 3. 等待响应并流式发送 TTS 音频
            back_queue = webchat_queue_mgr.get_or_create_back_queue(message_id, cid)

            bot_text = ""
            audio_playing = False

            try:
                while True:
                    if session.should_interrupt:
                        # 用户打断，停止处理
                        logger.info("[Live Chat] 检测到用户打断")
                        await websocket.send_json({"t": "stop_play"})
                        # 保存消息并标记为被打断
                        await self._save_interrupted_message(
                            session, user_text, bot_text
                        )
                        # 清空队列中未处理的消息
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
                            await websocket.send_json(
                                {
                                    "t": "metrics",
                                    "data": {
                                        "llm_ttft": stats.get("time_to_first_token", 0),
                                        "llm_total_time": stats.get("end_time", 0)
                                        - stats.get("start_time", 0),
                                    },
                                }
                            )
                        except Exception as e:
                            logger.error(f"[Live Chat] 解析 AgentStats 失败: {e}")
                        continue

                    if result_chain_type == "tts_stats":
                        try:
                            stats = json.loads(data)
                            await websocket.send_json(
                                {
                                    "t": "metrics",
                                    "data": stats,
                                }
                            )
                        except Exception as e:
                            logger.error(f"[Live Chat] 解析 TTSStats 失败: {e}")
                        continue

                    if result_type == "plain":
                        # 普通文本消息
                        bot_text += data

                    elif result_type == "audio_chunk":
                        # 流式音频数据
                        if not audio_playing:
                            audio_playing = True
                            logger.debug("[Live Chat] 开始播放音频流")

                            # Calculate latency from wav assembly finish to first audio chunk
                            speak_to_first_frame_latency = (
                                time.time() - wav_assembly_finish_time
                            )
                            await websocket.send_json(
                                {
                                    "t": "metrics",
                                    "data": {
                                        "speak_to_first_frame": speak_to_first_frame_latency
                                    },
                                }
                            )

                        text = result.get("text")
                        if text:
                            await websocket.send_json(
                                {
                                    "t": "bot_text_chunk",
                                    "data": {"text": text},
                                }
                            )

                        # 发送音频数据给前端
                        await websocket.send_json(
                            {
                                "t": "response",
                                "data": data,  # base64 编码的音频数据
                            }
                        )

                    elif result_type in ["complete", "end"]:
                        # 处理完成
                        logger.info(f"[Live Chat] Bot 回复完成: {bot_text}")

                        # 如果没有音频流，发送 bot 消息文本
                        if not audio_playing:
                            await websocket.send_json(
                                {
                                    "t": "bot_msg",
                                    "data": {
                                        "text": bot_text,
                                        "ts": int(time.time() * 1000),
                                    },
                                }
                            )

                        # 发送结束标记
                        await websocket.send_json({"t": "end"})

                        # 发送总耗时
                        wav_to_tts_duration = time.time() - wav_assembly_finish_time
                        await websocket.send_json(
                            {
                                "t": "metrics",
                                "data": {"wav_to_tts_total_time": wav_to_tts_duration},
                            }
                        )
                        break
            finally:
                webchat_queue_mgr.remove_back_queue(message_id)

        except Exception as e:
            logger.error(f"[Live Chat] 处理音频失败: {e}", exc_info=True)
            await websocket.send_json({"t": "error", "data": f"处理失败: {str(e)}"})

        finally:
            session.is_processing = False
            session.should_interrupt = False

    async def _save_interrupted_message(
        self, session: LiveChatSession, user_text: str, bot_text: str
    ) -> None:
        """保存被打断的消息"""
        interrupted_text = bot_text + " [用户打断]"
        logger.info(f"[Live Chat] 保存打断消息: {interrupted_text}")

        # 简单记录到日志，实际保存逻辑可以后续完善
        try:
            timestamp = int(time.time() * 1000)
            logger.info(
                f"[Live Chat] 用户消息: {user_text} (session: {session.session_id}, ts: {timestamp})"
            )
            if bot_text:
                logger.info(
                    f"[Live Chat] Bot 消息（打断）: {interrupted_text} (session: {session.session_id}, ts: {timestamp})"
                )
        except Exception as e:
            logger.error(f"[Live Chat] 记录消息失败: {e}", exc_info=True)
