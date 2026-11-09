import httpx
import pytest

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.elevenlabs_tts_source import (
    ProviderElevenLabsTTSAPI,
)


def _template() -> dict:
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    return dict(templates["Audexum TTS(API)"])


@pytest.mark.asyncio
async def test_audexum_template_posts_to_elevenlabs_compatible_route(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "astrbot.core.provider.sources.elevenlabs_tts_source.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    config = _template()
    config["api_key"] = "sk_live_test"
    provider = ProviderElevenLabsTTSAPI(config, {})
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["xi-api-key"]
        return httpx.Response(200, content=b"ID3audio")

    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    path = await provider.get_audio("hello")
    await provider.terminate()

    assert config["type"] == "elevenlabs_tts_api"
    assert seen["url"].startswith("https://audexum.com/v1/text-to-speech/Nova")
    assert seen["key"] == "sk_live_test"
    assert path.endswith(".mp3")
