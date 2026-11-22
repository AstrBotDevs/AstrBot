from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import httpx

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "stepfun_tts_api",
    "StepFun TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderStepFunTTSAPI(TTSProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(provider_config.get("model") or "stepaudio-3-tts")
        self.voice = provider_config.get("stepfun-tts-voice") or "wenrounvsheng"
        api_base = provider_config.get("api_base") or "https://api.stepfun.com/v1"
        api_key = provider_config.get("api_key", "")
        self.client = httpx.AsyncClient(
            base_url=api_base,
            headers={**self.request_headers, "Authorization": f"Bearer {api_key}"},
            timeout=float(provider_config.get("timeout") or 60),
            proxy=provider_config.get("proxy") or None,
        )

    async def get_audio(self, text: str) -> str:
        """Synthesize speech through StepFun's HTTP API.

        Args:
            text: Text to synthesize.

        Returns:
            Path to the generated WAV file.

        Raises:
            httpx.HTTPError: If the API request fails.
            OSError: If the WAV file cannot be written.
            ValueError: If StepFun returns an invalid WAV response.
        """
        response = await self.client.post(
            "audio/speech",
            json={
                "model": self.model_name,
                "input": text,
                "voice": self.voice,
                "response_format": "wav",
            },
        )
        response.raise_for_status()
        audio = response.content
        if len(audio) <= 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            raise ValueError("StepFun TTS returned an invalid WAV response")

        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = temp_dir / f"stepfun_tts_api_{uuid4().hex}.wav"
        try:
            output_path.write_bytes(audio)
        except OSError:
            with suppress(OSError):
                output_path.unlink(missing_ok=True)
            raise
        return str(output_path)

    async def terminate(self) -> None:
        await self.client.aclose()
