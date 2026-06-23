import builtins
from types import SimpleNamespace

import httpx
import pytest

import astrbot.core.provider.sources.anthropic_source as anthropic_source
import astrbot.core.provider.sources.kimi_code_source as kimi_code_source
import astrbot.core.provider.sources.request_retry as request_retry
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.provider.entities import LLMResponse


class _FakeAsyncAnthropic:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def close(self):
        return None


def test_anthropic_provider_passes_custom_headers_via_default_headers(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = anthropic_source.ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
            "custom_headers": {
                "User-Agent": "custom-agent/1.0",
                "X-Test-Header": 123,
            },
        },
        provider_settings={},
    )

    assert provider.custom_headers == {
        "User-Agent": "custom-agent/1.0",
        "X-Test-Header": "123",
    }
    # Custom headers are forwarded via the SDK's `default_headers` parameter,
    # not via a custom http_client (which is reserved for proxy configuration).
    assert provider.client.kwargs["default_headers"] == {
        "User-Agent": "custom-agent/1.0",
        "X-Test-Header": "123",
    }
    assert provider.client.kwargs["http_client"] is None


def test_kimi_code_provider_sets_defaults_and_preserves_custom_headers(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = kimi_code_source.ProviderKimiCode(
        provider_config={
            "id": "kimi-code",
            "type": "kimi_code_chat_completion",
            "key": ["test-key"],
            "custom_headers": {"X-Trace-Id": "trace-1"},
        },
        provider_settings={},
    )

    assert provider.base_url == kimi_code_source.KIMI_CODE_API_BASE
    assert provider.get_model() == kimi_code_source.KIMI_CODE_DEFAULT_MODEL
    assert provider.custom_headers == {
        "User-Agent": kimi_code_source.KIMI_CODE_USER_AGENT,
        "X-Trace-Id": "trace-1",
    }
    assert provider.client.kwargs["default_headers"] == {
        "User-Agent": kimi_code_source.KIMI_CODE_USER_AGENT,
        "X-Trace-Id": "trace-1",
    }


def test_kimi_code_provider_restores_required_user_agent_when_blank(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = kimi_code_source.ProviderKimiCode(
        provider_config={
            "id": "kimi-code",
            "type": "kimi_code_chat_completion",
            "key": ["test-key"],
            "custom_headers": {"User-Agent": "   "},
        },
        provider_settings={},
    )

    assert provider.custom_headers == {
        "User-Agent": kimi_code_source.KIMI_CODE_USER_AGENT,
    }


def test_create_http_client_returns_none_when_no_proxy(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_proxy_client should not be called without a proxy")

    monkeypatch.setattr(anthropic_source, "create_proxy_client", fail_if_called)

    provider = anthropic_source.ProviderAnthropic.__new__(
        anthropic_source.ProviderAnthropic
    )
    provider.custom_headers = {"X-Trace-Id": "abc"}

    assert provider._create_http_client({"proxy": ""}) is None


def test_create_http_client_uses_anthropic_httpx_module(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_proxy_client(
        provider_label: str,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        verify=None,
        httpx_module=None,
    ):
        captured["provider_label"] = provider_label
        captured["proxy"] = proxy
        captured["headers"] = headers
        captured["httpx_module"] = httpx_module
        return object()

    monkeypatch.setattr(
        anthropic_source, "create_proxy_client", fake_create_proxy_client
    )

    provider = anthropic_source.ProviderAnthropic.__new__(
        anthropic_source.ProviderAnthropic
    )
    provider.custom_headers = {"X-Trace-Id": "trace-1"}
    provider._create_http_client({"proxy": "http://127.0.0.1:7890"})

    from anthropic import _base_client as anthropic_base_client

    assert captured["provider_label"] == "Anthropic"
    assert captured["proxy"] == "http://127.0.0.1:7890"
    assert captured["headers"] == {"X-Trace-Id": "trace-1"}
    assert captured["httpx_module"] is anthropic_base_client.httpx


def test_create_http_client_falls_back_to_global_httpx_module(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_proxy_client(
        provider_label: str,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        verify=None,
        httpx_module=None,
    ):
        captured["httpx_module"] = httpx_module
        return object()

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "anthropic" and fromlist:
            raise ImportError("missing anthropic._base_client")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(
        anthropic_source, "create_proxy_client", fake_create_proxy_client
    )
    monkeypatch.setattr(builtins, "__import__", fake_import)

    provider = anthropic_source.ProviderAnthropic.__new__(
        anthropic_source.ProviderAnthropic
    )
    provider.custom_headers = None
    provider._create_http_client({"proxy": "http://127.0.0.1:7890"})

    assert captured["httpx_module"] is anthropic_source.httpx


@pytest.mark.asyncio
async def test_anthropic_get_models_retries_transient_request_error(monkeypatch):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 0)

    class FakeModels:
        def __init__(self):
            self.calls = 0

        async def list(self):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("temporary connection failure")
            return SimpleNamespace(
                data=[
                    SimpleNamespace(id="claude-b"),
                    SimpleNamespace(id="claude-a"),
                ]
            )

    models = FakeModels()
    provider = anthropic_source.ProviderAnthropic.__new__(
        anthropic_source.ProviderAnthropic
    )
    provider.client = SimpleNamespace(models=models)

    assert await provider.get_models() == ["claude-a", "claude-b"]
    assert models.calls == 2


@pytest.mark.asyncio
async def test_text_chat_wraps_string_system_prompt_as_list(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = anthropic_source.ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
        },
        provider_settings={},
    )

    captured_payloads: dict[str, object] = {}

    async def fake_query(payloads, tools, *, request_max_retries=None):
        captured_payloads.update(payloads)
        return LLMResponse(role="assistant", completion_text="ok")

    monkeypatch.setattr(provider, "_query", fake_query)

    await provider.text_chat(prompt="hello", system_prompt="You are helpful.")

    assert captured_payloads["system"] == [{"type": "text", "text": "You are helpful."}]


@pytest.mark.asyncio
async def test_text_chat_passes_through_list_system_prompt(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = anthropic_source.ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
        },
        provider_settings={},
    )

    captured_payloads: dict[str, object] = {}

    async def fake_query(payloads, tools, *, request_max_retries=None):
        captured_payloads.update(payloads)
        return LLMResponse(role="assistant", completion_text="ok")

    monkeypatch.setattr(provider, "_query", fake_query)

    structured_system = [
        {"type": "text", "text": "Persona block."},
        {"type": "text", "text": "Style guide."},
    ]
    await provider.text_chat(prompt="hello", system_prompt=structured_system)

    assert captured_payloads["system"] == structured_system


def test_anthropic_empty_output_raises_empty_model_output_error():
    llm_response = LLMResponse(role="assistant")

    with pytest.raises(EmptyModelOutputError):
        anthropic_source.ProviderAnthropic._ensure_usable_response(
            llm_response,
            completion_id="msg_empty",
            stop_reason="end_turn",
        )


def _make_anthropic_provider_for_payload_tests() -> anthropic_source.ProviderAnthropic:
    return anthropic_source.ProviderAnthropic(
        provider_config={"model": "claude-test"},
        provider_settings={},
        use_api_key=False,
    )


def test_prepare_payload_merges_consecutive_tool_results_into_single_user_message():
    provider = _make_anthropic_provider_for_payload_tests()

    _, new_messages = provider._prepare_payload(
        [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Reading files"}],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_00",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/one.txt"}',
                        },
                    },
                    {
                        "type": "function",
                        "id": "call_01",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/two.txt"}',
                        },
                    },
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_00",
                "content": "one",
            },
            {
                "role": "tool",
                "tool_call_id": "call_01",
                "content": "two",
            },
        ]
    )

    assert len(new_messages) == 2
    assert new_messages[1]["role"] == "user"
    assert new_messages[1]["content"] == [
        {"type": "tool_result", "tool_use_id": "call_00", "content": "one"},
        {"type": "tool_result", "tool_use_id": "call_01", "content": "two"},
    ]


