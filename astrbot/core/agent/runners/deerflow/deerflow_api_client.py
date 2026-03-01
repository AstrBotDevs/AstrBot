import codecs
import json
from collections.abc import AsyncGenerator
from typing import Any

from aiohttp import ClientResponse, ClientSession, ClientTimeout

from astrbot.core import logger


def _normalize_sse_newlines(text: str) -> str:
    """Normalize CRLF/CR to LF so SSE block splitting works reliably."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _parse_sse_data_lines(data_lines: list[str]) -> Any:
    raw_data = "\n".join(data_lines)
    try:
        return json.loads(raw_data)
    except json.JSONDecodeError:
        # Some LangGraph-compatible servers emit multiple JSON fragments
        # in one SSE event using repeated data lines (e.g. tuple payloads).
        parsed_lines: list[Any] = []
        can_parse_all = True
        for line in data_lines:
            line = line.strip()
            if not line:
                continue
            try:
                parsed_lines.append(json.loads(line))
            except json.JSONDecodeError:
                can_parse_all = False
                break
        if can_parse_all and parsed_lines:
            return parsed_lines[0] if len(parsed_lines) == 1 else parsed_lines
        return raw_data


async def _stream_sse(resp: ClientResponse) -> AsyncGenerator[dict[str, Any], None]:
    """Parse SSE response blocks into event/data dictionaries."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""

    async for chunk in resp.content.iter_chunked(8192):
        buffer += _normalize_sse_newlines(decoder.decode(chunk))

        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            if not block.strip():
                continue

            event_name = "message"
            data_lines: list[str] = []

            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())

            if not data_lines:
                continue

            data = _parse_sse_data_lines(data_lines)

            yield {"event": event_name, "data": data}

    # flush any remaining buffered text
    buffer += _normalize_sse_newlines(decoder.decode(b"", final=True))
    if not buffer.strip():
        return

    event_name = "message"
    data_lines = []
    for line in buffer.splitlines():
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        return

    data = _parse_sse_data_lines(data_lines)
    yield {"event": event_name, "data": data}


class DeerFlowAPIClient:
    """HTTP client for DeerFlow LangGraph API.

    Lifecycle is explicitly managed by callers (runner/stage). `__del__` is only a
    fallback diagnostic and must not be relied on for cleanup.
    """

    def __init__(
        self,
        api_base: str = "http://127.0.0.1:2026",
        api_key: str = "",
        auth_header: str = "",
        proxy: str | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self._session: ClientSession | None = None
        self._closed = False
        self.proxy = proxy.strip() if isinstance(proxy, str) else None
        if self.proxy == "":
            self.proxy = None
        self.headers: dict[str, str] = {}
        if auth_header:
            self.headers["Authorization"] = auth_header
        elif api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def _get_session(self) -> ClientSession:
        if self._closed:
            raise RuntimeError("DeerFlowAPIClient is already closed.")
        if self._session is None or self._session.closed:
            self._session = ClientSession(trust_env=True)
        return self._session

    async def __aenter__(self) -> "DeerFlowAPIClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        await self.close()

    async def create_thread(self, timeout: float = 20) -> dict[str, Any]:
        session = self._get_session()
        url = f"{self.api_base}/api/langgraph/threads"
        payload = {"metadata": {}}
        async with session.post(
            url,
            json=payload,
            headers=self.headers,
            timeout=timeout,
            proxy=self.proxy,
        ) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                raise Exception(
                    f"DeerFlow create thread failed: {resp.status}. {text}",
                )
            return await resp.json()

    async def stream_run(
        self,
        thread_id: str,
        payload: dict[str, Any],
        timeout: float = 120,
    ) -> AsyncGenerator[dict[str, Any], None]:
        session = self._get_session()
        url = f"{self.api_base}/api/langgraph/threads/{thread_id}/runs/stream"
        input_payload = payload.get("input")
        message_count = 0
        if isinstance(input_payload, dict) and isinstance(
            input_payload.get("messages"), list
        ):
            message_count = len(input_payload["messages"])
        # Log only a minimal summary to avoid exposing sensitive user content.
        logger.debug(
            "deerflow stream_run payload summary: thread_id=%s, keys=%s, message_count=%d, stream_mode=%s",
            thread_id,
            list(payload.keys()),
            message_count,
            payload.get("stream_mode"),
        )
        # For long-running SSE streams, avoid aiohttp total timeout.
        # Use socket read timeout so active heartbeats/chunks can keep the stream alive.
        stream_timeout = ClientTimeout(
            total=None,
            connect=min(timeout, 30),
            sock_connect=min(timeout, 30),
            sock_read=timeout,
        )
        async with session.post(
            url,
            json=payload,
            headers={
                **self.headers,
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
            },
            timeout=stream_timeout,
            proxy=self.proxy,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(
                    f"DeerFlow runs/stream request failed: {resp.status}. {text}",
                )
            async for event in _stream_sse(resp):
                yield event

    async def close(self) -> None:
        session = self._session
        if session is None:
            self._closed = True
            return

        if session.closed:
            self._session = None
            self._closed = True
            return

        try:
            await session.close()
        except Exception as e:
            logger.warning(
                "Failed to close DeerFlowAPIClient session cleanly: %s",
                e,
                exc_info=True,
            )
            raise

        self._session = None
        self._closed = True

    def __del__(self) -> None:
        session = getattr(self, "_session", None)
        closed = bool(getattr(self, "_closed", False))
        if closed or session is None or session.closed:
            return
        logger.warning(
            "DeerFlowAPIClient garbage collected with unclosed session; "
            "explicit close() should be called by runner lifecycle (or `async with`)."
        )

    @property
    def is_closed(self) -> bool:
        return self._closed
