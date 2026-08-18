import asyncio
import uuid
import wave
from pathlib import Path

from google import genai
from google.genai import types

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "Gemini TTS audio generation failed"


@register_provider_adapter(
    "gemini_tts",
    "Gemini TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderGeminiTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        api_key: str = provider_config.get("gemini_tts_api_key", "")
        api_base: str | None = provider_config.get("gemini_tts_api_base")
        timeout: int = int(provider_config.get("gemini_tts_timeout", 20))
        http_options = types.HttpOptions(timeout=timeout * 1000)

        if api_base:
            api_base = api_base.removesuffix("/")
            http_options.base_url = api_base
        from astrbot.core.utils.proxy_route import (
            httpx_client_kwargs,
            resolve_proxy_route,
        )

        route = resolve_proxy_route(local_config=provider_config)
        http_options.async_client_args = httpx_client_kwargs(route)

        self.client = genai.Client(api_key=api_key, http_options=http_options).aio
        self.model: str = provider_config.get(
            "gemini_tts_model",
            "gemini-2.5-flash-preview-tts",
        )
        self.set_model(self.model)
        self.prefix: str | None = provider_config.get(
            "gemini_tts_prefix",
        )
        self.voice_name: str = provider_config.get("gemini_tts_voice_name", "Leda")

    @staticmethod
    def _extract_audio(response: object) -> bytes:
        """Validate and return the PCM audio data from a Gemini response."""
        candidates = getattr(response, "candidates", None)
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("Gemini TTS returned no candidates")
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None)
        if not isinstance(parts, list) or not parts:
            raise ValueError("Gemini TTS returned no audio parts")
        inline_data = getattr(parts[0], "inline_data", None)
        audio = getattr(inline_data, "data", None)
        if not isinstance(audio, (bytes, bytearray)) or not audio:
            raise ValueError("Gemini TTS returned invalid audio data")
        return bytes(audio)

    async def get_audio(self, text: str) -> str:
        path = Path(get_astrbot_temp_path()) / f"gemini_tts_{uuid.uuid4()}.wav"
        completed = False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            prompt = f"{self.prefix}: {text}" if self.prefix else text
            client = self.client
            if client is None:
                raise RuntimeError(_REQUEST_ERROR)
            response = await client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=self.voice_name,
                            ),
                        ),
                    ),
                ),
            )
            audio = self._extract_audio(response)

            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(audio)

            completed = True
            return str(path)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[Gemini TTS] Request failed: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None
        finally:
            if not completed:
                path.unlink(missing_ok=True)

    async def terminate(self):
        client = self.client
        self.client = None
        if client is None:
            return
        try:
            await client.aclose()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[Gemini TTS] Client close failed: %s", safe_error("", exc))
