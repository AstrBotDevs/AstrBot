# ruff: noqa: E402
from __future__ import annotations

import sys
import types
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})


_install_optional_dependency_stubs()

from astrbot_sdk._internal.testing_support import MockCapabilityRouter, MockPeer
from astrbot_sdk.context import CancelToken
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.runtime.capability_dispatcher import CapabilityDispatcher
from astrbot_sdk.runtime.loader import (
    load_plugin,
    load_plugin_spec,
    validate_plugin_spec,
)
from astrbot_sdk.runtime.supervisor import SupervisorRuntime


class _DummyTransport:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send(self, payload: str) -> None:
        del payload


class _InProcessCapabilitySession:
    def __init__(self, plugin_dir: Path) -> None:
        plugin = load_plugin_spec(plugin_dir)
        validate_plugin_spec(plugin)
        self.plugin = plugin
        self.loaded_plugin = load_plugin(plugin)
        self.router = MockCapabilityRouter()
        self.peer = MockPeer(self.router)
        self.dispatcher = CapabilityDispatcher(
            plugin_id=plugin.name,
            peer=self.peer,
            capabilities=self.loaded_plugin.capabilities,
            llm_tools=self.loaded_plugin.llm_tools,
        )
        self.provided_capabilities = [
            item.descriptor.model_copy(deep=True)
            for item in self.loaded_plugin.capabilities
        ]
        self.capability_sources = {
            item.descriptor.name: plugin.name
            for item in self.loaded_plugin.capabilities
        }

    async def invoke_capability(
        self,
        capability_name: str,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        result = await self.dispatcher.invoke(
            InvokeMessage(
                id=request_id,
                capability=capability_name,
                input=dict(payload),
                stream=False,
            ),
            CancelToken(),
        )
        assert isinstance(result, dict)
        return result


def _write_plugin(plugin_dir: Path) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        dedent(
            """
            _schema_version: 2
            name: capability_roundtrip_plugin
            author: tests
            repo: capability_roundtrip_plugin
            version: 1.0.0
            desc: capability roundtrip tests

            runtime:
              python: "3.12"

            components:
              - class: main:CapabilityRoundTripPlugin
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "main.py").write_text(
        dedent(
            """
            from astrbot_sdk import Context, Star
            from astrbot_sdk.decorators import provide_capability


            class CapabilityRoundTripPlugin(Star):
                @provide_capability(
                    "capability_roundtrip_plugin.calculate",
                    description="Calculate a total and persist it through the core bridge",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                        },
                        "required": ["x", "y"],
                    },
                    output_schema={
                        "type": "object",
                        "properties": {
                            "result": {"type": "integer"},
                            "stored": {"type": "integer"},
                            "plugin": {"type": "string"},
                        },
                        "required": ["result", "stored", "plugin"],
                    },
                )
                async def calculate(self, payload: dict, ctx: Context) -> dict:
                    total = int(payload["x"]) + int(payload["y"])
                    await ctx.db.set("last_total", total)
                    stored = await ctx.db.get("last_total")
                    return {
                        "result": total,
                        "stored": int(stored),
                        "plugin": ctx.plugin_id,
                    }
            """
        ).lstrip(),
        encoding="utf-8",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_provide_capability_round_trips_through_core_router_and_sdk_dispatcher(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "capability_roundtrip_plugin"
    _write_plugin(plugin_dir)
    session = _InProcessCapabilitySession(plugin_dir)
    runtime = SupervisorRuntime(
        transport=_DummyTransport(),
        plugins_dir=tmp_path,
        env_manager=object(),  # type: ignore[arg-type]
    )

    assert len(session.provided_capabilities) == 1
    runtime._register_plugin_capability(  # noqa: SLF001
        session.provided_capabilities[0],
        session,
        session.plugin.name,
    )

    result = await runtime.capability_router.execute(
        "capability_roundtrip_plugin.calculate",
        {"x": 2, "y": 5},
        stream=False,
        cancel_token=CancelToken(),
        request_id="req-capability-roundtrip",
    )

    assert result == {
        "result": 7,
        "stored": 7,
        "plugin": "capability_roundtrip_plugin",
    }

    with pytest.raises(AstrBotError, match="capability_roundtrip_plugin.calculate"):
        await runtime.capability_router.execute(
            "capability_roundtrip_plugin.calculate",
            {"x": "bad", "y": 5},
            stream=False,
            cancel_token=CancelToken(),
            request_id="req-capability-invalid",
        )
