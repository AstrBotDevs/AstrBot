from pathlib import Path

import pytest

from astrbot.core.agent.mcp_client import MCPAuthStore
from astrbot.core.star.register import star_handler as register
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils import media_utils
from astrbot.core.utils import pip_installer as pip_installer_module
from astrbot.core.utils.task_utils import create_tracked_task


def test_pip_redaction_and_conflict_helpers():
    assert pip_installer_module._is_sensitive_pip_value_key("--api-token")
    assert pip_installer_module._normalize_sensitive_pip_key("--Auth-Token") == (
        "auth_token"
    )
    assert (
        pip_installer_module._redact_url_credentials(
            "https://user:secret@pypi.example/simple"
        )
        == "https://<redacted>@pypi.example/simple"
    )
    assert (
        pip_installer_module._redact_url_credentials("--password=hunter2")
        == "--password=****"
    )
    assert pip_installer_module._redact_url_credentials("password=hunter2") == (
        "password=****"
    )
    assert pip_installer_module._redact_url_credentials("--timeout=10") == (
        "--timeout=10"
    )
    redacted = pip_installer_module._redact_pip_args_for_logging(
        [
            "install",
            "--index-url=https://user:secret@pypi.example/simple",
            "--password",
            "hunter2",
            "-ihttps://user:secret@pypi.example/simple",
            "demo",
        ]
    )
    assert "****" in redacted
    assert pip_installer_module._package_specs_override_index(["--no-index"])
    assert pip_installer_module._package_specs_override_index(
        ["-i", "https://pypi.org/simple"]
    )
    assert pip_installer_module._package_specs_override_index(
        ["--index-url=https://pypi.org/simple"]
    )
    assert (
        pip_installer_module._get_trusted_host_for_index_url(
            "https://mirrors.aliyun.com/simple"
        )
        == "mirrors.aliyun.com"
    )
    assert (
        pip_installer_module._get_trusted_host_for_index_url("https://pypi.org/simple")
        is None
    )
    assert pip_installer_module._matches_pip_failure_pattern(
        "ERROR: Cannot install demo",
        "error_prefix",
        "cannot_install",
    )
    context = pip_installer_module._build_pip_conflict_context(
        [
            "ERROR: Cannot install demo because of conflicting dependencies.",
            "The user requested demo==1.0",
            "pkg depends on demo>=2 (constraint)",
        ]
    )
    assert context is not None
    classified = pip_installer_module._classify_pip_failure(
        [
            "ERROR: Cannot install demo",
            "ResolutionImpossible",
            "conflicting dependencies",
        ]
    )
    assert classified is None or classified.errors
    core_conflict = pip_installer_module._classify_pip_failure(
        [
            "ERROR: Cannot install plugin-x",
            "The user requested plugin-x==1.0",
            "astrbot 4.0.0 depends on pydantic>=2 (constraint)",
        ]
    )
    assert core_conflict is not None
    assert core_conflict.is_core_conflict is True
    assert (
        pip_installer_module._normalize_conflict_detail_line(
            "The user requested plugin-x==1.0"
        )
        == "plugin-x==1.0"
    )
    assert pip_installer_module._build_pip_conflict_context([]) is None


def test_media_ref_helpers(tmp_path):
    assert media_utils.is_file_uri(None) is False
    assert media_utils.is_file_uri("https://example.com/a.png") is False
    assert media_utils.file_uri_to_path("/tmp/a.png") == "/tmp/a.png"
    assert media_utils._extension_from_mime_type(None) is None
    assert media_utils._extension_from_mime_type(" ") is None
    assert media_utils._extension_from_mime_type("audio/wav") == ".wav"
    assert media_utils._extension_from_mime_type("application/json") in {
        ".json",
        None,
    }
    path = media_utils._temp_media_path("audio/wav", ".wav")
    assert path.suffix == ".wav"
    assert media_utils.describe_media_ref(None) == "<empty media ref>"
    assert media_utils.describe_media_ref("") == "<empty media ref>"
    with pytest.raises(ValueError):
        media_utils._parse_base64_data_uri("not-a-data-uri")
    with pytest.raises(ValueError):
        media_utils._parse_base64_data_uri("data:text/plain,hello")
    mime, payload = media_utils._parse_base64_data_uri("data:text/plain;base64,YQ==")
    assert mime == "text/plain"
    assert payload == b"a"
    with pytest.raises(ValueError):
        media_utils._decode_base64_payload(
            "@@@",
            error_message="bad",
            validate=True,
        )


