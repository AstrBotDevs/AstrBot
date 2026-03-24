from __future__ import annotations

from typing import Optional

import pytest

from astrbot_sdk import Context, MessageEvent, on_schedule, provide_capability
from astrbot_sdk.runtime._loader_support import (
    build_param_specs,
    resolve_capability_candidate,
    resolve_handler_candidate,
    validate_schedule_signature,
)
from astrbot_sdk.schedule import ScheduleContext
from astrbot_sdk.types import GreedyStr


def test_build_param_specs_skips_injected_params_and_preserves_optional_and_greedy() -> (
    None
):
    def handler(
        event: MessageEvent,
        ctx: Context,
        count: int,
        maybe_name: Optional[str],
        enabled: bool = False,
        remainder: GreedyStr = "",
    ) -> None:
        return None

    specs = build_param_specs(handler)

    assert [spec.name for spec in specs] == [
        "count",
        "maybe_name",
        "enabled",
        "remainder",
    ]
    assert [spec.type for spec in specs] == ["int", "optional", "bool", "greedy_str"]
    assert specs[1].inner_type == "str"
    assert specs[1].required is False
    assert specs[2].required is False
    assert specs[3].required is False


def test_build_param_specs_rejects_non_terminal_greedy_string() -> None:
    def handler(remainder: GreedyStr, count: int) -> None:
        return None

    with pytest.raises(ValueError, match="GreedyStr"):
        build_param_specs(handler)


def test_validate_schedule_signature_rejects_non_injected_names() -> None:
    def valid(ctx: Context, schedule: ScheduleContext) -> None:
        return None

    def invalid(ctx: Context, event: MessageEvent) -> None:
        return None

    validate_schedule_signature(valid)

    with pytest.raises(ValueError, match="Schedule handler"):
        validate_schedule_signature(invalid)


def test_resolve_handler_candidate_finds_schedule_decorated_method() -> None:
    class Plugin:
        @on_schedule(interval_seconds=60, description="heartbeat")
        async def tick(self, ctx: Context) -> None:
            return None

    instance = Plugin()

    resolved = resolve_handler_candidate(instance, "tick")

    assert resolved is not None
    bound, meta = resolved
    assert bound.__name__ == "tick"
    assert meta.trigger is not None
    assert meta.trigger.type == "schedule"


def test_resolve_capability_candidate_finds_capability_decorated_method() -> None:
    class Plugin:
        @provide_capability(
            "plugin.echo",
            description="Echo capability",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        async def echo(self, payload: dict) -> dict:
            return payload

    instance = Plugin()

    resolved = resolve_capability_candidate(instance, "echo")

    assert resolved is not None
    bound, meta = resolved
    assert bound.__name__ == "echo"
    assert meta.descriptor.name == "plugin.echo"
