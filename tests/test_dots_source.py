import httpx
import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.dots_source import ProviderDots
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


@pytest.mark.asyncio
async def test_dots_authentication_follows_request_key_rotation(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {
                        "id": "dots3-note-prev",
                        "object": "model",
                        "created": 0,
                        "owned_by": "dots",
                    }
                ],
            },
        )

    monkeypatch.setattr(
        ProviderOpenAIOfficial,
        "_create_http_client",
        lambda self, config: httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]["Dots"]
    config = {
        **template,
        "key": ["first-key", "second-key"],
        "custom_headers": {"X-Test": "preserved"},
    }
    provider = ProviderDots(config, {})
    try:
        assert provider.get_model() == "dots3-note-prev"
        assert await provider.get_models() == ["dots3-note-prev"]
        # Chat retries also assign client.api_key directly rather than calling set_key.
        provider.client.api_key = "second-key"
        assert await provider.get_models() == ["dots3-note-prev"]
        assert [request.headers["api-key"] for request in requests] == [
            "first-key",
            "second-key",
        ]
        assert all("authorization" not in request.headers for request in requests)
        assert all(request.headers["X-Test"] == "preserved" for request in requests)
        assert all(
            str(request.url) == "https://note3-prev-api.askdiandian.com/v1/models"
            for request in requests
        )
        assert "model" not in config
    finally:
        await provider.terminate()
