import codecs
import json
from collections.abc import AsyncGenerator
from typing import Any

from aiohttp import ClientSession

from astrbot.core import logger


async def _stream_sse(resp) -> AsyncGenerator[dict, None]:
    """Stream Server-Sent Events (SSE) response"""
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    async for chunk in resp.content.iter_chunked(8192):
        buffer += decoder.decode(chunk)
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            if block.strip().startswith("data:"):
                try:
                    yield json.loads(block[5:])
                except json.JSONDecodeError:
                    logger.warning(f"Drop invalid n8n json data: {block[5:]}")
                    continue
    # flush any remaining text
    buffer += decoder.decode(b"", final=True)
    if buffer.strip().startswith("data:"):
        try:
            yield json.loads(buffer[5:])
        except json.JSONDecodeError:
            logger.warning(f"Drop invalid n8n json data: {buffer[5:]}")


class N8nAPIClient:
    """n8n API Client for webhook-based workflow execution"""

    def __init__(
        self,
        webhook_url: str,
        auth_header: str | None = None,
        auth_value: str | None = None,
    ):
        self.webhook_url = webhook_url
        self.session = ClientSession(trust_env=True)
        self.headers = {}
        if auth_header and auth_value:
            self.headers[auth_header] = auth_value

    async def execute_workflow(
        self,
        data: dict[str, Any],
        method: str = "POST",
        streaming: bool = False,
        timeout: float = 120,
    ) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
        """Execute n8n workflow via webhook

        Args:
            data: Data to send to the webhook
            method: HTTP method (GET or POST)
            streaming: Whether to expect streaming response
            timeout: Request timeout in seconds

        Returns:
            Workflow execution result or async generator for streaming responses

        """
        logger.debug(f"n8n workflow execution: {data}")

        if method.upper() == "GET":
            async with self.session.get(
                self.webhook_url,
                params=data,
                headers=self.headers,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(
                        f"n8n workflow execution failed: {resp.status}. {text}",
                    )
                if streaming:
                    return self._handle_streaming_response(resp)
                return await resp.json()
        # POST method
        async with self.session.post(
            self.webhook_url,
            json=data,
            headers=self.headers,
            timeout=timeout,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(
                    f"n8n workflow execution failed: {resp.status}. {text}",
                )
            if streaming:
                return self._handle_streaming_response(resp)
            return await resp.json()

    async def _handle_streaming_response(
        self,
        resp,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Handle streaming response from n8n workflow"""
        content_type = resp.headers.get("Content-Type", "")
        if "text/event-stream" in content_type:
            # SSE response
            async for event in _stream_sse(resp):
                yield event
        else:
            # Regular streaming response
            decoder = codecs.getincrementaldecoder("utf-8")()
            buffer = ""
            async for chunk in resp.content.iter_chunked(8192):
                buffer += decoder.decode(chunk)
                # Try to parse each line as JSON
                lines = buffer.split("\n")
                buffer = lines[-1]  # Keep incomplete line in buffer
                for line in lines[:-1]:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            # If not JSON, yield as text
                            yield {"text": line}

            # Flush remaining buffer
            buffer += decoder.decode(b"", final=True)
            if buffer.strip():
                try:
                    yield json.loads(buffer)
                except json.JSONDecodeError:
                    yield {"text": buffer}

    async def close(self):
        """Close the HTTP session"""
        await self.session.close()
