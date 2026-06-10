import uuid
from pathlib import Path

import httpx

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

SUPPORTED_CONTAINER_OUTPUT_PREFIXES = ("mp3", "wav", "opus")
RAW_AUDIO_OUTPUT_PREFIXES = ("pcm", "ulaw", "alaw")


def _parse_optional_float(
    provider_config: dict,
    cfg_name: str,
) -> float | None:
    value = provider_config.get(cfg_name, "")
    if value in ("", None):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{cfg_name} must be a number between 0 and 1.") from exc
    if not 0 <= parsed <= 1:
        raise ValueError(f"{cfg_name} must be between 0 and 1.")
    return parsed


def _parse_bool(provider_config: dict, cfg_name: str) -> bool:
    value = provider_config[cfg_name]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    raise ValueError(f"{cfg_name} must be a boolean value.")


def _normalize_timeout(value: int | str | None) -> int:
    if value in ("", None):
        return 20
    try:
        timeout = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout must be a positive integer.") from exc
    if timeout <= 0:
        raise ValueError("timeout must be a positive integer.")
    return timeout


def _validate_output_format(output_format: str) -> None:
    fmt = output_format.lower()
    if fmt.startswith(RAW_AUDIO_OUTPUT_PREFIXES):
        raise ValueError(
            "ElevenLabs raw audio output formats are not supported by this provider. "
            "Use an mp3, wav, or opus output format instead."
        )
    if not fmt.startswith(SUPPORTED_CONTAINER_OUTPUT_PREFIXES):
        raise ValueError(
            "Unsupported ElevenLabs output format. "
            "Use an mp3, wav, or opus output format."
        )


@register_provider_adapter(
    "elevenlabs_tts_api",
    "ElevenLabs TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderElevenLabsTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get(
            "api_base", "https://api.elevenlabs.io/v1"
        ).removesuffix("/")
        self.voice_id = provider_config.get(
            "elevenlabs-tts-voice-id", "JBFqnCBsd6RMkjVDRZzb"
        )
        self.model_id = provider_config.get("model", "eleven_multilingual_v2")
        self.set_model(self.model_id)
        self.output_format = provider_config.get(
            "elevenlabs-tts-output-format", "mp3_44100_128"
        )
        _validate_output_format(self.output_format)

        # Only send explicitly configured voice settings so the API can apply defaults.
        self.voice_settings: dict = {}
        for key, cfg_name in (
            ("stability", "elevenlabs-tts-stability"),
            ("similarity_boost", "elevenlabs-tts-similarity-boost"),
            ("style", "elevenlabs-tts-style"),
        ):
            value = _parse_optional_float(provider_config, cfg_name)
            if value is not None:
                self.voice_settings[key] = value
        if "elevenlabs-tts-use-speaker-boost" in provider_config:
            self.voice_settings["use_speaker_boost"] = _parse_bool(
                provider_config,
                "elevenlabs-tts-use-speaker-boost",
            )

        timeout = _normalize_timeout(provider_config.get("timeout", 20))

        proxy = provider_config.get("proxy", "")
        if proxy:
            logger.info(f"[ElevenLabs TTS] 使用代理: {proxy}")
        self.client = httpx.AsyncClient(
            timeout=timeout,
            proxy=proxy or None,
            trust_env=False,
        )

    def _output_extension(self) -> str:
        """Infer the audio file extension from the configured output format."""
        fmt = self.output_format.lower()
        if fmt.startswith("mp3"):
            return "mp3"
        if fmt.startswith("opus"):
            return "opus"
        if fmt.startswith("wav"):
            return "wav"
        return "mp3"

    async def get_audio(self, text: str) -> str:
        url = f"{self.api_base}/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload: dict = {
            "text": text,
            "model_id": self.model_name,
        }
        if self.voice_settings:
            payload["voice_settings"] = self.voice_settings

        response = await self.client.post(
            url,
            headers=headers,
            params={"output_format": self.output_format},
            json=payload,
        )
        if response.status_code != 200:
            error_text = response.text[:1024]
            raise Exception(
                f"ElevenLabs TTS API 请求失败: {response.status_code}, {error_text}"
            )

        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        path = (
            temp_dir / f"elevenlabs_tts_api_{uuid.uuid4()}.{self._output_extension()}"
        )
        path.write_bytes(response.content)
        return str(path)

    async def terminate(self):
        if self.client:
            await self.client.aclose()
