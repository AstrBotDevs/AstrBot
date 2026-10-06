from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.oauth.openai_oauth_transcription import (
    DEFAULT_MAX_AUDIO_BYTES,
    OpenAIOAuthTranscriptionClient,
)
from astrbot.core.provider.provider import STTProvider
from astrbot.core.provider.register import register_provider_adapter

from .openai_oauth_source import ProviderOpenAIOAuth


@register_provider_adapter(
    "openai_oauth_stt",
    "OpenAI OAuth 音频转录",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderOpenAIOAuthSTT(STTProvider):
    """AstrBot STT adapter backed by the shared OpenAI OAuth state."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Create a lightweight OAuth provider and transcription client.

        Args:
            provider_config: STT settings and injected OAuth shared state.
            provider_settings: AstrBot provider-level settings.
        """
        super().__init__(provider_config, provider_settings)
        oauth_config = dict(provider_config)
        oauth_config["type"] = "openai_oauth_chat_completion"
        oauth_config["model"] = str(
            provider_config.get("oauth_chat_model") or "gpt-5.4"
        )
        self.oauth_provider = ProviderOpenAIOAuth(oauth_config, provider_settings)
        self.client = OpenAIOAuthTranscriptionClient(
            self.oauth_provider,
            max_audio_bytes=int(
                provider_config.get("max_audio_bytes") or DEFAULT_MAX_AUDIO_BYTES
            ),
            timeout=provider_config.get("timeout"),
        )
        self.set_model(str(provider_config.get("model") or "gpt-4o-transcribe").strip())

    async def transcribe_audio(
        self,
        audio_url: str,
        model: str = "gpt-4o-transcribe",
        language: str | None = None,
        prompt: str | None = None,
    ) -> str:
        """Transcribe an audio reference for core or plugin callers.

        Args:
            audio_url: Audio reference accepted by MediaResolver.
            model: OpenAI transcription model name.
            language: Optional ISO-639-1 language hint.
            prompt: Optional transcription context.

        Returns:
            Transcribed text.
        """
        return await self.client.transcribe_audio(
            audio_url,
            model=model,
            language=language,
            prompt=prompt,
        )

    async def get_text(self, audio_url: str) -> str:
        """Transcribe audio using this adapter's configured defaults.

        Args:
            audio_url: Audio reference accepted by MediaResolver.

        Returns:
            Transcribed text.
        """
        return await self.transcribe_audio(
            audio_url,
            model=self.get_model(),
            language=self.provider_config.get("language") or None,
            prompt=self.provider_config.get("prompt") or None,
        )

    async def terminate(self) -> None:
        """Close the lightweight OAuth provider's inherited HTTP client."""
        await self.client.close()
        await self.oauth_provider.terminate()
