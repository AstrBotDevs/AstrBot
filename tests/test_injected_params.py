from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import BaseModel

from astrbot_sdk._internal.command_model import resolve_command_model_param
from astrbot_sdk._internal.injected_params import (
    is_framework_injected_parameter,
    legacy_arg_parameter_names,
)
from astrbot_sdk.conversation import ConversationSession
from astrbot_sdk.schedule import ScheduleContext
from astrbot_sdk.protocol.descriptors import CommandTrigger, HandlerDescriptor
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.loader import LoadedHandler, _build_param_specs


class _Payload(BaseModel):
    name: str


def test_legacy_arg_parameter_names_excludes_injected_aliases() -> None:
    def handler(
        ctx,
        conversation,
        conv,
        sched,
        schedule,
        name,
        extra="fallback",
    ) -> None: ...

    assert legacy_arg_parameter_names(handler) == ["name", "extra"]


def test_resolve_command_model_param_ignores_injected_aliases() -> None:
    def handler(conversation, sched, payload: _Payload) -> None: ...

    resolved = resolve_command_model_param(handler)

    assert resolved is not None
    assert resolved.name == "payload"
    assert resolved.model_cls is _Payload


def test_is_framework_injected_parameter_supports_type_based_injection() -> None:
    assert is_framework_injected_parameter("custom_conv", ConversationSession)
    assert is_framework_injected_parameter("custom_schedule", ScheduleContext)


def test_loader_build_param_specs_excludes_injected_aliases() -> None:
    def handler(conversation, schedule, name: str, count: int = 0) -> None: ...

    specs = _build_param_specs(handler)

    assert [spec.name for spec in specs] == ["name", "count"]


def test_handler_dispatcher_derive_args_skips_injected_aliases() -> None:
    def handler(conversation, name, sched) -> None: ...

    loaded = LoadedHandler(
        descriptor=HandlerDescriptor(
            id="plugin.handler",
            trigger=CommandTrigger(command="ping"),
        ),
        callable=handler,
        owner=object(),
    )
    dispatcher = HandlerDispatcher(
        plugin_id="plugin",
        peer=SimpleNamespace(),
        handlers=[loaded],
    )

    args = dispatcher._derive_args(loaded, SimpleNamespace(text="ping alice"))

    assert args == {"name": "alice"}
