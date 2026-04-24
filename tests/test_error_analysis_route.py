import asyncio
import contextlib
import re

import pytest

from astrbot.dashboard.routes.error_analysis import (
    ErrorAnalysisRoute,
    parse_json_from_model_output,
    redact_sensitive_text,
)


def test_parse_json_from_model_output_plain_json():
    payload, raw = parse_json_from_model_output('{"summary":"ok","confidence":0.7}')

    assert payload is not None
    assert payload["summary"] == "ok"
    assert payload["confidence"] == 0.7
    assert raw == '{"summary":"ok","confidence":0.7}'


def test_parse_json_from_model_output_markdown_block():
    content = """```json
{
  "summary": "from fenced",
  "severity": "high"
}
```"""
    payload, _ = parse_json_from_model_output(content)

    assert payload is not None
    assert payload["summary"] == "from fenced"
    assert payload["severity"] == "high"


def test_parse_json_from_model_output_invalid():
    payload, raw = parse_json_from_model_output("not-json")

    assert payload is None
    assert raw == "not-json"


def test_redact_sensitive_text_masks_known_patterns():
    text = (
        "Authorization: Bearer very_secret_token\n"
        "api_key=abc123456\n"
        "password=hunter2\n"
        "sk-abcdefghijklmnop"
    )

    redacted = redact_sensitive_text(text)

    assert "very_secret_token" not in redacted
    assert "abc123456" not in redacted
    assert "hunter2" not in redacted
    assert "sk-abcdefghijklmnop" not in redacted
    assert "Bearer ****" in redacted
    assert "api_key=****" in redacted
    assert "password=****" in redacted
    assert "sk-****" in redacted


def test_classify_target_uses_traceback_plugin_path_over_core_pathname():
    route = ErrorAnalysisRoute.__new__(ErrorAnalysisRoute)

    result = route._classify_target(
        {
            "pathname": "astrbot/core/core_lifecycle.py",
            "message": "plugin failed",
            "exc_text": 'Traceback...\nFile "data/plugins/weather/main.py", line 12, in run',
            "data": "",
        }
    )

    assert result["target_type"] == "plugin"
    assert result["target_name"] == "weather"


def test_classify_target_prefers_provider_signal_over_core_pathname():
    route = ErrorAnalysisRoute.__new__(ErrorAnalysisRoute)

    result = route._classify_target(
        {
            "pathname": "astrbot/core/provider_manager.py",
            "source_file": "astrbot/core/provider_manager.py",
            "message": "Provider request failed with 401: invalid api key",
            "exc_text": "",
            "data": "",
        }
    )

    assert result["target_type"] == "provider"
    assert result["target_name"] == "Provider"


def test_generate_record_id_has_random_suffix():
    route = ErrorAnalysisRoute.__new__(ErrorAnalysisRoute)

    value_a = route._generate_record_id(1713960000.123)
    value_b = route._generate_record_id(1713960000.123)

    assert value_a != value_b
    assert re.fullmatch(r"ea_\d+_[0-9a-f]{8}", value_a)


def test_read_file_excerpt_reads_target_region(tmp_path):
    route = ErrorAnalysisRoute.__new__(ErrorAnalysisRoute)
    route._is_path_allowed = lambda path: True

    path = tmp_path / "large_file.py"
    path.write_text(
        "\n".join(f"line_{index}" for index in range(1, 1001)),
        encoding="utf-8",
    )

    excerpt = route._read_file_excerpt(
        path=path,
        center_line=900,
        context_lines=30,
        max_bytes=20_000,
    )

    assert excerpt is not None
    assert "900: line_900" in excerpt["content"]
    assert "1: line_1" not in excerpt["content"]


@pytest.mark.asyncio
async def test_watch_logs_handles_single_log_failure_and_keeps_running():
    queue: asyncio.Queue = asyncio.Queue()

    class _Broker:
        def __init__(self):
            self.unregistered = False

        def register(self):
            return queue

        def unregister(self, _q):
            self.unregistered = True

    route = ErrorAnalysisRoute.__new__(ErrorAnalysisRoute)
    route.log_broker = _Broker()
    calls = {"count": 0}

    async def _handle_log(_item):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")

    route._handle_log = _handle_log

    task = asyncio.create_task(route._watch_logs())
    await queue.put({"n": 1})
    await queue.put({"n": 2})

    for _ in range(20):
        if calls["count"] >= 2:
            break
        await asyncio.sleep(0.01)

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert calls["count"] >= 2
    assert route.log_broker.unregistered is True
