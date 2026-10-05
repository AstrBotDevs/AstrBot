"""中国移动新消息 (5G消息) AstrBot 平台适配器。

协议移植自官方 OpenClaw 插件 openclaw-cmcc-newmsg-channel v1.0.0：

- WebSocket 长连接: server_url, 握手 header X-API-Key
- 连接后发送 {"type":"auth","apiKey":...,"version":...} 等待 auth_ok
- 心跳: 每 15s 发送 {"type":"ping"}, 服务端回 {"type":"pong"} (10s 超时)
- 收消息: {"type":"message"|"text_message"|"media_message",
           "from", "content", "messageId", "timestamp",
           "mediaType", "mediaUrl", "mediaFileName", ...}
- 发文本: {"type":"send","apiKey":...,"to":...,"content":...,"messageId":...}
- 发富媒体: 先 POST {upload_url}/upload (multipart: file, apiKey)
  返回 {"code":10200,"data":"<mediaUrl>"}，再按 send 消息发送
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from typing import Any

import aiohttp

try:  # websockets >= 14
    from websockets.asyncio.client import connect as ws_connect

    _HEADER_KW = "additional_headers"
except ImportError:  # pragma: no cover - 兼容旧版
    from websockets import connect as ws_connect  # type: ignore

    _HEADER_KW = "extra_headers"

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Plain, Record, Video
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.message_session import MessageSesion
from astrbot.core.platform.platform import PlatformStatus

from .cmcc_event import CmccNewmsgMessageEvent

DEFAULT_SERVER_URL = "wss://5gvas01.cmicmaap.com/gtw-ai/openclaw/ws/msg"
DEFAULT_UPLOAD_URL = "https://5gvas01.cmicmaap.com/gtw-ai/openclaw/api"

HEARTBEAT_INTERVAL = 15
HEARTBEAT_TIMEOUT = 10
RECONNECT_BASE_DELAY = 3
RECONNECT_MAX_DELAY = 60
UPLOAD_TIMEOUT = 120


def _gen_message_id() -> str:
    return "msg_%d_%09d" % (int(time.time() * 1000), random.randint(0, 999999999))


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:3] + "***" + key[-3:]


def _markdown_to_plain(text: str) -> str:
    """将 Markdown 转为纯文本（与官方插件 send.js 行为一致）。"""
    if not text:
        return text
    s = re.sub(r"```[\s\S]*?```", lambda m: m.group(0)[3:-3].strip(), text)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.M)
    s = re.sub(r"^#{3,6}(.?)", r"\1", s, flags=re.M)
    s = re.sub(r"^\[[^\]]+\]\s*", "", s, flags=re.M)
    s = re.sub(r"^[\s]*[-*]\s+", "• ", s, flags=re.M)
    s = re.sub(r"^[\s]*\d+\.\s+", "• ", s, flags=re.M)
    s = re.sub(r"^>\s*", "", s, flags=re.M)
    s = re.sub(r"^(-{3,}|\*{3,}|_{3,})\s*$", "", s, flags=re.M)
    s = re.sub(r"~~([^~]+)~~", r"\1", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _media_type_from_name(name: str) -> str:
    low = (name or "").lower()
    if any(low.endswith(e) for e in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
        return "IMAGE"
    if any(low.endswith(e) for e in (".mp4", ".webm", ".3gp", ".mov", ".avi")):
        return "VIDEO"
    if any(low.endswith(e) for e in (".mp3", ".wav", ".aac", ".m4a", ".ogg")):
        return "AUDIO"
    return "FILE"


def _escape_json_content(value: str) -> str:
    """转义字符串中未转义的引号（与官方插件 escapeJsonString 一致）。"""
    out = []
    for i, ch in enumerate(value):
        prev = value[i - 1] if i > 0 else ""
        if ch == '"' and prev != "\\":
            out.append('\\"')
        else:
            out.append(ch)
    return "".join(out)


def _parse_json(raw: Any) -> dict | None:
    """容错解析服务端 JSON（与官方插件的修复策略一致）。"""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return None
    raw = raw.strip().lstrip("﻿")
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass

    # 修复 content 字段中未转义引号的问题
    marker = '"content":"'
    ci = raw.find(marker)
    if ci == -1:
        return None
    vs = ci + len(marker)
    # content 的结束位置：其后任意一个已知字段的起始标记
    end_markers = (
        '","from":"',
        '","phone":"',
        '","to":"',
        '","messageId":"',
        '","id":"',
        '","timestamp":',
        '","type":"',
        '","mediaType":"',
    )
    fe = -1
    for em in end_markers:
        pos = raw.find(em, vs)
        if pos != -1 and (fe == -1 or pos < fe):
            fe = pos
    if fe == -1:
        return None
    fixed = raw[:vs] + _escape_json_content(raw[vs:fe]) + raw[fe:]
    try:
        obj = json.loads(fixed)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _component_from_media(
    media_type: str | None, media_url: str | None, file_name: str | None
):
    """把收到的媒体消息转成 AstrBot 消息组件。"""
    if not media_url:
        return None
    mt = (media_type or "").upper()
    if mt == "IMAGE":
        return Image(file=media_url, url=media_url)
    if mt == "AUDIO":
        return Record(file=media_url, url=media_url)
    if mt == "VIDEO":
        return Video(file=media_url, url=media_url)
    name = file_name or os.path.basename(media_url.split("?")[0]) or "file"
    return File(name=name, file="", url=media_url)


@register_platform_adapter(
    "cmcc_newmsg",
    "中国移动新消息(5G消息)适配器",
    default_config_tmpl={
        "api_key": "",
        "server_url": DEFAULT_SERVER_URL,
        "upload_url": DEFAULT_UPLOAD_URL,
        "version": "2.0",
    },
)
class CmccNewmsgPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.api_key = str(platform_config.get("api_key") or "")
        self.server_url = str(platform_config.get("server_url") or DEFAULT_SERVER_URL)
        self.upload_url = str(platform_config.get("upload_url") or DEFAULT_UPLOAD_URL)
        self.version = str(platform_config.get("version") or "2.0")
        self.self_id = "cmcc_newmsg_" + (
            self.api_key[3:11] if len(self.api_key) > 11 else "bot"
        )
        self._ws = None
        self._terminated = False
        self._last_pong = 0.0

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            "cmcc_newmsg", "中国移动新消息(5G消息)适配器", self.config.get("id") or "cmcc_newmsg"
        )

    # ------------------------------------------------------------------ run
    async def run(self) -> None:
        if not self.api_key or not re.match(r"^(ak_|app_)", self.api_key):
            self.record_error("cmcc-newmsg: API Key 未配置或格式错误(需 ak_/app_ 开头)")
            logger.error("cmcc-newmsg 平台未启动: API Key 缺失或格式错误")
            return

        retry = 0
        while not self._terminated:
            try:
                await self._connect_once()
                retry = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.record_error(f"cmcc-newmsg 连接异常: {e!s}")
                logger.error(f"cmcc-newmsg 连接异常: {e!s}")

            if self._terminated:
                break
            retry += 1
            delay = min(RECONNECT_BASE_DELAY * (2 ** (retry - 1)), RECONNECT_MAX_DELAY)
            delay += delay * 0.2 * (random.random() - 0.5)
            logger.info(f"cmcc-newmsg 将在 {delay:.1f}s 后重连 (第 {retry} 次)")
            await asyncio.sleep(delay)

    async def _connect_once(self) -> None:
        kwargs = {_HEADER_KW: {"X-API-Key": self.api_key}}
        logger.info(f"cmcc-newmsg 正在连接 {_mask_key(self.api_key)} @ {self.server_url}")
        async with ws_connect(self.server_url, open_timeout=30, **kwargs) as ws:
            self._ws = ws
            # 认证（服务端会先发 connected，再回 auth_ok）
            auth_deadline = asyncio.get_event_loop().time() + 15
            auth_msg = None
            while True:
                remaining = auth_deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise RuntimeError("cmcc-newmsg 认证超时")
                try:
                    first = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError as e:
                    raise RuntimeError("cmcc-newmsg 认证超时") from e
                msg = _parse_json(first)
                if not msg:
                    continue
                t = msg.get("type")
                if t == "auth_ok":
                    auth_msg = msg
                    break
                if t == "auth_failed":
                    raise RuntimeError(
                        f"cmcc-newmsg 认证失败: {msg.get('message', '')}"
                    )
                # connected / 其他消息，继续等待 auth_ok
            if auth_msg is None:
                raise RuntimeError("cmcc-newmsg 认证失败")

            self.clear_errors()
            self.status = PlatformStatus.RUNNING
            self._last_pong = time.time()
            logger.info(f"cmcc-newmsg 认证成功 ({_mask_key(self.api_key)})")

            hb = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                async for raw in ws:
                    await self._handle_raw(raw)
            finally:
                hb.cancel()
                self._ws = None

    async def _heartbeat_loop(self, ws) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if time.time() - self._last_pong > HEARTBEAT_INTERVAL + HEARTBEAT_TIMEOUT:
                    logger.error("cmcc-newmsg 心跳超时，主动断开")
                    await ws.close()
                    return
                await ws.send(json.dumps({"type": "ping"}))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"cmcc-newmsg 心跳任务退出: {e!s}")

    async def _handle_raw(self, raw: Any) -> None:
        msg = _parse_json(raw)
        if not msg:
            logger.warning("cmcc-newmsg 无法解析消息，已跳过")
            return
        t = msg.get("type")
        if t in ("message", "text_message", "media_message"):
            abm = self._convert_message(msg)
            self.commit_event(
                CmccNewmsgMessageEvent(
                    message_str=abm.message_str,
                    message_obj=abm,
                    platform_meta=self.meta(),
                    session_id=abm.session_id,
                    adapter=self,
                )
            )
        elif t == "pong":
            self._last_pong = time.time()
        elif t == "ping":
            # 主动响应服务端心跳
            if self._ws is not None:
                await self._ws.send(json.dumps({"type": "pong"}))
        elif t == "media_processed":
            logger.debug(f"cmcc-newmsg 媒体处理完成: {msg}")
        elif t in ("error", "auth_failed"):
            logger.error(f"cmcc-newmsg 服务端错误: {msg.get('message')}")
        else:
            logger.debug(f"cmcc-newmsg 未知消息类型: {t}")

    # ------------------------------------------------------------ 消息转换
    def _convert_message(self, msg: dict) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.type = MessageType.FRIEND_MESSAGE
        sender_id = str(msg.get("from") or msg.get("phone") or "unknown")
        abm.sender = MessageMember(
            user_id=sender_id, nickname=str(msg.get("nickname") or sender_id)
        )
        abm.self_id = self.self_id
        abm.message_id = str(
            msg.get("messageId") or msg.get("id") or _gen_message_id()
        )
        ts = msg.get("timestamp")
        try:
            ts_i = int(ts) if ts is not None else 0
            abm.timestamp = ts_i / 1000 if ts_i > 10**12 else ts_i or time.time()
        except (TypeError, ValueError):
            abm.timestamp = time.time()
        abm.raw_message = msg
        abm.session_id = sender_id
        abm.message_str = str(msg.get("content") or "")

        if msg.get("type") == "media_message":
            comp = _component_from_media(
                msg.get("mediaType"), msg.get("mediaUrl"), msg.get("mediaFileName")
            )
            abm.message = [comp] if comp is not None else []
            if not abm.message:
                abm.message = [Plain(abm.message_str)]
        else:
            abm.message = [Plain(abm.message_str)]
        return abm

    # ---------------------------------------------------------------- 发送
    async def send_text(self, to: str, text: str) -> str:
        ws = self._ws
        if ws is None:
            raise RuntimeError("WebSocket 未连接")
        message_id = _gen_message_id()
        payload = {
            "type": "send",
            "apiKey": self.api_key,
            "to": to,
            "content": text,
            "messageId": message_id,
        }
        await ws.send(json.dumps(payload, ensure_ascii=False))
        return message_id

    async def upload_media(self, file_path: str) -> tuple[str, str]:
        """上传本地文件，返回 (mediaUrl, mediaType)。"""
        if not os.path.exists(file_path):
            raise RuntimeError(f"文件不存在: {file_path}")
        file_name = os.path.basename(file_path)
        media_type = _media_type_from_name(file_name)
        size = os.path.getsize(file_path)
        form = aiohttp.FormData()
        with open(file_path, "rb") as f:
            form.add_field(
                "file", f, filename=file_name,
                content_type="application/octet-stream",
            )
            form.add_field("apiKey", self.api_key)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.upload_url.rstrip('/')}/upload",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=UPLOAD_TIMEOUT),
                ) as resp:
                    body = await resp.text()
        try:
            result = json.loads(body)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"上传响应解析失败: {body[:200]}") from e
        if result.get("code") == 10200 and result.get("data"):
            return str(result["data"]), media_type
        raise RuntimeError(f"上传失败: {result.get('message') or result}")

    async def send_media(
        self,
        to: str,
        media_url: str,
        media_type: str,
        file_name: str = "",
        size: int = 0,
        caption: str = "",
        mime_type: str = "",
    ) -> str:
        ws = self._ws
        if ws is None:
            raise RuntimeError("WebSocket 未连接")
        message_id = _gen_message_id()
        payload: dict[str, Any] = {
            "type": "send",
            "apiKey": self.api_key,
            "to": to,
            "mediaType": media_type,
            "content": caption,
            "mediaUrl": media_url,
            "messageId": message_id,
        }
        if file_name:
            payload["mediaFileName"] = file_name
        if size:
            payload["mediaSize"] = size
        if mime_type:
            payload["mediaMimeType"] = mime_type
        await ws.send(json.dumps(payload, ensure_ascii=False))
        return message_id

    async def send_message_chain(self, to: str, chain: MessageChain) -> None:
        if not to:
            raise RuntimeError("cmcc-newmsg 缺少发送目标")
        texts: list[str] = []
        for comp in chain.chain:
            if isinstance(comp, Plain):
                texts.append(comp.text or "")
            elif isinstance(comp, (Image, Record, Video, File)):
                await self._send_media_component(to, comp)
            # 其他组件(At/Reply 等)暂不支持，忽略
        text = _markdown_to_plain("".join(texts))
        if text:
            await self.send_text(to, text)

    async def _send_media_component(self, to: str, comp) -> None:
        try:
            path = await comp.convert_to_file_path()
        except Exception as e:
            logger.error(f"cmcc-newmsg 媒体解析失败: {e!s}")
            return
        try:
            media_url, media_type = await self.upload_media(path)
        except Exception as e:
            logger.error(f"cmcc-newmsg 媒体上传失败: {e!s}")
            return
        file_name = os.path.basename(path)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        caption = getattr(comp, "text", "") or ""
        await self.send_media(
            to, media_url, media_type,
            file_name=file_name, size=size, caption=str(caption),
        )

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        await super().send_by_session(session, message_chain)
        to = session.session_id
        await self.send_message_chain(to, message_chain)

    async def terminate(self) -> None:
        self._terminated = True
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