def test_prepare_payload_keeps_single_tool_result_as_single_user_message():
    provider = _make_anthropic_provider_for_payload_tests()

    _, new_messages = provider._prepare_payload(
        [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Reading file"}],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_00",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/one.txt"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_00",
                "content": "one",
            },
        ]
    )

    assert len(new_messages) == 2
    assert new_messages[1] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "call_00", "content": "one"}
        ],
    }


def test_prepare_payload_does_not_merge_non_consecutive_tool_results():
    provider = _make_anthropic_provider_for_payload_tests()

    _, new_messages = provider._prepare_payload(
        [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "First tool"}],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_00",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/one.txt"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_00",
                "content": "one",
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Second tool"}],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_01",
                        "function": {
                            "name": "astrbot_file_read_tool",
                            "arguments": '{"path": "/tmp/two.txt"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_01",
                "content": "two",
            },
        ]
    )

    assert new_messages == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "First tool"},
                {
                    "type": "tool_use",
                    "name": "astrbot_file_read_tool",
                    "input": {"path": "/tmp/one.txt"},
                    "id": "call_00",
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_00", "content": "one"}
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Second tool"},
                {
                    "type": "tool_use",
                    "name": "astrbot_file_read_tool",
                    "input": {"path": "/tmp/two.txt"},
                    "id": "call_01",
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_01", "content": "two"}
            ],
        },
    ]


