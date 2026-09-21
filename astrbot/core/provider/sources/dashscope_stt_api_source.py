import httpx
from astrbot import logger
from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter
from astrbot.core.utils.media_utils import MediaResolver, describe_media_ref


DEFAULT_DASHSCOPE_STT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_DASHSCOPE_STT_MODEL = "qwen3-asr-flash"


class DashScopeAPIError(Exception):
    pass


def normalize_timeout(timeout: int | str | None) -> int | None:
    if timeout in (None, ""):
        return None
    if isinstance(timeout, str):
        return int(timeout)
    return timeout


def build_headers(api_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def build_api_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return normalized + "/chat/completions"


@register_provider_adapter(
    "dashscope_stt",
    "阿里云百炼 STT (Qwen3-ASR)",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderDashScopeSTT(STTProvider):
    def __init__(self, provider_config: dict, provider_settings: dict):
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        if not self.api_key:
            raise ValueError("DashScope STT requires an API key.")
        self.base_url = (
            provider_config.get("api_base") or
            provider_config.get("base_url") or
            DEFAULT_DASHSCOPE_STT_BASE
        )
        self.model = provider_config.get("model", DEFAULT_DASHSCOPE_STT_MODEL)
        self.language = provider_config.get("language", "") or None
        self.enable_itn = provider_config.get("enable_itn", False)
        self.timeout = normalize_timeout(provider_config.get("timeout", 20))
        self.proxy = provider_config.get("proxy", "")
        self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            kwargs = {"timeout": self.timeout, "follow_redirects": True}
            if self.proxy:
                kwargs["proxy"] = self.proxy
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    async def get_text(self, audio_url: str) -> str:
        """
        Transcribe audio from the given source using DashScope Qwen3-ASR.

        The audio source can be a local file path, a remote HTTP/HTTPS URL, or a
        base64-encoded data URI. The MediaResolver will attempt to convert it to a
        proper Data URL (data:audio/...;base64,<data>) with WAV format.

        This method uses DashScope's OpenAI-compatible endpoint:
            POST /v1/chat/completions

        The request includes:
            - model: qwen3-asr-flash (or custom)
            - messages: a user message with content of type "input_audio"
            - asr_options: optionally specifies language and ITN (Inverse Text Normalization)
            - stream: False (non-streaming response)

        Args:
            audio_url (str): A media reference supported by MediaResolver, e.g.,
                - HTTP/HTTPS URL to an audio file
                - Local file path (absolute or relative)
                - Base64 data URI (if already in proper format, it will be used as-is)

        Returns:
            str: The transcribed text from the audio.

        Raises:
            ValueError: If the audio source cannot be resolved or converted.
            DashScopeAPIError: If the API request fails (HTTP error, malformed response,
                empty transcription result, or invalid parameters).
            httpx.HTTPStatusError: If the underlying HTTP request fails (propagated if
                not caught by the adapter).

        Note:
            - The audio file size (original) must be <= 10 MB; base64 encoding increases
            size by ~33%, so ensure original file is <= 7.5 MB.
            - This implementation uses non-streaming mode; for long audio (e.g., > 60s),
            consider using the async file transcription model qwen3-asr-flash-filetrans.
        """
        # 1. Obtain audio data
        audio_data = await MediaResolver(
            audio_url,
            media_type="audio",
            default_suffix=".wav",
        ).to_base64_data(strict=True, target_format="wav")

        if audio_data is None:
            raise ValueError(f"Failed to parse audio source: {describe_media_ref(audio_url)}")

        # 2. Build data URI
        data_uri = audio_data.to_data_url()

        # 3. Build request body
        content = [{"type": "input_audio", "input_audio": {"data": data_uri}}]
        asr_options = {}
        if self.language:
            asr_options["language"] = self.language
        if self.enable_itn is not None:
            asr_options["enable_itn"] = self.enable_itn

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }
        if asr_options:
            payload["asr_options"] = asr_options

        # 4. Send request
        client = self._get_client()
        url = build_api_url(self.base_url)
        resp = await client.post(url, headers=build_headers(self.api_key), json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            error_text = resp.text[:1024]
            raise DashScopeAPIError(
                f"DashScope STT request failed (HTTP {resp.status_code}): {error_text}"
            ) from e

        data = resp.json()
        choices = data.get("choices")
        if not choices:
            raise DashScopeAPIError(f"No choices in response: {data}")

        first = choices[0]
        message = first.get("message") or {}
        content_text = message.get("content", "")
        if not isinstance(content_text, str) or not content_text.strip():
            raise DashScopeAPIError(f"The recognition result is empty: {data}")

        return content_text.strip()

    async def terminate(self):
        if self._client:
            await self._client.aclose()
            self._client = None
