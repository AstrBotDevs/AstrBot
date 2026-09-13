import importlib
import json
import sys
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from astrbot.core.provider.register import provider_cls_map
from astrbot.core.provider.sources import zhipu_coding_plan_source

ProviderZhipuCodingPlan = zhipu_coding_plan_source.ProviderZhipuCodingPlan


def test_dynamic_import_registers_zhipu_coding_plan_provider():
    provider_type = "zhipu_coding_plan_chat_completion"
    provider_cls_map.pop(provider_type, None)

    module = importlib.reload(zhipu_coding_plan_source)

    assert provider_type in provider_cls_map
    assert module.ProviderZhipuCodingPlan is not None


def _make_provider(overrides: dict | None = None) -> ProviderZhipuCodingPlan:
    provider_config = {
        "id": "zhipu-coding-plan-test",
        "type": "zhipu_coding_plan_chat_completion",
        "key": ["test-key"],
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderZhipuCodingPlan(provider_config, {})


@pytest.mark.asyncio
async def test_provider_uses_coding_plan_defaults_and_static_models():
    api_base = getattr(zhipu_coding_plan_source, "ZHIPU_CODING_PLAN_API_BASE", None)
    default_model = getattr(
        zhipu_coding_plan_source, "ZHIPU_CODING_PLAN_DEFAULT_MODEL", None
    )
    models = getattr(zhipu_coding_plan_source, "ZHIPU_CODING_PLAN_MODELS", None)

    assert api_base == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert default_model == "glm-5.3"
    assert models == [
        "glm-5.3",
        "glm-5.3-flash",
        "glm-5.2",
        "glm-5-turbo",
        "glm-5v-turbo",
        "glm-5.1",
        "glm-4.7",
    ]

    provider = _make_provider()

    assert str(provider.client.base_url).rstrip("/") == api_base
    assert provider.get_model() == default_model
    assert provider.provider_config["custom_extra_body"] == {}
    assert await provider.get_models() == models


def test_provider_preserves_explicit_global_coding_plan_endpoint():
    global_api_base = getattr(
        zhipu_coding_plan_source,
        "ZHIPU_CODING_PLAN_GLOBAL_API_BASE",
        None,
    )
    assert global_api_base == "https://api.z.ai/api/coding/paas/v4"

    provider = _make_provider({"api_base": global_api_base})

    assert str(provider.client.base_url).rstrip("/") == global_api_base


@pytest.mark.parametrize("blank_value", ["", "   "])
def test_provider_replaces_blank_coding_plan_defaults(blank_value):
    provider = _make_provider({"api_base": blank_value, "model": blank_value})

    assert str(provider.client.base_url).rstrip("/") == (
        zhipu_coding_plan_source.ZHIPU_CODING_PLAN_API_BASE
    )
    assert (
        provider.get_model() == zhipu_coding_plan_source.ZHIPU_CODING_PLAN_DEFAULT_MODEL
    )


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ("off", "low"),
        ("none", "low"),
        ("minimal", "low"),
        ("low", "low"),
        ("medium", "high"),
        ("high", "high"),
        ("xhigh", "max"),
        ("adaptive", "max"),
        ("max", "max"),
        ("ultra", "max"),
    ],
)
def test_glm_53_reasoning_effort_matches_openclaw_policy(requested, expected):
    extra_body = {
        "reasoning_effort": requested,
        "temperature": 0.2,
    }

    zhipu_coding_plan_source._apply_reasoning_policy("glm-5.3", extra_body)

    assert extra_body == {
        "reasoning_effort": expected,
        "temperature": 0.2,
    }


@pytest.mark.parametrize(
    ("requested", "expected_effort"),
    [
        ("low", "high"),
        ("medium", "high"),
        ("high", "high"),
        ("adaptive", "high"),
        ("xhigh", "max"),
        ("max", "max"),
        ("ultra", "max"),
    ],
)
def test_glm_52_reasoning_effort_matches_openclaw_policy(
    requested,
    expected_effort,
):
    extra_body = {"reasoning_effort": requested}

    zhipu_coding_plan_source._apply_reasoning_policy("glm-5.2", extra_body)

    assert extra_body == {"reasoning_effort": expected_effort}


