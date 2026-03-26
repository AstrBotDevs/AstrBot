from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.errors import AstrBotError, ErrorCodes

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


def _plugin_metadata(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": name,
        "description": f"{name} plugin",
        "author": "tests",
        "version": "1.0.0",
    }


@pytest.mark.unit
def test_error_handling_doc_error_factories_and_payload_round_trip() -> None:
    errors = [
        AstrBotError.invalid_input(
            "bad input",
            hint="fix the payload",
            docs_url="https://docs.example.com/errors#invalid-input",
            details={"field": "name"},
        ),
        AstrBotError.capability_not_found("demo.echo"),
        AstrBotError.network_error(
            "connection timed out",
            hint="retry later",
            details={"phase": "connect"},
        ),
        AstrBotError.internal_error(
            "database unavailable",
            hint="contact the plugin author",
            details={"component": "db"},
        ),
        AstrBotError.cancelled("operation cancelled by user"),
        AstrBotError.protocol_version_mismatch("v4 vs v5"),
        AstrBotError.protocol_error("malformed protocol payload"),
        AstrBotError.rate_limited(
            hint="retry after 60 seconds",
            details={"retry_after": 60},
        ),
        AstrBotError.cooldown_active(
            hint="cooldown 30 seconds",
            details={"remaining_seconds": 30},
        ),
    ]

    expected_codes = {
        ErrorCodes.INVALID_INPUT,
        ErrorCodes.CAPABILITY_NOT_FOUND,
        ErrorCodes.NETWORK_ERROR,
        ErrorCodes.INTERNAL_ERROR,
        ErrorCodes.CANCELLED,
        ErrorCodes.PROTOCOL_VERSION_MISMATCH,
        ErrorCodes.PROTOCOL_ERROR,
        ErrorCodes.RATE_LIMITED,
        ErrorCodes.COOLDOWN_ACTIVE,
    }

    assert {error.code for error in errors} == expected_codes
    assert AstrBotError.network_error("boom").retryable is True
    assert AstrBotError.invalid_input("boom").retryable is False

    for original in errors:
        restored = AstrBotError.from_payload(original.to_payload())

        assert restored.code == original.code
        assert restored.message == original.message
        assert restored.hint == original.hint
        assert restored.retryable == original.retryable
        assert restored.docs_url == original.docs_url
        assert restored.details == original.details
        assert str(restored) == restored.message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_handling_doc_retry_and_capability_missing_round_trip_through_core_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    runtime.plugin_bridge.upsert_plugin(metadata=_plugin_metadata("error-docs"))
    ctx = runtime.make_context("error-docs")

    runtime.enqueue_llm_response("retry success")
    original_text_chat = runtime.chat_provider.text_chat
    attempts = {"count": 0}

    async def flaky_text_chat(**kwargs: Any):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise AstrBotError.network_error(
                "connection timed out",
                hint="retry later",
            )
        return await original_text_chat(**kwargs)

    monkeypatch.setattr(runtime.chat_provider, "text_chat", flaky_text_chat)

    async def with_retry(
        ctx: Context,
        operation,
        *,
        max_retries: int = 3,
    ) -> str:
        last_error: AstrBotError | None = None
        for attempt in range(max_retries):
            try:
                return await operation()
            except AstrBotError as error:
                last_error = error
                await ctx.db.set(f"retry_attempt_{attempt + 1}", error.code)
                if not error.retryable or attempt == max_retries - 1:
                    raise
                await asyncio.sleep(0)
        raise RuntimeError("retry loop exited without returning")

    result = await with_retry(
        ctx,
        lambda: ctx.llm.chat("generate some content"),
        max_retries=3,
    )

    assert result == "retry success"
    assert attempts["count"] == 3
    assert await ctx.db.get_many(["retry_attempt_1", "retry_attempt_2"]) == {
        "retry_attempt_1": ErrorCodes.NETWORK_ERROR,
        "retry_attempt_2": ErrorCodes.NETWORK_ERROR,
    }

    with pytest.raises(AstrBotError) as exc_info:
        await ctx._proxy.call("unknown.capability", {})  # noqa: SLF001

    assert exc_info.value.code == ErrorCodes.CAPABILITY_NOT_FOUND
    assert "unknown.capability" in exc_info.value.message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_handling_doc_cancel_token_and_debug_logging_use_real_context_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    runtime.plugin_bridge.upsert_plugin(metadata=_plugin_metadata("error-docs"))
    cancel_token = CancelToken()
    ctx = Context(
        peer=runtime.peer,
        plugin_id="error-docs",
        request_id="error-docs:cancel-1",
        cancel_token=cancel_token,
    )

    watcher = ctx.logger.watch()
    progressed = asyncio.Event()
    wait_task = asyncio.create_task(ctx.cancel_token.wait())

    async def collect_entries(limit: int) -> list[Any]:
        entries: list[Any] = []
        async for entry in watcher:
            entries.append(entry)
            if len(entries) >= limit:
                break
        return entries

    async def long_task() -> None:
        ctx.logger.info("cancelled={}", ctx.cancel_token.cancelled)
        try:
            for step in range(10):
                ctx.logger.debug("step {} cancelled={}", step, ctx.cancel_token.cancelled)
                await ctx.db.set("last_step", step)
                if step == 0:
                    progressed.set()
                await asyncio.sleep(0)
                ctx.cancel_token.raise_if_cancelled()
        except asyncio.CancelledError:
            ctx.logger.info("operation cancelled")
            raise

    collector_task = asyncio.create_task(collect_entries(3))
    task = asyncio.create_task(long_task())

    await asyncio.wait_for(progressed.wait(), timeout=1)
    ctx.cancel_token.cancel()
    await asyncio.wait_for(wait_task, timeout=1)

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)

    entries = await asyncio.wait_for(collector_task, timeout=1)
    await watcher.aclose()

    assert [entry.message for entry in entries] == [
        "cancelled=False",
        "step 0 cancelled=False",
        "operation cancelled",
    ]
    assert await ctx.db.get("last_step") == 0

