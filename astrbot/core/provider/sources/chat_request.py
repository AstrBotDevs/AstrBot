"""Wrap each upstream chat attempt with usage accounting."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import (
    AbstractAsyncContextManager,
    AsyncExitStack,
    aclosing,
    asynccontextmanager,
)
from dataclasses import dataclass, field
from datetime import datetime, timezone
from inspect import isawaitable
from time import monotonic
from typing import TYPE_CHECKING, TypeVar

from astrbot.core import db_helper
from astrbot.core.db.po import ChatRequestStat
from astrbot.core.platform.astr_message_event import current_message_event
from astrbot.core.provider.entities import TokenUsage
from astrbot.core.utils.plugin_scope import current_plugin_id

from .request_retry import retry_provider_request_context

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider

T = TypeVar("T")


@dataclass
class ChatAttempt:
    """Usage snapshots collected during one request."""

    started: float = field(default_factory=monotonic)
    usage: TokenUsage | None = None
    time_to_first_token: float | None = None
    status: str = "completed"

    def mark_first_token(self) -> None:
        """Record the latency of the first streamed output."""
        if self.time_to_first_token is None:
            self.time_to_first_token = monotonic() - self.started


@asynccontextmanager
async def chat_request(
    provider: "Provider",
    label: str,
    model: str,
    factory: Callable[[], Awaitable[T] | AbstractAsyncContextManager[T]],
    *,
    conversation_id: str | None,
    max_attempts: int | None,
    streaming: bool = False,
) -> AsyncIterator[tuple[T, ChatAttempt]]:
    """Track each attempt, including failed opens and interrupted streams.

    Args:
        provider: Chat adapter issuing the request.
        label: Provider name used in retry logs.
        model: Model sent to the upstream API.
        factory: One SDK call or a context manager that opens one stream.
        conversation_id: Explicit conversation attribution when provided.
        max_attempts: Transport retry limit.
        streaming: Whether to close the returned stream when the consumer exits.

    Yields:
        The SDK response and its record for the adapter to fill from usage metadata.
    """
    event = current_message_event.get()
    umo = getattr(event, "unified_msg_origin", None)
    conversation_id = conversation_id or getattr(
        getattr(event, "agent_session", None), "session_id", None
    )
    provider_id = provider.provider_config.get("id") or "default"
    plugin_id = current_plugin_id.get()

    @asynccontextmanager
    async def attempt():
        request = ChatAttempt()
        created_at = datetime.now(timezone.utc)
        try:
            async with AsyncExitStack() as stack:
                response = factory()
                if isawaitable(response):
                    response = await response
                if isinstance(response, AbstractAsyncContextManager):
                    response = await stack.enter_async_context(response)
                elif streaming and hasattr(response, "aclose"):
                    await stack.enter_async_context(aclosing(response))
                yield response, request
        except (asyncio.CancelledError, GeneratorExit):
            request.status = "aborted"
            raise
        except Exception:
            request.status = "error"
            raise
        finally:
            usage = request.usage
            record = ChatRequestStat(
                created_at=created_at,
                provider_id=provider_id,
                provider_model=model,
                conversation_id=conversation_id,
                umo=umo,
                plugin_id=plugin_id,
                status=request.status,
                token_input_other=usage.input_other if usage is not None else None,
                token_input_cached=usage.input_cached if usage is not None else None,
                token_output=usage.output if usage is not None else None,
                duration=monotonic() - request.started,
                time_to_first_token=request.time_to_first_token,
            )
            db_helper.chat_usage_writer.enqueue(record)

    async with retry_provider_request_context(
        label, attempt, max_attempts=max_attempts
    ) as result:
        yield result