@pytest.mark.parametrize("requested", ["off", "none"])
def test_glm_52_can_disable_thinking(requested):
    extra_body = {"reasoning_effort": requested}

    zhipu_coding_plan_source._apply_reasoning_policy("glm-5.2", extra_body)

    assert extra_body == {"thinking": {"type": "disabled"}}


def test_glm_52_defaults_to_thinking_disabled():
    extra_body = {}

    zhipu_coding_plan_source._apply_reasoning_policy("glm-5.2", extra_body)

    assert extra_body == {"thinking": {"type": "disabled"}}


def test_glm_52_preserves_explicit_thinking_enabled():
    extra_body = {"thinking": {"type": "enabled"}}

    zhipu_coding_plan_source._apply_reasoning_policy("glm-5.2", extra_body)

    assert extra_body == {"thinking": {"type": "enabled"}}


@pytest.mark.parametrize("model", ["glm-5.1", "glm-4.7"])
def test_legacy_models_drop_unsupported_reasoning_effort(model):
    extra_body = {"reasoning_effort": "max", "temperature": 0.2}

    zhipu_coding_plan_source._apply_reasoning_policy(model, extra_body)

    assert extra_body == {"temperature": 0.2}


@pytest.mark.parametrize(
    ("model", "extra_body", "expected"),
    [
        (
            "glm-5.2",
            {"reasoning_effort": "off", "thinking": {"type": "enabled"}},
            {"thinking": {"type": "disabled"}},
        ),
        (
            "glm-5.2",
            {"reasoning_effort": "high", "thinking": {"type": "disabled"}},
            {"reasoning_effort": "high"},
        ),
        (
            "glm-5.3",
            {"reasoning_effort": "none", "thinking": {"type": "disabled"}},
            {"reasoning_effort": "low"},
        ),
    ],
)
def test_reasoning_policy_removes_conflicting_thinking_state(
    model,
    extra_body,
    expected,
):
    zhipu_coding_plan_source._apply_reasoning_policy(model, extra_body)

    assert extra_body == expected


@pytest.mark.asyncio
async def test_non_stream_request_uses_reasoning_policy_without_openclaw_identity():
    provider = _make_provider(
        {
            "custom_headers": {"X-Test-Header": "test-value"},
            "custom_extra_body": {"reasoning_effort": "medium"},
        }
    )
    captured: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-zhipu-test",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "glm-5.3",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                }
            )

    provider.client = SimpleNamespace(
        api_key="test-key",
        chat=SimpleNamespace(completions=FakeCompletions()),
    )

    response = await provider._query(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "ping"}]},
        None,
        request_max_retries=1,
    )

    assert response.completion_text == "ok"
    assert captured["stream"] is False
    assert captured["extra_body"] == {"reasoning_effort": "high"}
    assert provider.custom_headers == {"X-Test-Header": "test-value"}
    assert "User-Agent" not in provider.custom_headers


@pytest.mark.asyncio
async def test_runtime_model_override_recomputes_reasoning_policy():
    provider = _make_provider(
        {
            "model": "glm-5.2",
            "custom_extra_body": {"reasoning_effort": "off"},
        }
    )
    captured: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return ChatCompletion.model_validate(
                {
                    "id": "chatcmpl-zhipu-override",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "glm-5.3",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                }
            )

    provider.client = SimpleNamespace(
        api_key="test-key",
        chat=SimpleNamespace(completions=FakeCompletions()),
    )

    await provider._query(
        {"model": "glm-5.3", "messages": [{"role": "user", "content": "ping"}]},
        None,
        request_max_retries=1,
    )

    assert captured["extra_body"] == {"reasoning_effort": "low"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "configured_effort", "requested_effort", "expected"),
    [
        ("glm-5.1", "max", "max", {}),
        ("glm-5.2", "off", "max", {"reasoning_effort": "max"}),
        ("glm-5.3", "max", "low", {"reasoning_effort": "low"}),
    ],
)
async def test_request_reasoning_effort_is_normalized_on_the_wire(
    model,
    configured_effort,
    requested_effort,
    expected,
):
    provider = _make_provider(
        {
            "model": model,
            "custom_extra_body": {"reasoning_effort": configured_effort},
        }
    )
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        captured["user_agent"] = request.headers.get("user-agent", "")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-zhipu-wire",
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider.client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.test/v1",
        http_client=http_client,
    )

    try:
        await provider._query(
            {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "reasoning_effort": requested_effort,
            },
            None,
            request_max_retries=1,
        )
    finally:
        await provider.client.close()

    actual_policy = {
        key: captured[key]
        for key in ("reasoning_effort", "thinking")
        if key in captured
    }
    assert actual_policy == expected
    assert "openclaw" not in captured["user_agent"].lower()


