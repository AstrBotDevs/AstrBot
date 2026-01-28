import asyncio
import json
import os
import time
import uuid
import wave
from typing import Any

import jwt
from quart import websocket

from astrbot import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .route import Route, RouteContext


class LiveChatSession:
    """Live Chat 会话管理器"""

    def __init__(self, session_id: str, username: str):
        self.session_id = session_id
        self.username = username
        self.conversation_id = str(uuid.uuid4())
        self.is_speaking = False
        self.is_processing = False
        self.should_interrupt = False
        self.audio_frames: list[bytes] = []
        self.current_stamp: str | None = None
        self.temp_audio_path: str | None = None

    def start_speaking(self, stamp: str):
        """开始说话"""
        self.is_speaking = True
        self.current_stamp = stamp
        self.audio_frames = []
        logger.debug(f"[Live Chat] {self.username} 开始说话 stamp={stamp}")

    def add_audio_frame(self, data: bytes):
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
            temp_dir = os.path.join(get_astrbot_data_path(), "temp")
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

    def cleanup(self):
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
        self.sessions: dict[str, LiveChatSession] = {}

        # 注册 WebSocket 路由
        self.app.websocket("/api/live_chat/ws")(self.live_chat_ws)

    async def live_chat_ws(self):
        """Live Chat WebSocket 处理器"""
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
                await self._handle_message(live_session, message)

        except Exception as e:
            logger.error(f"[Live Chat] WebSocket 错误: {e}", exc_info=True)

        finally:
            # 清理会话
            if session_id in self.sessions:
                live_session.cleanup()
                del self.sessions[session_id]
            logger.info(f"[Live Chat] WebSocket 连接关闭: {username}")

    async def _handle_message(self, session: LiveChatSession, message: dict):
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
    ):
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
            back_queue = webchat_queue_mgr.get_or_create_back_queue(cid)

            bot_text = ""
            audio_playing = False

            while True:
                if session.should_interrupt:
                    # 用户打断，停止处理
                    logger.info("[Live Chat] 检测到用户打断")
                    await websocket.send_json({"t": "stop_play"})
                    # 保存消息并标记为被打断
                    await self._save_interrupted_message(session, user_text, bot_text)
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

        except Exception as e:
            logger.error(f"[Live Chat] 处理音频失败: {e}", exc_info=True)
            await websocket.send_json({"t": "error", "data": f"处理失败: {str(e)}"})

        finally:
            session.is_processing = False
            session.should_interrupt = False

    async def _save_interrupted_message(
        self, session: LiveChatSession, user_text: str, bot_text: str
    ):
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
