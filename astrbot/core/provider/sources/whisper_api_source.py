import httpx
from openai import NOT_GIVEN, AsyncOpenAI

from astrbot.core.utils.media_utils import MediaResolver
from astrbot.core.utils.network_utils import create_proxy_client

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "openai_whisper_api",
    "OpenAI Whisper API",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderOpenAIWhisperAPI(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        proxy = provider_config.get("proxy", "")
        httpx_module = httpx
        try:
            # The OpenAI SDK can bundle its own compatible httpx module.
            from openai import _base_client as openai_base_client

            httpx_module = getattr(openai_base_client, "httpx", httpx)
        except ImportError:
            pass
        http_client = create_proxy_client(
            "OpenAI Whisper", proxy, httpx_module=httpx_module
        )

        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=provider_config.get("api_base"),
            timeout=provider_config.get("timeout", NOT_GIVEN),
            http_client=http_client,
        )

        self.set_model(provider_config["model"])

    async def get_text(self, audio_url: str) -> str:
        """Only supports mp3, mp4, mpeg, m4a, wav, webm"""
        async with MediaResolver(
            audio_url,
            media_type="audio",
            default_suffix=".wav",
        ).as_path(target_format="wav") as audio:
            with audio.open("rb") as audio_file:
                result = await self.client.audio.transcriptions.create(
                    model=self.model_name,
                    file=("audio.wav", audio_file),
                )
        return result.text

    async def terminate(self):
        if self.client:
            await self.client.close()