@pytest.mark.asyncio
async def test_stream_request_uses_coding_plan_reasoning_policy():
    provider = _make_provider({"custom_extra_body": {"reasoning_effort": "xhigh"}})
    captured: dict = {}
    chunks = [
        ChatCompletionChunk.model_validate(
            {
                "id": "chatcmpl-zhipu-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "glm-5.3",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "ok"},
                        "finish_reason": None,
                    }
                ],
            }
        ),
        ChatCompletionChunk.model_validate(
            {
                "id": "chatcmpl-zhipu-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "glm-5.3",
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
            }
        ),
        ChatCompletionChunk.model_validate(
            {
                "id": "chatcmpl-zhipu-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "glm-5.3",
                "choices": [],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        ),
    ]

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if not chunks:
                raise StopAsyncIteration
            return chunks.pop(0)

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream()

    provider.client = SimpleNamespace(
        api_key="test-key",
        chat=SimpleNamespace(completions=FakeCompletions()),
    )

    responses = [
        response
        async for response in provider._query_stream(
            {
                "model": "glm-5.3",
                "messages": [{"role": "user", "content": "ping"}],
            },
            None,
            request_max_retries=1,
        )
    ]

    assert captured["stream"] is True
    assert captured["extra_body"] == {"reasoning_effort": "max"}
    assert responses[-1].completion_text == "ok"


@pytest.mark.asyncio
async def test_stream_tool_call_enables_tool_stream_and_parses_arguments():
    provider = _make_provider()
    captured: dict = {}
    chunks = [
        ChatCompletionChunk.model_validate(
            {
                "id": "chatcmpl-zhipu-tool",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "glm-5.3",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup",
                                        "arguments": '{"query":',
                                    },
                                }
                            ],
                        },
                        "finish_reason": None,
                    }
                ],
            }
        ),
        ChatCompletionChunk.model_validate(
            {
                "id": "chatcmpl-zhipu-tool",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "glm-5.3",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": '"value"}'},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
        ),
    ]

    class FakeToolSet:
        def get_func_desc_openai_style(self, **_kwargs):
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Lookup a value",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    },
                }
            ]

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if not chunks:
                raise StopAsyncIteration
            return chunks.pop(0)

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream()

    provider.client = SimpleNamespace(
        api_key="test-key",
        chat=SimpleNamespace(completions=FakeCompletions()),
    )

    responses = [
        response
        async for response in provider._query_stream(
            {
                "model": "glm-5.3",
                "messages": [{"role": "user", "content": "lookup value"}],
            },
            FakeToolSet(),
            request_max_retries=1,
        )
    ]

    assert captured["extra_body"] == {
        "reasoning_effort": "max",
        "tool_stream": True,
    }
    assert captured["tools"][0]["function"]["name"] == "lookup"
    assert captured["stream"] is True
    assert responses[-1].role == "tool"
    assert responses[-1].tools_call_name == ["lookup"]
    assert responses[-1].tools_call_args == [{"query": "value"}]
    assert responses[-1].tools_call_ids == ["call_1"]


def test_provider_manager_dynamic_import_registers_coding_plan_type():
    from astrbot.core.provider.manager import ProviderManager

    provider_type = "zhipu_coding_plan_chat_completion"
    provider_cls_map.pop(provider_type, None)
    sys.modules.pop(
        "astrbot.core.provider.sources.zhipu_coding_plan_source",
        None,
    )

    ProviderManager.dynamic_import_provider(None, provider_type)

    assert provider_type in provider_cls_map


def test_dashboard_template_exposes_separate_zhipu_coding_plan_source():
    from astrbot.core.config.default import CONFIG_METADATA_2

    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    template = templates["Zhipu Coding Plan"]

    assert template["id"] == "zhipu-coding-plan"
    assert template["provider"] == "zhipu"
    assert template["type"] == "zhipu_coding_plan_chat_completion"
    assert template["api_base"] == zhipu_coding_plan_source.ZHIPU_CODING_PLAN_API_BASE
    assert template["custom_extra_body"] == {}
