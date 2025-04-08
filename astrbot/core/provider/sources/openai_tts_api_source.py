import uuid
from openai import AsyncOpenAI, NOT_GIVEN
from ..provider import TTSProvider
from ..entities import ProviderType
from ..register import register_provider_adapter


@register_provider_adapter(
    "openai_tts_api", "OpenAI TTS API", provider_type=ProviderType.TEXT_TO_SPEECH
)
class ProviderOpenAITTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.voice = provider_config.get("openai-tts-voice", "alloy")

        timeout = provider_config.get("timeout", NOT_GIVEN)
        if isinstance(timeout, str):
            timeout = int(timeout)

        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=provider_config.get("api_base", None),
            timeout=timeout,
        )

        self.set_model(provider_config.get("model", None))

    async def get_audio(self, text: str) -> str:
        path = f"data/temp/openai_tts_api_{uuid.uuid4()}.wav"
        async with self.client.audio.speech.with_streaming_response.create(
            model=self.model_name, voice=self.voice, response_format="wav", input=text
        ) as response:
            with open(path, "wb") as f:
                async for chunk in response.iter_bytes(chunk_size=1024):
                    f.write(chunk)
        return path
