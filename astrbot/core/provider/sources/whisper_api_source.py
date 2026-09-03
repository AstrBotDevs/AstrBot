from openai import NOT_GIVEN, AsyncOpenAI

from astrbot.core.utils.media_utils import MediaResolver

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

        # Optional transcription hints. Empty values fall back to NOT_GIVEN so
        # that Whisper keeps auto-detecting the language, matching the previous
        # behavior for users who do not configure these fields.
        self.language = str(provider_config.get("language") or "").strip()
        self.prompt = str(provider_config.get("prompt") or "").strip()

        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=provider_config.get("api_base"),
            timeout=provider_config.get("timeout", NOT_GIVEN),
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
                    language=self.language or NOT_GIVEN,
                    prompt=self.prompt or NOT_GIVEN,
                )
        return result.text

    async def terminate(self):
        if self.client:
            await self.client.close()
