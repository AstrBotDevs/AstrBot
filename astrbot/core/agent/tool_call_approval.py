from __future__ import annotations

import secrets
import string
import typing as T
from abc import ABC, abstractmethod
from dataclasses import dataclass

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.session_waiter import (
    FILTERS,
    DefaultSessionFilter,
    SessionController,
    SessionWaiter,
)

ApprovalReason = T.Literal[
    "approved",
    "rejected",
    "timeout",
    "unsupported_strategy",
    "error",
]


@dataclass(slots=True)
class ToolCallApprovalContext:
    event: AstrMessageEvent
    tool_name: str
    tool_args: dict[str, T.Any]
    tool_call_id: str


@dataclass(slots=True)
class ToolCallApprovalResult:
    approved: bool
    reason: ApprovalReason
    detail: str = ""

    def to_tool_result_text(self, tool_name: str) -> str:
        if self.approved:
            return f"tool call approval passed: {tool_name}"
        if self.reason == "timeout":
            return (
                f"error: tool call approval timed out for `{tool_name}`. "
                "The tool call was cancelled."
            )
        if self.reason == "unsupported_strategy":
            return (
                f"error: tool call approval strategy is unsupported for `{tool_name}`. "
                "The tool call was cancelled."
            )
        if self.reason == "error":
            return (
                f"error: tool call approval failed for `{tool_name}` ({self.detail}). "
                "The tool call was cancelled."
            )
        return (
            f"error: user rejected tool call approval for `{tool_name}`. "
            "The tool call was cancelled."
        )


class BaseToolCallApprovalStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def request(
        self,
        ctx: ToolCallApprovalContext,
        config: dict[str, T.Any],
    ) -> ToolCallApprovalResult: ...


class DynamicCodeApprovalStrategy(BaseToolCallApprovalStrategy):
    @property
    def name(self) -> str:
        return "dynamic_code"

    async def request(
        self,
        ctx: ToolCallApprovalContext,
        config: dict[str, T.Any],
    ) -> ToolCallApprovalResult:
        timeout_seconds = _safe_int(config.get("timeout", 60), default=60, minimum=1)
        dynamic_cfg = config.get("dynamic_code", {})
        if not isinstance(dynamic_cfg, dict):
            dynamic_cfg = {}
        code_length = _safe_int(dynamic_cfg.get("code_length", 6), default=6, minimum=4)
        case_sensitive = bool(dynamic_cfg.get("case_sensitive", False))

        code = "".join(secrets.choice(string.digits) for _ in range(code_length))

        await ctx.event.send(
            MessageChain().message(
                "Tool call needs your approval before execution.\n"
                f"Tool: `{ctx.tool_name}`\n"
                f"Approval code: `{code}`\n"
                "Please send this code to continue. "
                "Any other message will cancel this tool call."
            )
        )

        try:
            result = await _wait_for_code_input(
                event=ctx.event,
                expected_code=code,
                timeout=timeout_seconds,
                case_sensitive=case_sensitive,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Tool call approval failed unexpectedly for %s: %s",
                ctx.tool_name,
                exc,
                exc_info=True,
            )
            return ToolCallApprovalResult(
                approved=False,
                reason="error",
                detail=str(exc),
            )

        if not result.approved:
            if result.reason == "timeout":
                await ctx.event.send(
                    MessageChain().message(
                        f"Tool call `{ctx.tool_name}` approval timed out. This call was cancelled."
                    )
                )
            else:
                await ctx.event.send(
                    MessageChain().message(
                        f"Tool call `{ctx.tool_name}` was cancelled."
                    )
                )
        return result


_STRATEGY_REGISTRY: dict[str, BaseToolCallApprovalStrategy] = {}


def register_tool_call_approval_strategy(
    strategy: BaseToolCallApprovalStrategy,
) -> None:
    _STRATEGY_REGISTRY[strategy.name] = strategy


def _register_builtin_strategies() -> None:
    register_tool_call_approval_strategy(DynamicCodeApprovalStrategy())


_register_builtin_strategies()


async def request_tool_call_approval(
    *,
    config: dict[str, T.Any] | None,
    ctx: ToolCallApprovalContext,
) -> ToolCallApprovalResult:
    if not config or not bool(config.get("enable", False)):
        return ToolCallApprovalResult(approved=True, reason="approved")

    strategy_name = (
        str(config.get("strategy", "dynamic_code")).strip() or "dynamic_code"
    )
    strategy = _STRATEGY_REGISTRY.get(strategy_name)
    if not strategy:
        logger.warning("Unsupported tool call approval strategy: %s", strategy_name)
        return ToolCallApprovalResult(
            approved=False,
            reason="unsupported_strategy",
            detail=strategy_name,
        )
    return await strategy.request(ctx, config)


async def _wait_for_code_input(
    *,
    event: AstrMessageEvent,
    expected_code: str,
    timeout: int,
    case_sensitive: bool,
) -> ToolCallApprovalResult:
    session_filter = DefaultSessionFilter()
    FILTERS.append(session_filter)
    waiter = SessionWaiter(
        session_filter=session_filter,
        session_id=event.unified_msg_origin,
        record_history_chains=False,
    )

    async def _handler(
        controller: SessionController, incoming: AstrMessageEvent
    ) -> None:
        raw_input = (incoming.message_str or "").strip()
        if _is_code_match(
            expected=expected_code,
            actual=raw_input,
            case_sensitive=case_sensitive,
        ):
            if not controller.future.done():
                controller.future.set_result(
                    ToolCallApprovalResult(approved=True, reason="approved"),
                )
        else:
            if not controller.future.done():
                controller.future.set_result(
                    ToolCallApprovalResult(
                        approved=False,
                        reason="rejected",
                        detail=raw_input,
                    )
                )
        controller.stop()

    try:
        result = await waiter.register_wait(handler=_handler, timeout=timeout)
    except TimeoutError:
        return ToolCallApprovalResult(approved=False, reason="timeout")

    if isinstance(result, ToolCallApprovalResult):
        return result
    return ToolCallApprovalResult(
        approved=False,
        reason="error",
        detail=f"Invalid approval result type: {type(result).__name__}",
    )


def _is_code_match(*, expected: str, actual: str, case_sensitive: bool) -> bool:
    if case_sensitive:
        return actual == expected
    return actual.casefold() == expected.casefold()


def _safe_int(value: T.Any, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
        if parsed < minimum:
            return minimum
        return parsed
    except Exception:  # noqa: BLE001
        return default
