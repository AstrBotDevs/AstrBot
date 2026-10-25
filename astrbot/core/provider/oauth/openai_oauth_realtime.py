import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from websockets.asyncio.client import connect

from astrbot.core.provider.sources.request_retry import ProviderRequestError

REALTIME_CALL_URL = (
    "https://chatgpt.com/backend-api/codex/realtime/calls"
    "?intent=quicksilver&architecture=avas"
)
REALTIME_SIDEBAND_BASE_URL = "wss://api.openai.com/v1/live"
REALTIME_MODEL = "gpt-live-1-codex"
REALTIME_VOICES = {
    "arbor",
    "breeze",
    "cove",
    "ember",
    "juniper",
    "maple",
    "sol",
    "spruce",
    "vale",
}
REALTIME_CHANNELS = {"speakable", "commentary"}
MAX_SDP_BYTES = 256 * 1024
MAX_CONTEXT_CHUNK_BYTES = 500
MAX_CONTEXT_TEXT_BYTES = 64 * 1024
MAX_INSTRUCTIONS_BYTES = 64 * 1024
_CALL_ID_PATTERN = re.compile(
    r"^(?:rtc_[A-Za-z0-9_-]{1,128}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)


class _NoRedirectConnect(connect):
    """Disable every WebSocket redirect before authenticated headers are reused."""

    def process_redirect(self, exc: Exception) -> Exception | str:
        """Reject redirects and sanitize all opening-handshake failures.

        Args:
            exc: WebSocket opening-handshake exception.

        Returns:
            A local exception. This method never returns a redirect URL.
        """
        return RuntimeError("Realtime sideband 握手失败或尝试重定向。")


websocket_connect = _NoRedirectConnect


@dataclass(frozen=True, slots=True)
class OpenAIOAuthRealtimeEvent:
    """Normalized event exposed to a plugin without raw upstream payloads."""

    type: str
    text: str = ""
    role: str = ""
    delegation_id: str = ""
    raw_type: str = ""


def _chunk_utf8(text: str) -> list[str]:
    """Split text without breaking characters or the upstream byte limit.

    Args:
        text: Nonempty context text.

    Returns:
        Ordered chunks whose UTF-8 encoding is at most 500 bytes each.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_bytes = 0
    for character in text:
        size = len(character.encode("utf-8"))
        if current and current_bytes + size > MAX_CONTEXT_CHUNK_BYTES:
            chunks.append("".join(current))
            current = []
            current_bytes = 0
        current.append(character)
        current_bytes += size
    if current:
        chunks.append("".join(current))
    return chunks


class OpenAIOAuthRealtimeSession:
    """Own one negotiated WebRTC call's sideband control connection."""

    def __init__(
        self,
        client: "OpenAIOAuthRealtimeClient",
        call_id: str,
        answer_sdp: str,
        websocket: Any,
        expires_at: float,
    ) -> None:
        self.id = call_id
        self.answer_sdp = answer_sdp
        self.expires_at = expires_at
        self._client = client
        self._websocket = websocket
        self._events: asyncio.Queue[OpenAIOAuthRealtimeEvent] = asyncio.Queue(
            maxsize=client.event_queue_size
        )
        self._closed_event = asyncio.Event()
        self._close_lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False
        self._last_activity = time.monotonic()
        self._active_delegation_id = ""
        self._completed_delegations: set[str] = set()
        self._seen_delegations: set[str] = set()
        self._reader_task = asyncio.create_task(self._reader())
        self._lifecycle_task = asyncio.create_task(self._watch_lifecycle())

    @property
    def closed(self) -> bool:
        """Return whether local ownership of the session has ended."""
        return self._closed

    async def __aenter__(self) -> "OpenAIOAuthRealtimeSession":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    def touch(self) -> None:
        """Record plugin-visible activity for the idle timeout."""
        if not self._closed:
            self._last_activity = time.monotonic()

    async def events(self) -> AsyncGenerator[OpenAIOAuthRealtimeEvent, None]:
        """Yield normalized events until the session closes."""
        while True:
            event = await self._events.get()
            yield event
            if event.type == "closed":
                return

    async def send_text(self, text: str, channel: str = "speakable") -> None:
        """Append bounded textual context to the realtime session.

        Args:
            text: Text to append.
            channel: Either ``speakable`` or ``commentary``.

        Raises:
            ValueError: If text or channel is invalid.
            RuntimeError: If the session is closed.
        """
        value = str(text or "")
        if not value:
            raise ValueError("Realtime 追加文本不能为空。")
        if len(value.encode("utf-8")) > MAX_CONTEXT_TEXT_BYTES:
            raise ValueError("Realtime 追加文本超过 64 KiB。")
        if channel not in REALTIME_CHANNELS:
            raise ValueError("Realtime channel 仅支持 speakable 或 commentary。")
        async with self._send_lock:
            self._require_open()
            for chunk in _chunk_utf8(value):
                await self._send_json(
                    {
                        "type": "session.context.append",
                        "channel": channel,
                        "content": [{"type": "input_text", "text": chunk}],
                    }
                )
        self.touch()

    async def submit_delegation_result(
        self,
        delegation_id: str,
        result: str,
        channel: str = "speakable",
    ) -> None:
        """Submit exactly one final result for the current delegation.

        Args:
            delegation_id: Active delegation identifier from an event.
            result: Agent or tool result to append.
            channel: Either ``speakable`` or ``commentary``.

        Raises:
            ValueError: If the delegation, result, or channel is invalid.
            RuntimeError: If the session is closed.
        """
        value = str(result or "")
        if not value:
            raise ValueError("Realtime 委托结果不能为空。")
        if len(value.encode("utf-8")) > MAX_CONTEXT_TEXT_BYTES:
            raise ValueError("Realtime 委托结果超过 64 KiB。")
        if channel not in REALTIME_CHANNELS:
            raise ValueError("Realtime channel 仅支持 speakable 或 commentary。")
        async with self._send_lock:
            self._require_open()
            if delegation_id in self._completed_delegations:
                raise ValueError("Realtime 委托已完成，不能重复提交。")
            if not delegation_id or delegation_id != self._active_delegation_id:
                raise ValueError("Realtime 委托不存在或已过期。")
            for chunk in _chunk_utf8(value):
                await self._send_json(
                    {
                        "type": "delegation.context.append",
                        "delegation_item_id": delegation_id,
                        "channel": channel,
                        "content": [{"type": "input_text", "text": chunk}],
                    }
                )
            self._completed_delegations.add(delegation_id)
            if self._active_delegation_id == delegation_id:
                self._active_delegation_id = ""
        self.touch()

    async def wait_closed(self) -> None:
        """Wait until local session cleanup finishes."""
        await self._closed_event.wait()

    async def close(self) -> None:
        """Idempotently end the verified call through its sideband only."""
        await self._close(send_close=True)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Realtime 会话已关闭。")

    async def _send_json(self, payload: dict[str, Any]) -> None:
        await asyncio.wait_for(
            self._websocket.send(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            ),
            timeout=self._client.send_timeout,
        )

    def _emit(self, event: OpenAIOAuthRealtimeEvent) -> None:
        self._events.put_nowait(event)

    async def _reader(self) -> None:
        terminal_error = False
        try:
            while True:
                frame = await self._websocket.recv()
                if isinstance(frame, bytes):
                    raise RuntimeError("Realtime sideband 收到未支持的二进制消息。")
                try:
                    event = json.loads(frame)
                except (TypeError, ValueError):
                    continue
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("type") or "")
                if event_type in {
                    "input_transcript.added",
                    "output_transcript.added",
                }:
                    self.touch()
                    prefix = "input" if event_type.startswith("input") else "output"
                    item = event.get("item")
                    text = str(item.get("text") or "") if isinstance(item, dict) else ""
                    self._emit(
                        OpenAIOAuthRealtimeEvent(type=f"{prefix}_transcript", text=text)
                    )
                elif event_type == "turn.done":
                    self.touch()
                    turn = event.get("turn")
                    if not isinstance(turn, dict):
                        turn = {}
                    self._emit(
                        OpenAIOAuthRealtimeEvent(
                            type="turn_done",
                            text=str(turn.get("transcript") or turn.get("text") or ""),
                            role=str(turn.get("role") or ""),
                        )
                    )
                elif event_type == "session.started":
                    session = event.get("session")
                    if isinstance(session, dict):
                        upstream_expiry = session.get("expires_at")
                        if isinstance(upstream_expiry, (int, float)):
                            self.expires_at = min(
                                self.expires_at, float(upstream_expiry)
                            )
                elif event_type == "delegation.created":
                    self.touch()
                    self._handle_delegation(event)
                elif event_type in {"error", "session.error"}:
                    self._emit(OpenAIOAuthRealtimeEvent(type="error"))
                    terminal_error = True
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            terminal_error = True
        finally:
            await self._close(send_close=terminal_error)

    def _handle_delegation(self, event: dict[str, Any]) -> None:
        item = event.get("item")
        if not isinstance(item, dict):
            return
        if item.get("type") != "delegation" or item.get("target") != "client":
            return
        delegation_id = str(item.get("id") or "")
        if not delegation_id or len(delegation_id.encode("utf-8")) > 256:
            return
        if delegation_id in self._seen_delegations:
            return
        if len(self._seen_delegations) >= self._client.max_delegations:
            raise RuntimeError("Realtime 委托数量超过会话上限。")
        self._seen_delegations.add(delegation_id)
        if self._active_delegation_id:
            previous = self._active_delegation_id
            self._completed_delegations.add(previous)
            self._emit(
                OpenAIOAuthRealtimeEvent(
                    type="delegation_cancelled", delegation_id=previous
                )
            )
        content = item.get("content")
        prompt_parts: list[str] = []
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "input_text":
                    prompt_parts.append(str(part.get("text") or ""))
        self._active_delegation_id = delegation_id
        self._emit(
            OpenAIOAuthRealtimeEvent(
                type="delegation",
                text="".join(prompt_parts),
                delegation_id=delegation_id,
            )
        )

    async def _watch_lifecycle(self) -> None:
        try:
            while not self._closed:
                absolute_remaining = self.expires_at - time.time()
                idle_remaining = self._client.idle_timeout - (
                    time.monotonic() - self._last_activity
                )
                remaining = min(absolute_remaining, idle_remaining)
                if remaining <= 0:
                    await self._close(send_close=True)
                    return
                await asyncio.sleep(min(1.0, remaining))
        except asyncio.CancelledError:
            raise

    async def _close(self, *, send_close: bool) -> None:
        current = asyncio.current_task()
        async with self._close_lock:
            if self._cleanup_task is None:
                self._closed = True
                self._cleanup_task = asyncio.create_task(
                    self._run_cleanup(send_close=send_close)
                )
            cleanup_task = self._cleanup_task
        if current in {self._reader_task, self._lifecycle_task}:
            return
        await asyncio.shield(cleanup_task)

    async def _run_cleanup(self, *, send_close: bool) -> None:
        tasks = [self._reader_task, self._lifecycle_task]
        try:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if send_close:
                try:
                    await asyncio.wait_for(
                        self._send_json({"type": "session.close"}),
                        timeout=self._client.close_timeout,
                    )
                except Exception:
                    pass
            try:
                await asyncio.wait_for(
                    self._websocket.close(code=1000, reason="session closed"),
                    timeout=self._client.close_timeout,
                )
            except Exception:
                pass
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._client._release_session(self)
            try:
                self._emit(OpenAIOAuthRealtimeEvent(type="closed"))
            except asyncio.QueueFull:
                self._events.get_nowait()
                self._emit(OpenAIOAuthRealtimeEvent(type="closed"))
            self._closed_event.set()


