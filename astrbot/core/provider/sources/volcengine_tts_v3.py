import asyncio
import base64
import binascii
import json
import uuid
from pathlib import Path

import aiohttp

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import generate_timestamp_id

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

SUPPORTED_AUDIO_FORMATS = {"wav", "mp3", "pcm", "ogg_opus"}
SUPPORTED_SAMPLE_RATES = {8000, 16000, 24000, 32000, 44100, 48000}
AUDIO_FILE_EXTENSIONS = {
    "wav": "wav",
    "mp3": "mp3",
    "pcm": "pcm",
    "ogg_opus": "ogg",
}


@register_provider_adapter(
    "volcengine_tts_v3",
    "火山引擎 TTS(音频生成)",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderVolcengineTTSV3(TTSProvider):
    """Volcengine audio generation HTTP API provider."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize the Volcengine audio generation provider.

        Args:
            provider_config: Provider-specific configuration.
            provider_settings: Shared TTS provider settings.

        Raises:
            ValueError: If an audio configuration value is unsupported.
        """
        super().__init__(provider_config, provider_settings)
        self.api_key = str(provider_config.get("api_key") or "").strip()
        self.api_base = str(provider_config.get("api_base") or "").strip()
        if not self.api_base:
            self.api_base = "https://openspeech.bytedance.com/api/v3/tts/create"
        model = str(provider_config.get("model") or "").strip()
        self.set_model(model or "seed-audio-1.0")
        self.speaker = str(provider_config.get("volcengine_v3_speaker") or "").strip()
        self.audio_format = (
            str(provider_config.get("volcengine_v3_format") or "mp3").strip().lower()
        )
        try:
            self.sample_rate = int(
                provider_config.get("volcengine_v3_sample_rate", 48000)
            )
            self.speech_rate = int(provider_config.get("volcengine_v3_speech_rate", 0))
            self.loudness_rate = int(
                provider_config.get("volcengine_v3_loudness_rate", 0)
            )
            self.pitch_rate = int(provider_config.get("volcengine_v3_pitch_rate", 0))
            self.timeout = int(provider_config.get("timeout", 300))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Volcengine TTS v3 numeric configuration values must be integers."
            ) from exc
        self.proxy = str(provider_config.get("proxy") or "").strip()
        self._session_factory = aiohttp.ClientSession

        if self.audio_format not in SUPPORTED_AUDIO_FORMATS:
            raise ValueError(
                "Unsupported Volcengine TTS v3 audio format: "
                f"{self.audio_format}. Supported formats: "
                f"{', '.join(sorted(SUPPORTED_AUDIO_FORMATS))}."
            )
        if self.sample_rate not in SUPPORTED_SAMPLE_RATES:
            raise ValueError(
                "Unsupported Volcengine TTS v3 sample rate: "
                f"{self.sample_rate}. Supported sample rates: "
                f"{', '.join(str(rate) for rate in sorted(SUPPORTED_SAMPLE_RATES))}."
            )
        if not -50 <= self.speech_rate <= 100:
            raise ValueError(
                "Volcengine TTS v3 speech rate must be between -50 and 100."
            )
        if not -50 <= self.loudness_rate <= 100:
            raise ValueError(
                "Volcengine TTS v3 loudness rate must be between -50 and 100."
            )
        if not -12 <= self.pitch_rate <= 12:
            raise ValueError("Volcengine TTS v3 pitch rate must be between -12 and 12.")
        if self.timeout <= 0:
            raise ValueError("Volcengine TTS v3 timeout must be greater than zero.")

    def _build_payload(self, text: str) -> dict[str, object]:
        """Build a request payload for the audio generation endpoint.

        Args:
            text: Text or prompt to synthesize.

        Returns:
            The JSON-compatible request payload.
        """
        payload: dict[str, object] = {
            "model": self.model_name,
            "text_prompt": text,
            "audio_config": {
                "format": self.audio_format,
                "sample_rate": self.sample_rate,
                "speech_rate": self.speech_rate,
                "loudness_rate": self.loudness_rate,
                "pitch_rate": self.pitch_rate,
            },
        }
        if self.speaker:
            payload["references"] = [{"speaker": self.speaker}]
        return payload

    async def get_audio(self, text: str) -> str:
        """Generate an audio file from text.

        Args:
            text: Text or prompt to synthesize. The API accepts up to 3000
                characters.

        Returns:
            The path to the generated temporary audio file.

        Raises:
            ValueError: If credentials or input text are missing or invalid.
            RuntimeError: If the API request, response parsing, download, or
                file generation fails.
        """
        if not self.api_key:
            raise ValueError("Volcengine TTS v3 API key is required.")
        if not isinstance(text, str):
            raise ValueError("Volcengine TTS v3 text prompt must be a string.")
        if not text.strip():
            raise ValueError("Volcengine TTS v3 text prompt cannot be empty.")
        if len(text) > 3000:
            raise ValueError(
                "Volcengine TTS v3 text prompt cannot exceed 3000 characters."
            )

        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        proxy = self.proxy or None
        payload = self._build_payload(text)

        logger.debug("Sending Volcengine TTS v3 audio generation request.")

        try:
            async with self._session_factory() as session:
                async with session.post(
                    self.api_base,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                    proxy=proxy,
                ) as response:
                    response_text = await response.text()
                    log_id = response.headers.get("X-Tt-Logid", "")
                    logger.debug(
                        f"Volcengine TTS v3 response status: {response.status}"
                    )

                    if response.status != 200:
                        safe_body = (
                            response_text.replace(self.api_key, "***")
                            if self.api_key
                            else response_text
                        )
                        log_suffix = f", log ID: {log_id}" if log_id else ""
                        raise RuntimeError(
                            "Volcengine TTS v3 request failed with status "
                            f"{response.status}{log_suffix}: {safe_body[:200]}"
                        )

                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError as exc:
                        safe_body = (
                            response_text.replace(self.api_key, "***")
                            if self.api_key
                            else response_text
                        )
                        raise RuntimeError(
                            "Volcengine TTS v3 returned invalid JSON: "
                            f"{safe_body[:200]}"
                        ) from exc

                    if not isinstance(response_data, dict):
                        raise RuntimeError(
                            "Volcengine TTS v3 returned a non-object JSON response."
                        )

                error_code = response_data.get("code")
                if error_code not in (None, 0, "0"):
                    error_message = str(
                        response_data.get("message") or "Unknown API error"
                    )
                    if self.api_key:
                        error_message = error_message.replace(self.api_key, "***")
                    log_suffix = f", log ID: {log_id}" if log_id else ""
                    raise RuntimeError(
                        "Volcengine TTS v3 API error "
                        f"{error_code}{log_suffix}: {error_message}"
                    )

                audio_data: bytes
                audio_base64 = response_data.get("audio") or response_data.get("data")
                if audio_base64:
                    if not isinstance(audio_base64, str):
                        raise RuntimeError(
                            "Volcengine TTS v3 returned a non-string audio payload."
                        )
                    try:
                        compact_audio = "".join(audio_base64.split())
                        audio_data = base64.b64decode(compact_audio, validate=True)
                    except (binascii.Error, ValueError) as exc:
                        raise RuntimeError(
                            "Volcengine TTS v3 returned invalid Base64 audio data."
                        ) from exc
                elif isinstance(response_data.get("url"), str) and response_data["url"]:
                    async with session.get(
                        response_data["url"],
                        timeout=timeout,
                        proxy=proxy,
                    ) as audio_response:
                        if audio_response.status != 200:
                            error_text = await audio_response.text()
                            if self.api_key:
                                error_text = error_text.replace(self.api_key, "***")
                            raise RuntimeError(
                                "Volcengine TTS v3 audio download failed with status "
                                f"{audio_response.status}: {error_text[:200]}"
                            )
                        audio_data = await audio_response.read()
                elif "audio" in response_data or "data" in response_data:
                    if audio_base64 is not None and not isinstance(audio_base64, str):
                        raise RuntimeError(
                            "Volcengine TTS v3 returned a non-string audio payload."
                        )
                    raise RuntimeError("Volcengine TTS v3 returned empty audio data.")
                else:
                    response_keys = ", ".join(sorted(response_data)) or "none"
                    raise RuntimeError(
                        "Volcengine TTS v3 returned no audio payload or URL. "
                        f"Response keys: {response_keys}."
                    )

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            error_message = str(exc)
            if self.api_key:
                error_message = error_message.replace(self.api_key, "***")
            raise RuntimeError(
                f"Volcengine TTS v3 network request failed: {error_message}"
            ) from exc

        if not audio_data:
            raise RuntimeError("Volcengine TTS v3 returned empty audio data.")

        try:
            temp_dir = Path(get_astrbot_temp_path())
            await asyncio.to_thread(temp_dir.mkdir, parents=True, exist_ok=True)
            extension = AUDIO_FILE_EXTENSIONS[self.audio_format]
            file_path = temp_dir / (
                f"volcengine_tts_v3_{generate_timestamp_id()}.{extension}"
            )
            await asyncio.to_thread(file_path.write_bytes, audio_data)
        except OSError as exc:
            raise RuntimeError(
                f"Volcengine TTS v3 failed to write the audio file: {exc}"
            ) from exc
        return str(file_path)
