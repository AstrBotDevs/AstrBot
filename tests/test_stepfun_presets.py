import copy
import json

import httpx
import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preset", "base_url"),
    [
        ("StepFun", "https://api.stepfun.com/v1"),
        ("StepFun Step Plan", "https://api.stepfun.com/step_plan/v1"),
    ],
)
@pytest.mark.parametrize("stream", [False, True])
async def test_stepfun_presets_route_models_and_chat(
    monkeypatch, preset, base_url, stream
):
    config = copy.deepcopy(
        CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]["config_template"][
            preset
        ]
    )
    assert config["type"] == "openai_chat_completion"
    assert config["provider_type"] == "chat_completion"
    assert config["api_base"] == base_url
    config.update(
        key=["test-stepfun-key"],
        model="step-3.5-flash",
        timeout=45,
        custom_headers={"X-Test-Header": "stepfun"},
        custom_extra_body={"reasoning_effort": "high", "max_tokens": 8192},
    )
    requests = []

    def handle(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [{"id": "step-3.5-flash", "object": "model"}],
                },
            )
        message = {"role": "assistant", "content": "Hello"}
        response = {
            "id": "test-completion",
            "object": "chat.completion.chunk" if stream else "chat.completion",
            "created": 0,
            "model": "step-3.5-flash",
            "choices": [
                {
                    "index": 0,
                    "delta" if stream else "message": message,
                    "finish_reason": "stop",
                }
            ],
        }
        if stream:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=f"data: {json.dumps(response)}\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(200, json=response)

    monkeypatch.setattr(
        ProviderOpenAIOfficial,
        "_create_http_client",
        staticmethod(
            lambda config: httpx.AsyncClient(transport=httpx.MockTransport(handle))
        ),
    )
    provider = ProviderOpenAIOfficial(config, {})
    try:
        assert await provider.get_models() == ["step-3.5-flash"]
        if stream:
            responses = [
                response async for response in provider.text_chat_stream(prompt="Hi")
            ]
            assert any(response.completion_text == "Hello" for response in responses)
        else:
            assert (await provider.text_chat(prompt="Hi")).completion_text == "Hello"
        assert [str(request.url) for request in requests] == [
            f"{base_url}/models",
            f"{base_url}/chat/completions",
        ]
        assert requests[1].headers["Authorization"] == "Bearer test-stepfun-key"
        assert requests[1].headers["X-Test-Header"] == "stepfun"
        payload = json.loads(requests[1].content)
        assert payload["model"] == "step-3.5-flash"
        assert payload["reasoning_effort"] == "high"
        assert payload["max_tokens"] == 8192
        assert payload.get("stream", False) is stream
        assert requests[1].extensions["timeout"]["read"] == 45
    finally:
        await provider.terminate()