# ---- tool_choice 转换测试 ----


class _FakeToolSet:
    """模拟包含工具的 ToolSet"""

    def get_func_desc_anthropic_style(self):
        return [{"name": "get_weather", "description": "Get weather"}]

    def empty(self):
        return False


class _EmptyToolSet:
    """模拟空工具列表的 ToolSet，用于验证无工具时不设置 tool_choice"""

    def get_func_desc_anthropic_style(self):
        return []

    def empty(self):
        return True


class _FakeMessages:
    """模拟 AsyncAnthropic.messages 命名空间"""


async def _capture_payloads_create(**kwargs):
    """捕获 payloads 并返回一个真实的 Message 实例"""
    from anthropic.types import Message, TextBlock, Usage

    _capture_payloads_create.last_kwargs = kwargs
    return Message(
        id="msg_fake",
        content=[TextBlock(type="text", text="Hello")],
        model="claude-test",
        role="assistant",
        stop_reason=None,
        stop_sequence=None,
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
    )


def _setup_provider_with_mock_client(monkeypatch) -> anthropic_source.ProviderAnthropic:
    """创建 provider 并 mock 底层 API 调用"""
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)

    provider = anthropic_source.ProviderAnthropic(
        provider_config={
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
        },
        provider_settings={},
    )

    fakeMessages = _FakeMessages()
    fakeMessages.create = _capture_payloads_create
    provider.client.messages = fakeMessages

    return provider


@pytest.mark.asyncio
async def test_query_handles_none_usage_when_content_filtered(monkeypatch):
    provider = _setup_provider_with_mock_client(monkeypatch)
    content_filter_message = (
        "The request was rejected because it was considered high risk"
    )

    class _FakeMessageBlock:
        def __init__(self, text: str):
            self.type = "text"
            self.text = text

    class _FakeMessage:
        def __init__(self):
            self.id = "msg_content_filter"
            self.content = [_FakeMessageBlock(content_filter_message)]
            self.stop_reason = "content_filter"
            self.usage = None

    async def fake_create(**kwargs):
        return _FakeMessage()

    monkeypatch.setattr(anthropic_source, "Message", _FakeMessage)
    provider.client.messages.create = fake_create

    llm_response = await provider.text_chat(prompt="test")

    assert llm_response.completion_text == content_filter_message
    assert llm_response.usage is not None
    assert llm_response.usage.input_other == 0
    assert llm_response.usage.input_cached == 0
    assert llm_response.usage.output == 0


