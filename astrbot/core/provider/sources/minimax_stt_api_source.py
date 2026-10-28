import httpx

from astrbot.core.utils.media_utils import MediaResolver

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter

DEFAULT_MINIMAX_STT_API_BASE = "https://api.minimaxi.com/v1"
DEFAULT_MINIMAX_STT_MODEL = "asr-1.0"
# MiniMax rejects payloads larger than 50 MB with HTTP 413.
MINIMAX_STT_MAX_AUDIO_SIZE = 50 * 1024 * 1024


@register_provider_adapter(
    "minimax_stt_api",
    "MiniMax STT API",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderMiniMaxSTTAPI(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get("api_base", DEFAULT_MINIMAX_STT_API_BASE)
        self.proxy = provider_config.get("proxy", "")
        timeout = provider_config.get("timeout", 120)
        self.timeout = int(timeout) if timeout not in (None, "") else 120
        self.set_model(provider_config.get("model", DEFAULT_MINIMAX_STT_MODEL))

        client_kwargs: dict = {
            "timeout": self.timeout,
            "follow_redirects": True,
        }
        if self.proxy:
            client_kwargs["proxy"] = self.proxy
        self.client = httpx.AsyncClient(**client_kwargs)

    def _build_transcription_url(self) -> str:
        """Build the full transcription endpoint URL.

        The API base may be given either as the platform root
        (``https://api.minimaxi.com/v1``) or as the complete endpoint, so the
        path suffix is only appended when it is missing.

        Returns:
            The URL to POST the audio file to.
        """
        normalized = self.api_base.rstrip("/")
        if normalized.endswith("/speech_to_text"):
            return normalized
        return f"{normalized}/speech_to_text"

    async def get_text(self, audio_url: str) -> str:
        """Transcribe an audio file with the MiniMax speech-to-text API.

        Args:
            audio_url: Audio reference (local path, URL or data URI).

        Returns:
            The transcribed text.

        Raises:
            Exception: Raised when the API rejects the request or returns no
                transcription.
        """
        async with MediaResolver(
            audio_url,
            media_type="audio",
            default_suffix=".wav",
        ).as_path(preserve_mp3=True) as audio:
            audio_bytes = audio.read_bytes()
            audio_format = audio.format or "wav"
            audio_mime_type = audio.mime_type or f"audio/{audio_format}"

        if not audio_bytes:
            raise Exception("MiniMax STT API received an empty audio payload")
        if len(audio_bytes) > MINIMAX_STT_MAX_AUDIO_SIZE:
            raise Exception(
                "MiniMax STT API accepts at most 50 MB of audio per request, "
                f"got {len(audio_bytes) // (1024 * 1024)} MB"
            )

        headers = {"Authorization": f"Bearer {self.chosen_api_key}"}
        headers.update(self.request_headers)

        response = await self.client.post(
            self._build_transcription_url(),
            headers=headers,
            data={
                "model": self.model_name,
                "response_format": "json",
            },
            files={
                "file": (
                    f"audio.{audio_format}",
                    audio_bytes,
                    audio_mime_type,
                ),
            },
        )

        if response.status_code != 200:
            raise Exception(
                f"MiniMax STT API request failed: HTTP {response.status_code}, "
                f"response: {response.text[:1024]}"
            )

        result = response.json()
        text = result.get("text", "")
        if not isinstance(text, str) or not text.strip():
            raise Exception("MiniMax STT API returned an empty transcription")
        return text.strip()

    async def terminate(self):
        if self.client:
            await self.client.aclose()