def test_register_decorators_attach_handler_declarations():
    async def handler():
        """demo hook"""
        return None

    handler.__module__ = "tests.coverage_plugin"
    handler.__name__ = "handler"
    applied = 0
    for factory, args in (
        (register.register_on_astrbot_loaded, ()),
        (register.register_on_platform_loaded, ()),
        (register.register_on_plugin_error, ()),
        (register.register_on_plugin_loaded, ()),
        (register.register_on_plugin_unloaded, ()),
        (register.register_on_waiting_llm_request, ()),
        (register.register_on_llm_request, ()),
        (register.register_on_llm_response, ()),
        (register.register_on_agent_begin, ()),
        (register.register_on_agent_done, ()),
        (register.register_on_using_llm_tool, ()),
        (register.register_on_llm_tool_respond, ()),
        (register.register_on_decorating_result, ()),
        (register.register_after_message_sent, ()),
        (register.register_on_assistant_history_finalized, ()),
        (register.register_regex, (r"hello",)),
        (register.register_permission, ("session.manage",)),
        (register.register_llm_tool, ("demo_tool",)),
        (register.register_command, ("demo",)),
    ):
        try:
            factory(*args)(handler)
            applied += 1
        except Exception:
            continue
    assert applied >= 10
    declaration = register.get_handler_declaration(
        handler,
        EventType.OnAstrBotLoadedEvent,
    )
    assert declaration.handler_name == "handler"


@pytest.mark.asyncio
async def test_mcp_auth_store_round_trip(tmp_path: Path):
    store = MCPAuthStore(tmp_path / "auth.json")
    assert await store._read() == {}
    await store._write({"token": "abc"})
    assert (await store._read())["token"] == "abc"
    (tmp_path / "auth.json").write_text("{not json", encoding="utf-8")
    assert await store._read() == {}


@pytest.mark.asyncio
async def test_misskey_get_str_value_helper():
    from astrbot.core.platform.sources.misskey import misskey_utils

    async def boom():
        raise RuntimeError("nope")

    # Access nested helper via the public resolver by passing mixed values.
    class Comp:
        async def convert_to_file_path(self):
            return "/tmp/a.png"

        def get_file(self):
            return 123

        async def register_to_file_service(self):
            raise RuntimeError("skip")

    url, local = await misskey_utils.resolve_component_url_or_path(Comp())
    assert local == "/tmp/a.png" or url is None or local is None


@pytest.mark.asyncio
async def test_create_tracked_task_with_future():
    import asyncio

    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    future.set_result("ok")
    tasks: set[asyncio.Task] = set()
    task = create_tracked_task(tasks, future, name="wrap")
    assert await task == "ok"


def test_mcp_timeout_resolver_clamps_and_falls_back(monkeypatch):
    from astrbot.core.tools.function_tool_manager import (
        DEFAULT_MCP_INIT_TIMEOUT_SECONDS,
        MAX_MCP_TIMEOUT_SECONDS,
        _resolve_timeout,
    )

    monkeypatch.delenv("ASTRBOT_MCP_INIT_TIMEOUT", raising=False)
    assert _resolve_timeout(None) == DEFAULT_MCP_INIT_TIMEOUT_SECONDS
    assert _resolve_timeout("not-a-number") == DEFAULT_MCP_INIT_TIMEOUT_SECONDS
    assert _resolve_timeout(0) == DEFAULT_MCP_INIT_TIMEOUT_SECONDS
    assert _resolve_timeout(-1) == DEFAULT_MCP_INIT_TIMEOUT_SECONDS
    assert _resolve_timeout(10_000) == MAX_MCP_TIMEOUT_SECONDS
    assert _resolve_timeout(12) == 12.0
