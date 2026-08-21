from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SDK_SRC = PROJECT_ROOT / "astrbot-sdk" / "src"

if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from astrbot_sdk._internal.command_model import format_command_model_help
from astrbot_sdk.cli import _render_init_agent_templates
from astrbot_sdk.clients.managers import MessageHistoryPage, MessageHistoryRecord
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.filters import CustomFilter
from astrbot_sdk.message.components import Plain
from astrbot_sdk.message.session import MessageSession
from astrbot_sdk.runtime._capability_router_builtins.capabilities.http import (
    HttpCapabilityMixin,
)


class _BooleanOptionsModel(BaseModel):
    foo_bar: bool = False


class _HttpCapabilityHost(HttpCapabilityMixin):
    def __init__(self) -> None:
        self.http_api_store: list[dict[str, object]] = []

    @staticmethod
    def _require_caller_plugin_id(_capability_name: str) -> str:
        return "demo"


def test_command_model_help_uses_canonical_boolean_option_names() -> None:
    help_text = format_command_model_help("demo", _BooleanOptionsModel)

    assert "--foo-bar / --no-foo-bar" in help_text
    assert "--foo_bar / --no-foo_bar" not in help_text


def test_render_init_agent_templates_creates_codex_skill_scaffold(tmp_path: Path) -> None:
    _render_init_agent_templates(
        target_dir=tmp_path,
        plugin_name="demo_plugin",
        display_name="Demo Plugin",
        agents=("codex",),
    )

    skill_dir = tmp_path / ".agents" / "skills" / "astrbot-plugin-dev"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "agents" / "openai.yaml").exists()


@pytest.mark.asyncio
async def test_http_register_api_rejects_empty_methods_after_normalization() -> None:
    host = _HttpCapabilityHost()

    with pytest.raises(AstrBotError, match="至少需要一个非空 HTTP 方法"):
        await host._http_register_api(
            "req-1",
            {
                "methods": ["", "   "],
                "route": "/demo",
                "handler_capability": "demo.handle",
            },
            None,
        )


def test_local_filter_binding_caches_signature_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    binding = CustomFilter(lambda event: bool(event)).compile()[1][0]

    def _unexpected_signature(_callable: object) -> object:
        raise AssertionError("evaluate() should not inspect signatures repeatedly")

    monkeypatch.setattr("astrbot_sdk.filters.inspect.signature", _unexpected_signature)

    assert binding.evaluate(event="payload") is True
    assert binding.evaluate(event="payload") is True


def test_message_history_record_preserves_component_instances() -> None:
    session = MessageSession(platform_id="qq", message_type="group", session_id="42")
    component = Plain("hello")

    record = MessageHistoryRecord.model_validate(
        {
            "id": 1,
            "session": session,
            "parts": [component],
        }
    )

    assert record.parts == [component]
    assert record.parts[0] is component


def test_message_history_page_preserves_record_instances() -> None:
    record = MessageHistoryRecord.model_validate(
        {
            "id": 1,
            "session": MessageSession(
                platform_id="qq",
                message_type="group",
                session_id="42",
            ),
            "parts": [Plain("hello")],
        }
    )

    page = MessageHistoryPage.model_validate({"records": [record]})

    assert page.records == [record]
    assert page.records[0] is record