class OpenAIOAuthRealtimeClient:
    """Create and own bounded OAuth GPT-Live realtime sessions."""

    def __init__(
        self,
        oauth_provider: Any,
        *,
        max_sessions: int = 2,
        event_queue_size: int = 128,
        session_ttl: float = 30 * 60,
        idle_timeout: float = 5 * 60,
        create_timeout: float = 30,
        sideband_timeout: float = 15,
        send_timeout: float = 15,
        close_timeout: float = 5,
        sideband_connect_attempts: int = 1,
        max_delegations: int = 1024,
    ) -> None:
        self.oauth_provider = oauth_provider
        self.max_sessions = int(max_sessions)
        self.event_queue_size = int(event_queue_size)
        self.session_ttl = float(session_ttl)
        self.idle_timeout = float(idle_timeout)
        self.create_timeout = float(create_timeout)
        self.sideband_timeout = float(sideband_timeout)
        self.send_timeout = float(send_timeout)
        self.close_timeout = float(close_timeout)
        self.sideband_connect_attempts = int(sideband_connect_attempts)
        self.max_delegations = int(max_delegations)
        if (
            min(
                self.max_sessions,
                self.event_queue_size,
                self.session_ttl,
                self.idle_timeout,
                self.create_timeout,
                self.sideband_timeout,
                self.send_timeout,
                self.close_timeout,
                self.sideband_connect_attempts,
                self.max_delegations,
            )
            <= 0
        ):
            raise ValueError("Realtime 配额与超时参数必须大于 0。")
        self._state_lock = asyncio.Lock()
        self._session_slots = 0
        self._sessions: set[OpenAIOAuthRealtimeSession] = set()
        self._pending_tasks: set[asyncio.Task] = set()
        self._closing = False

    @property
    def session_count(self) -> int:
        """Return the combined pending and active session count."""
        return self._session_slots

    async def create_session(
        self,
        sdp_offer: str,
        *,
        model: str = REALTIME_MODEL,
        voice: str = "cove",
        instructions: str = "",
    ) -> OpenAIOAuthRealtimeSession:
        """Create a WebRTC call and attach its plugin-facing sideband.

        Args:
            sdp_offer: Audio-only WebRTC SDP offer produced by the plugin.
            model: Must be ``gpt-live-1-codex`` in the initial implementation.
            voice: Supported GPT-Live output voice.
            instructions: Developer instructions for the realtime session.

        Returns:
            Active session containing the answer SDP.

        Raises:
            ValueError: If model, voice, or SDP is invalid.
            PermissionError: If the account cannot create the call.
            RuntimeError: For limits or sanitized upstream failures.
            TimeoutError: If creation exceeds its bound.
        """
        offer = str(sdp_offer or "")
        if not offer or len(offer.encode("utf-8")) > MAX_SDP_BYTES:
            raise ValueError("Realtime SDP offer 为空或超过 256 KiB。")
        if "v=0" not in offer or "m=audio" not in offer or "m=video" in offer:
            raise ValueError("Realtime SDP offer 必须是 audio-only WebRTC SDP。")
        if model != REALTIME_MODEL:
            raise ValueError(f"Realtime 首版仅支持模型 {REALTIME_MODEL}。")
        if voice not in REALTIME_VOICES:
            raise ValueError("Realtime voice 不在支持列表中。")
        if len(str(instructions or "").encode("utf-8")) > MAX_INSTRUCTIONS_BYTES:
            raise ValueError("Realtime instructions 超过 64 KiB。")

        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Realtime 创建任务不可用。")
        async with self._state_lock:
            if self._closing:
                raise RuntimeError("Realtime 客户端正在关闭。")
            if self._session_slots >= self.max_sessions:
                raise RuntimeError("Realtime 会话达到并发上限。")
            self._session_slots += 1
            self._pending_tasks.add(task)

        session: OpenAIOAuthRealtimeSession | None = None
        slot_reserved = True
        try:
            session = await asyncio.wait_for(
                self._create_session(offer, model, voice, str(instructions or "")),
                timeout=self.create_timeout,
            )
            async with self._state_lock:
                if self._closing or session.closed:
                    closing_during_create = True
                else:
                    closing_during_create = False
                    self._sessions.add(session)
                    self._pending_tasks.discard(task)
                    slot_reserved = False
            if closing_during_create:
                await session.close()
                raise RuntimeError("Realtime 客户端关闭或 sideband 在创建期间失效。")
            return session
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Realtime 会话创建超时；远端清理状态未知。") from exc
        except asyncio.CancelledError:
            raise
        finally:
            if slot_reserved:
                async with self._state_lock:
                    self._pending_tasks.discard(task)
                    self._session_slots -= 1
            if session is not None and slot_reserved and not session.closed:
                await session.close()

    async def _create_session(
        self,
        offer: str,
        model: str,
        voice: str,
        instructions: str,
    ) -> OpenAIOAuthRealtimeSession:
        await self.oauth_provider._ensure_fresh_oauth_token()
        identifiers = {
            "session-id": str(uuid.uuid4()),
            "thread-id": str(uuid.uuid4()),
            "x-session-id": str(uuid.uuid4()),
        }
        body = {
            "sdp": offer,
            "session": {
                "model": model,
                "instructions": instructions,
                "audio": {"output": {"voice": voice}},
                "delegation": {"type": "client"},
            },
        }
        response, attempted_version = await self._post_call(body, identifiers)
        if response.status_code == 401:
            refreshed = await self.oauth_provider._refresh_after_auth_failure(
                attempted_version
            )
            if refreshed:
                response, _ = await self._post_call(body, identifiers)
        if response.status_code == 401:
            raise RuntimeError("Realtime OAuth 认证失败，请重新绑定账户。")
        if response.status_code == 403:
            raise PermissionError("当前 OAuth 账户或会话参数无权创建 Realtime call。")
        if not 200 <= response.status_code < 300:
            raise ProviderRequestError(
                f"Realtime call 创建失败：HTTP {response.status_code}。",
                status_code=response.status_code,
            )
        answer = response.text
        if (
            not answer
            or "v=0" not in answer
            or len(answer.encode("utf-8")) > MAX_SDP_BYTES
        ):
            raise RuntimeError(
                "Realtime answer SDP 为空或超过 256 KiB；远端清理状态未知。"
            )
        call_id = self._extract_call_id(response)
        websocket = None
        headers, _ = self.oauth_provider._build_backend_headers_with_version()
        headers = {
            key: value
            for key, value in headers.items()
            if key.lower() not in {"content-type", "accept", "openai-alpha"}
        }
        headers.update(identifiers)
        headers["OpenAI-Alpha"] = "quicksilver=v2"
        for _attempt in range(self.sideband_connect_attempts):
            try:
                websocket = await asyncio.wait_for(
                    websocket_connect(
                        f"{REALTIME_SIDEBAND_BASE_URL}/{call_id}",
                        additional_headers=headers,
                        open_timeout=self.sideband_timeout,
                        close_timeout=5,
                        max_size=MAX_SDP_BYTES,
                        proxy=self.oauth_provider.provider_config.get("proxy") or True,
                    ),
                    timeout=self.sideband_timeout,
                )
                break
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0)
        if websocket is None:
            raise RuntimeError(
                "Realtime sideband 建立失败；未重复创建 call，远端清理状态未知。"
            )
        session = OpenAIOAuthRealtimeSession(
            self,
            call_id,
            answer,
            websocket,
            time.time() + self.session_ttl,
        )
        try:
            await asyncio.sleep(0)
            if session.closed:
                raise RuntimeError(
                    "Realtime sideband 在会话就绪前关闭；远端清理状态未知。"
                )
            return session
        except BaseException:
            await session.close()
            raise

    async def _post_call(
        self,
        body: dict[str, Any],
        identifiers: dict[str, str],
    ) -> tuple[httpx.Response, int]:
        headers, attempted_version = (
            self.oauth_provider._build_backend_headers_with_version()
        )
        headers.update(identifiers)
        headers["OpenAI-Alpha"] = "quicksilver=v2"
        headers["Accept"] = "application/sdp"
        try:
            async with httpx.AsyncClient(
                proxy=self.oauth_provider.provider_config.get("proxy") or None,
                timeout=self.create_timeout,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    REALTIME_CALL_URL,
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError("Realtime call 请求超时；远端清理状态未知。") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                "Realtime call 网络请求失败；远端清理状态未知。"
            ) from exc
        return response, attempted_version

    def _extract_call_id(self, response: httpx.Response) -> str:
        location = str(response.headers.get("Location") or "").strip()
        candidates: list[str] = []
        if location:
            parsed = urlsplit(location)
            if parsed.netloc and parsed.hostname not in {
                "chatgpt.com",
                "api.openai.com",
            }:
                raise RuntimeError(
                    "Realtime call Location 来源无效；远端清理状态未知。"
                )
            candidates.extend(segment for segment in parsed.path.split("/") if segment)
        fallback = str(response.headers.get("openai-session-id") or "").strip()
        if fallback:
            candidates.append(fallback)
        for candidate in reversed(candidates):
            if _CALL_ID_PATTERN.fullmatch(candidate):
                return candidate
        raise RuntimeError("Realtime call 响应缺少合法 ID；远端清理状态未知。")

    def _release_session(self, session: OpenAIOAuthRealtimeSession) -> None:
        if session in self._sessions:
            self._sessions.remove(session)
            self._session_slots -= 1

    async def close(self) -> None:
        """Reject new work, cancel pending creates, and close active sessions."""
        current = asyncio.current_task()
        async with self._state_lock:
            self._closing = True
            pending = [task for task in self._pending_tasks if task is not current]
            sessions = list(self._sessions)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await asyncio.gather(
            *(session.close() for session in sessions),
            return_exceptions=True,
        )