@pytest.mark.asyncio
async def test_tool_choice_auto_converts_to_dict(monkeypatch):
    """tool_choice='auto' 应转换为 {'type': 'auto'}"""
    provider = _setup_provider_with_mock_client(monkeypatch)

    await provider.text_chat(
        prompt="hello",
        func_tool=_FakeToolSet(),
        tool_choice="auto",
    )

    assert _capture_payloads_create.last_kwargs["tool_choice"] == {"type": "auto"}


@pytest.mark.asyncio
async def test_tool_choice_any_converts_to_dict(monkeypatch):
    """tool_choice='any' 应转换为 {'type': 'any'}"""
    provider = _setup_provider_with_mock_client(monkeypatch)

    await provider.text_chat(
        prompt="hello",
        func_tool=_FakeToolSet(),
        tool_choice="any",
    )

    assert _capture_payloads_create.last_kwargs["tool_choice"] == {"type": "any"}


@pytest.mark.asyncio
async def test_tool_choice_none_converts_to_dict(monkeypatch):
    """tool_choice='none' 应转换为 {'type': 'none'}"""
    provider = _setup_provider_with_mock_client(monkeypatch)

    await provider.text_chat(
        prompt="hello",
        func_tool=_FakeToolSet(),
        tool_choice="none",
    )

    assert _capture_payloads_create.last_kwargs["tool_choice"] == {"type": "none"}


@pytest.mark.asyncio
async def test_tool_choice_required_legacy_compat(monkeypatch):
    """tool_choice='required'(OpenAI 命名) 应兼容转换为 {'type': 'any'}"""
    provider = _setup_provider_with_mock_client(monkeypatch)

    await provider.text_chat(
        prompt="hello",
        func_tool=_FakeToolSet(),
        tool_choice="required",
    )

    assert _capture_payloads_create.last_kwargs["tool_choice"] == {"type": "any"}


@pytest.mark.asyncio
async def test_tool_choice_dict_passthrough(monkeypatch):
    """tool_choice 为 dict 时应直接透传"""
    provider = _setup_provider_with_mock_client(monkeypatch)

    await provider.text_chat(
        prompt="hello",
        func_tool=_FakeToolSet(),
        tool_choice={"type": "tool", "name": "get_weather"},
    )

    assert _capture_payloads_create.last_kwargs["tool_choice"] == {
        "type": "tool",
        "name": "get_weather",
    }


@pytest.mark.asyncio
async def test_tool_choice_default_when_not_set(monkeypatch):
    """未传 tool_choice 时，默认应为 {'type': 'auto'}"""
    provider = _setup_provider_with_mock_client(monkeypatch)

    await provider.text_chat(
        prompt="hello",
        func_tool=_FakeToolSet(),
    )

    assert _capture_payloads_create.last_kwargs["tool_choice"] == {"type": "auto"}


@pytest.mark.asyncio
async def test_tool_choice_invalid_string_falls_back_to_auto(monkeypatch):
    """无效的 tool_choice 字符串应回退为 {'type': 'auto'}"""
    provider = _setup_provider_with_mock_client(monkeypatch)

    await provider.text_chat(
        prompt="hello",
        func_tool=_FakeToolSet(),
        tool_choice="invalid_value",
    )

    assert _capture_payloads_create.last_kwargs["tool_choice"] == {"type": "auto"}


@pytest.mark.asyncio
async def test_tool_choice_no_tools_skips_tool_choice(monkeypatch):
    """无工具时不应设置 tool_choice"""
    provider = _setup_provider_with_mock_client(monkeypatch)

    await provider.text_chat(
        prompt="hello",
        func_tool=None,
        tool_choice="any",
    )

    assert "tool_choice" not in _capture_payloads_create.last_kwargs


@pytest.mark.asyncio
async def test_tool_choice_empty_tool_list_skips_tool_choice(monkeypatch):
    """ToolSet 存在但工具列表为空时，不应设置 tools 和 tool_choice"""
    provider = _setup_provider_with_mock_client(monkeypatch)

    await provider.text_chat(
        prompt="hello",
        func_tool=_EmptyToolSet(),
        tool_choice="any",
    )

    kwargs = _capture_payloads_create.last_kwargs
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs
